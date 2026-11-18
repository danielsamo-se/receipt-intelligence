"""Product memory uses the same SQLite file/transactions as corrections and replay."""
from __future__ import annotations

import json
import uuid

from .catalog import ReceiptLine
from .storage import Store, now


class MemoryStore:
    def __init__(self, store: Store):
        self.store = store
        with store.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS memory_products (
                    merchant_id TEXT NOT NULL, product_id TEXT NOT NULL,
                    name TEXT NOT NULL, node_id TEXT NOT NULL, attributes_json TEXT NOT NULL,
                    source_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY (merchant_id,product_id)
                );
                CREATE TABLE IF NOT EXISTS memory_identifiers (
                    merchant_id TEXT NOT NULL, pos_namespace TEXT NOT NULL, identifier TEXT NOT NULL,
                    product_id TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY (merchant_id,pos_namespace,identifier),
                    FOREIGN KEY (merchant_id,product_id) REFERENCES memory_products(merchant_id,product_id)
                );
                CREATE TABLE IF NOT EXISTS memory_aliases (
                    merchant_id TEXT NOT NULL, pos_namespace TEXT NOT NULL, merchant_type TEXT NOT NULL,
                    alias TEXT NOT NULL, product_id TEXT NOT NULL, event_id INTEGER,
                    source_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY (merchant_id,pos_namespace,merchant_type,alias),
                    FOREIGN KEY (merchant_id,product_id) REFERENCES memory_products(merchant_id,product_id)
                );
                CREATE TABLE IF NOT EXISTS memory_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, merchant_id TEXT NOT NULL,
                    pos_namespace TEXT NOT NULL, merchant_type TEXT NOT NULL, alias TEXT NOT NULL,
                    product_id TEXT NOT NULL, action TEXT NOT NULL, undo_of INTEGER,
                    input_json TEXT NOT NULL, evidence_json TEXT NOT NULL,
                    note TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_active_reviews (
                    merchant_id TEXT NOT NULL, pos_namespace TEXT NOT NULL, merchant_type TEXT NOT NULL,
                    alias TEXT NOT NULL, product_id TEXT NOT NULL, event_id INTEGER NOT NULL,
                    PRIMARY KEY (merchant_id,pos_namespace,merchant_type,alias,product_id)
                );
                CREATE TABLE IF NOT EXISTS memory_receipts (
                    id TEXT PRIMARY KEY, merchant_id TEXT NOT NULL, raw_text TEXT NOT NULL,
                    price_cents INTEGER NOT NULL, merchant_type TEXT NOT NULL,
                    pos_namespace TEXT NOT NULL, identifier TEXT, created_at TEXT NOT NULL
                );
            """)

    def seed(self, data: dict, normalize):
        """Idempotent synthetic catalog import. Never reseeds a reversed merchant alias."""
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            for product in data["products"]:
                source = json.dumps({"kind":"synthetic_catalog_assumption", "version":data["version"],
                                     "notice":data["notice"], "classification_confirmed":True})
                inserted = db.execute("INSERT OR IGNORE INTO memory_products VALUES (?,?,?,?,?,?,?)",
                    (data["merchant_id"],product["product_id"],product["name"],product["node_id"],
                     json.dumps(product["attributes"]),source,now())).rowcount
                if not inserted:
                    continue
                db.execute("INSERT INTO memory_identifiers VALUES (?,?,?,?,?)",
                    (data["merchant_id"],data["pos_namespace"],product["identifier"],product["product_id"],now()))
                for alias in product["aliases"]:
                    db.execute("INSERT INTO memory_aliases VALUES (?,?,?,?,?,?,?,?)",
                        (data["merchant_id"],data["pos_namespace"],data["merchant_type"],normalize(alias),
                         product["product_id"],None,source,now()))

    def snapshot(self, merchant_id: str, namespace: str, merchant_type: str) -> dict:
        with self.store.connection() as db:
            db.execute("BEGIN")
            products = {}
            for row in db.execute("SELECT * FROM memory_products WHERE merchant_id=?",(merchant_id,)):
                product = dict(row)
                product["attributes"] = json.loads(product.pop("attributes_json"))
                product["source"] = json.loads(product.pop("source_json"))
                products[product["product_id"]] = product
            aliases = {}
            for row in db.execute("SELECT * FROM memory_aliases WHERE merchant_id=? AND pos_namespace=? AND merchant_type=?",
                                  (merchant_id,namespace,merchant_type)):
                alias = dict(row)
                alias["source"] = json.loads(alias.pop("source_json"))
                aliases[alias["alias"]] = alias
            identifiers = {r["identifier"]:r["product_id"] for r in db.execute(
                "SELECT * FROM memory_identifiers WHERE merchant_id=? AND pos_namespace=?",(merchant_id,namespace))}
            reviews = [dict(r) for r in db.execute("""SELECT e.* FROM memory_active_reviews a
                JOIN memory_events e ON e.id=a.event_id WHERE a.merchant_id=? AND a.pos_namespace=? AND a.merchant_type=?""",
                (merchant_id,namespace,merchant_type))]
            return {"products":products,"aliases":aliases,"identifiers":identifiers,"reviews":reviews}

    def review(self, merchant_id: str, namespace: str, merchant_type: str, alias: str,
               product_id: str, action: str, receipt: dict, evidence: dict, note: str) -> int:
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            key = (merchant_id,namespace,merchant_type,alias)
            current = db.execute("SELECT * FROM memory_aliases WHERE merchant_id=? AND pos_namespace=? AND merchant_type=? AND alias=?",key).fetchone()
            if action == "confirm" and current:
                raise ValueError("This alias already has a confirmed mapping. Reverse its confirmation before remapping.")
            if action == "reject" and current and current["product_id"] == product_id:
                raise ValueError("Reverse the existing confirmation before rejecting this mapping.")
            if not db.execute("SELECT 1 FROM memory_products WHERE merchant_id=? AND product_id=?",(merchant_id,product_id)).fetchone():
                raise KeyError("Merchant product not found")
            event_id = db.execute("INSERT INTO memory_events (merchant_id,pos_namespace,merchant_type,alias,product_id,action,input_json,evidence_json,note,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (*key,product_id,action,json.dumps(receipt),json.dumps(evidence),note,now())).lastrowid
            db.execute("INSERT INTO memory_active_reviews VALUES (?,?,?,?,?,?) ON CONFLICT(merchant_id,pos_namespace,merchant_type,alias,product_id) DO UPDATE SET event_id=excluded.event_id",
                (*key,product_id,event_id))
            if action == "confirm":
                db.execute("INSERT INTO memory_aliases VALUES (?,?,?,?,?,?,?,?)",
                    (*key,product_id,event_id,json.dumps({"kind":"merchant_identity_confirmation","event_id":event_id}),now()))
            self.store.bump(db)
            return event_id

    def reverse(self, merchant_id: str, event_id: int, note: str) -> int:
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM memory_events WHERE merchant_id=? AND id=?",(merchant_id,event_id)).fetchone()
            if not row or row["action"] not in ("confirm","reject"):
                raise ValueError("Active confirmation or rejection not found.")
            key = (merchant_id,row["pos_namespace"],row["merchant_type"],row["alias"],row["product_id"])
            active = db.execute("SELECT event_id FROM memory_active_reviews WHERE merchant_id=? AND pos_namespace=? AND merchant_type=? AND alias=? AND product_id=?",key).fetchone()
            if not active or active[0] != event_id:
                raise ValueError("This review has already been reversed or superseded.")
            db.execute("DELETE FROM memory_aliases WHERE merchant_id=? AND event_id=?",(merchant_id,event_id))
            db.execute("DELETE FROM memory_active_reviews WHERE merchant_id=? AND pos_namespace=? AND merchant_type=? AND alias=? AND product_id=?",key)
            result = db.execute("INSERT INTO memory_events (merchant_id,pos_namespace,merchant_type,alias,product_id,action,undo_of,input_json,evidence_json,note,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (*key,"reverse",event_id,row["input_json"],row["evidence_json"],note,now())).lastrowid
            self.store.bump(db)
            return result

    def audit(self, merchant_id: str, namespace: str, merchant_type: str, alias: str) -> list[dict]:
        with self.store.connection() as db:
            entries = [dict(r) for r in db.execute("SELECT * FROM memory_events WHERE merchant_id=? AND pos_namespace=? AND merchant_type=? AND alias=? ORDER BY id DESC",
                (merchant_id,namespace,merchant_type,alias))]
            active = {r[0] for r in db.execute("SELECT event_id FROM memory_active_reviews WHERE merchant_id=?",(merchant_id,))}
            for entry in entries:
                entry["input"] = json.loads(entry.pop("input_json"))
                entry["evidence"] = json.loads(entry.pop("evidence_json"))
                entry["reversible"] = entry["id"] in active
            return entries

    def add_receipt(self, merchant_id: str, raw_text: str, price_cents: int, merchant_type: str,
                    namespace: str, identifier: str | None) -> str:
        receipt_id = "memory:" + uuid.uuid4().hex
        with self.store.connection() as db:
            db.execute("INSERT INTO memory_receipts VALUES (?,?,?,?,?,?,?,?)",
                (receipt_id,merchant_id,raw_text,price_cents,merchant_type,namespace,identifier,now()))
        return receipt_id

    def receipt(self, merchant_id: str, line_id: str) -> tuple[ReceiptLine, dict]:
        with self.store.connection() as db:
            row = db.execute("SELECT * FROM memory_receipts WHERE id=? AND merchant_id=?",(line_id,merchant_id)).fetchone()
            if not row:
                raise KeyError("Merchant receipt not found")
            return ReceiptLine(row["id"],row["id"],"memory_demo",row["raw_text"],row["price_cents"],row["merchant_type"]), dict(row)
