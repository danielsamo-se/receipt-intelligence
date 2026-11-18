from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """Append-only correction ledger with an atomic merchant/line active pointer."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
                INSERT OR IGNORE INTO metadata VALUES ('revision', 0);
                CREATE TABLE IF NOT EXISTS correction_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    merchant_id TEXT NOT NULL, line_id TEXT NOT NULL, action TEXT NOT NULL,
                    node_id TEXT, previous_event_id INTEGER, undo_of INTEGER,
                    policy TEXT NOT NULL, before_json TEXT NOT NULL, model_json TEXT NOT NULL,
                    note TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS active_overrides (
                    merchant_id TEXT NOT NULL, line_id TEXT NOT NULL,
                    event_id INTEGER NOT NULL, node_id TEXT NOT NULL,
                    PRIMARY KEY (merchant_id, line_id)
                );
                CREATE TABLE IF NOT EXISTS replay_sessions (
                    id TEXT PRIMARY KEY, merchant_id TEXT NOT NULL, policy TEXT NOT NULL,
                    status TEXT NOT NULL, generation INTEGER NOT NULL,
                    sequence_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS replay_members (
                    session_id TEXT NOT NULL REFERENCES replay_sessions(id), line_id TEXT NOT NULL,
                    sequence_index INTEGER NOT NULL, processed_at TEXT NOT NULL,
                    PRIMARY KEY (session_id,line_id)
                );
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def bump(db):
        db.execute("UPDATE metadata SET value=value+1 WHERE key='revision'")

    def snapshot(self, merchant_id: str) -> tuple[int, dict]:
        with self.connection() as db:
            db.execute("BEGIN")
            revision = db.execute("SELECT value FROM metadata WHERE key='revision'").fetchone()[0]
            active = db.execute("""SELECT a.*, e.note, e.created_at, e.policy FROM active_overrides a
                                   JOIN correction_events e ON e.id=a.event_id WHERE a.merchant_id=?""", (merchant_id,)).fetchall()
            return revision, {r["line_id"]: dict(r) for r in active}

    def set_override(self, merchant_id: str, line_id: str, node_id: str, policy: str, model: dict, note: str,
                     before_decision: dict | None = None) -> int:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT * FROM active_overrides WHERE merchant_id=? AND line_id=?", (merchant_id, line_id)).fetchone()
            before = {"outcome": "override", "node_id": previous["node_id"], "event_id": previous["event_id"]} if previous else before_decision or model
            cursor = db.execute("""INSERT INTO correction_events
                (merchant_id,line_id,action,node_id,previous_event_id,policy,before_json,model_json,note,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""", (merchant_id, line_id, "set", node_id,
                previous["event_id"] if previous else None, policy, json.dumps(before), json.dumps(model), note, now()))
            event_id = cursor.lastrowid
            db.execute("""INSERT INTO active_overrides VALUES (?,?,?,?)
                ON CONFLICT(merchant_id,line_id) DO UPDATE SET event_id=excluded.event_id,node_id=excluded.node_id""",
                (merchant_id, line_id, event_id, node_id))
            self.bump(db)
            return event_id

    def undo(self, merchant_id: str, line_id: str, policy: str, model: dict) -> int:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute("""SELECT a.*, e.previous_event_id FROM active_overrides a
                JOIN correction_events e ON e.id=a.event_id WHERE a.merchant_id=? AND a.line_id=?""", (merchant_id, line_id)).fetchone()
            if active is None:
                raise ValueError("There is no active correction to undo.")
            prior = db.execute("SELECT * FROM correction_events WHERE id=?", (active["previous_event_id"],)).fetchone() if active["previous_event_id"] else None
            before = {"outcome": "override", "node_id": active["node_id"], "event_id": active["event_id"]}
            cursor = db.execute("""INSERT INTO correction_events
                (merchant_id,line_id,action,node_id,previous_event_id,undo_of,policy,before_json,model_json,note,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (merchant_id,line_id,"undo",prior["node_id"] if prior else None,
                active["event_id"],active["event_id"],policy,json.dumps(before),json.dumps(model),"Undo previous merchant correction",now()))
            if prior:
                db.execute("UPDATE active_overrides SET event_id=?,node_id=? WHERE merchant_id=? AND line_id=?", (prior["id"],prior["node_id"],merchant_id,line_id))
            else:
                db.execute("DELETE FROM active_overrides WHERE merchant_id=? AND line_id=?", (merchant_id,line_id))
            self.bump(db)
            return cursor.lastrowid

    def audit(self, merchant_id: str, line_id: str) -> list[dict]:
        with self.connection() as db:
            records = db.execute("SELECT * FROM correction_events WHERE merchant_id=? AND line_id=? ORDER BY id DESC", (merchant_id,line_id)).fetchall()
            result = []
            for row in records:
                entry = dict(row)
                entry["original_classification"] = json.loads(entry.pop("before_json"))
                entry["original_model_decision"] = json.loads(entry.pop("model_json"))
                result.append(entry)
            return result

    @staticmethod
    def _replay(db, session_id: str, merchant_id: str) -> dict:
        row = db.execute("SELECT * FROM replay_sessions WHERE id=? AND merchant_id=?", (session_id,merchant_id)).fetchone()
        if row is None:
            raise KeyError("Replay session not found")
        data = dict(row)
        data["sequence"] = json.loads(data.pop("sequence_json"))
        data["line_ids"] = [r[0] for r in db.execute("SELECT line_id FROM replay_members WHERE session_id=? ORDER BY sequence_index", (session_id,))]
        data["processed_count"] = len(data["line_ids"])
        data["total_count"] = len(data["sequence"])
        return data

    def replay(self, session_id: str, merchant_id: str) -> dict:
        with self.connection() as db:
            db.execute("BEGIN")
            return self._replay(db,session_id,merchant_id)

    def report_context(self, merchant_id: str, session_id: str) -> tuple[int,dict,dict]:
        with self.connection() as db:
            db.execute("BEGIN")
            revision = db.execute("SELECT value FROM metadata WHERE key='revision'").fetchone()[0]
            active = db.execute("""SELECT a.*,e.note,e.created_at,e.policy FROM active_overrides a
                JOIN correction_events e ON e.id=a.event_id WHERE a.merchant_id=?""",(merchant_id,)).fetchall()
            return revision,{r["line_id"]:dict(r) for r in active},self._replay(db,session_id,merchant_id)

    def create_replay(self, merchant_id: str, policy: str, sequence: list[str]) -> dict:
        if len(set(sequence)) != len(sequence):
            raise ValueError("Replay sequence must have unique receipt-line IDs.")
        session_id = uuid.uuid4().hex
        with self.connection() as db:
            db.execute("INSERT INTO replay_sessions VALUES (?,?,?,?,?,?,?)", (session_id,merchant_id,policy,"running",1,json.dumps(sequence),now()))
            self.bump(db)
        return self.replay(session_id,merchant_id)

    def add_replay_member(self, session_id: str, merchant_id: str, line_id: str, generation: int) -> bool:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            session = self._replay(db,session_id,merchant_id)
            if session["generation"] != generation or session["status"] != "running":
                return False
            if line_id not in session["sequence"]:
                raise ValueError("Receipt line is not part of this replay sequence.")
            result = db.execute("INSERT OR IGNORE INTO replay_members VALUES (?,?,?,?)", (session_id,line_id,session["sequence"].index(line_id),now()))
            if result.rowcount:
                self.bump(db)
            return bool(result.rowcount)

    def reset_replay(self, session_id: str, merchant_id: str, policy: str) -> dict:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._replay(db,session_id,merchant_id)
            db.execute("DELETE FROM replay_members WHERE session_id=?",(session_id,))
            db.execute("UPDATE replay_sessions SET generation=generation+1,status='running',policy=? WHERE id=?",(policy,session_id))
            self.bump(db)
        return self.replay(session_id,merchant_id)

    def replay_status(self, session_id: str, merchant_id: str, generation: int, status: str):
        with self.connection() as db:
            result = db.execute("UPDATE replay_sessions SET status=? WHERE id=? AND merchant_id=? AND generation=?",(status,session_id,merchant_id,generation))
            if result.rowcount:
                self.bump(db)

    def interrupt_replays(self):
        with self.connection() as db:
            result = db.execute("UPDATE replay_sessions SET status='interrupted' WHERE status='running'")
            if result.rowcount:
                self.bump(db)
