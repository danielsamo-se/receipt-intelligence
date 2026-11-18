import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal

from .catalog import Catalog, PROJECT
from .engine import DecisionEngine, Policy
from .service import MERCHANT_ID, NOTICE, ReceiptService
from .storage import Store
from .replay import EventBroker, ReplayManager


class CorrectionBody(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    policy: Policy = "SAFE"
    note: str = Field(default="", max_length=500)


class UndoBody(BaseModel):
    policy: Policy = "SAFE"


class ReplayBody(BaseModel):
    merchant_id: str = MERCHANT_ID
    policy: Policy = "SAFE"


def create_app(db_path: Path | None = None, replay_interval: float = 1.0) -> FastAPI:
    catalog = Catalog()
    store = Store(db_path or PROJECT / os.environ.get("RECEIPT_DB_PATH", "app/.local/demo.sqlite3"))
    service = ReceiptService(store,catalog)
    broker = EventBroker()
    replay = ReplayManager(service,broker,replay_interval)
    @asynccontextmanager
    async def lifespan(application):
        store.interrupt_replays()
        yield
        await replay.close()
    application = FastAPI(title="Receipt Intelligence", version="0.1.0",lifespan=lifespan)
    application.state.service = service
    application.state.store = store
    application.state.replay = replay

    @application.get("/api/health")
    def health():
        return {"status": "ok", "mode": "cached_offline", "receipt_lines": len(catalog.lines)}

    @application.get("/api/bootstrap")
    def bootstrap():
        pilot_count = sum(line.dataset=="pilot" for line in catalog.lines.values())
        holdout_count = sum(line.dataset=="holdout" for line in catalog.lines.values())
        return {"merchant_id":MERCHANT_ID,"merchant_name":service.assumptions["merchant_name"],"notice":NOTICE,
                "period_label":service.assumptions["period_label"],"taxonomy_version":catalog.taxonomy["version"],
                "nodes":list(catalog.nodes.values()),"line_count":len(catalog.lines),
                "scopes":[{"value":"pilot","label":f"Initial examples · {pilot_count}"},{"value":"holdout","label":f"Additional examples · {holdout_count}"},{"value":"all","label":f"All examples · {len(catalog.lines)}"}]}

    @application.get("/api/taxonomy")
    def taxonomy():
        return {"version": catalog.taxonomy["version"], "nodes": list(catalog.nodes.values())}

    @application.get("/api/decision/{line_id}")
    def decision(line_id: str, policy: Policy = "SAFE", merchant_id: str = "nordmarkt-demo"):
        try:
            return service.decision(line_id, merchant_id, policy)
        except KeyError:
            raise HTTPException(404, "Receipt line not found") from None

    @application.get("/api/merchants/{merchant_id}/report")
    def report(merchant_id: str, policy: Policy = "SAFE", dataset: Literal["pilot","holdout","all"] = "pilot", session_id: str | None = None):
        try:
            return service.report(merchant_id,policy,dataset,replay_id=session_id)
        except KeyError:
            raise HTTPException(404,"Demo merchant or replay session not found") from None

    @application.get("/api/merchants/{merchant_id}/lines/{line_id}")
    def inspect(merchant_id: str,line_id: str,policy: Policy = "SAFE"):
        try:
            return {"decision":service.decision(line_id,merchant_id,policy),
                    "sales_assumption":service.assumptions["items"][line_id],"audit":store.audit(merchant_id,line_id)}
        except KeyError:
            raise HTTPException(404,"Merchant or receipt line not found") from None

    @application.post("/api/merchants/{merchant_id}/lines/{line_id}/corrections")
    async def correct(merchant_id: str,line_id: str,body: CorrectionBody):
        try:
            service.set_override(line_id,merchant_id,body.policy,body.node_id,body.note)
            await broker.publish(merchant_id,{"type":"correction.saved","line_id":line_id})
            return inspect(merchant_id,line_id,body.policy)
        except KeyError:
            raise HTTPException(404,"Merchant or receipt line not found") from None
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from None

    @application.post("/api/merchants/{merchant_id}/lines/{line_id}/undo")
    async def undo(merchant_id: str,line_id: str,body: UndoBody):
        try:
            service.undo(line_id,merchant_id,body.policy)
            await broker.publish(merchant_id,{"type":"correction.undone","line_id":line_id})
            return inspect(merchant_id,line_id,body.policy)
        except KeyError:
            raise HTTPException(404,"Merchant or receipt line not found") from None
        except ValueError as exc:
            raise HTTPException(409,str(exc)) from None

    @application.get("/api/evaluation")
    def evaluation():
        folder = PROJECT / "results/taxonomy-v2"
        pilot = json.loads((folder/"pilot-30/threshold_summary.json").read_text(encoding="utf-8"))
        comparison = json.loads((folder/"followup-D-vs-TOPDOWN/combined_summary.json").read_text(encoding="utf-8"))
        decisions = json.loads((folder/"pilot-30/offline_decisions.json").read_text(encoding="utf-8"))
        return {"notice":"Exploratory synthetic evaluation — not independent merchant ground truth.",
                "pilot":[r for r in pilot if r["method"]=="A" or r["threshold"]==.85],
                "followup":comparison,
                "forced_examples":[{k:d[k] for k in ("id","raw_text","ground_truth","prediction","score","outcome")} for d in decisions if d["method"]=="A" and d["outcome"] not in ("correct_leaf","correct_parent")],
                "sources":["results/taxonomy-v2/pilot-30/threshold_summary.json","results/taxonomy-v2/followup-D-vs-TOPDOWN/combined_summary.json"],
                "limitations":["54 synthetic examples; proposed labels are not independent merchant ground truth.","No statistical significance, production accuracy or calibration claim.","Merchant corrections are operational feedback, separate from frozen evaluation labels."]}

    @application.websocket("/api/ws")
    async def events(socket: WebSocket, merchant_id: str = MERCHANT_ID):
        try:
            service.merchant(merchant_id)
        except KeyError:
            await socket.close(code=1008)
            return
        await broker.connect(merchant_id,socket)
        try:
            while True:
                message = await socket.receive_text()
                if message == "ping":
                    await socket.send_json({"type":"pong"})
        except WebSocketDisconnect:
            pass
        finally:
            broker.disconnect(merchant_id,socket)

    @application.post("/api/replay")
    async def start_replay(body: ReplayBody):
        try:
            return await replay.start(body.merchant_id,body.policy)
        except KeyError:
            raise HTTPException(404,"Demo merchant not found") from None

    @application.get("/api/replay/{session_id}")
    def get_replay(session_id: str,merchant_id: str = MERCHANT_ID):
        try:
            service.merchant(merchant_id)
            return store.replay(session_id,merchant_id)
        except KeyError:
            raise HTTPException(404,"Replay session not found") from None

    @application.post("/api/replay/{session_id}/reset")
    async def reset_replay(session_id: str,body: ReplayBody):
        try:
            return await replay.reset(session_id,body.merchant_id,body.policy)
        except KeyError:
            raise HTTPException(404,"Replay session not found") from None

    @application.post("/api/replay/{session_id}/stop")
    async def stop_replay(session_id: str,body: ReplayBody):
        try:
            return await replay.stop(session_id,body.merchant_id)
        except KeyError:
            raise HTTPException(404,"Replay session not found") from None

    built_frontend = PROJECT / "app/frontend/dist"
    if built_frontend.is_dir():
        application.mount("/",StaticFiles(directory=built_frontend,html=True),name="frontend")

    return application


app = create_app()
