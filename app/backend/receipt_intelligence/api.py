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
from .evaluation import matched_evaluation


class CorrectionBody(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    policy: Policy = "SAFE"
    note: str = Field(default="", max_length=500)


class UndoBody(BaseModel):
    policy: Policy = "SAFE"


class ReplayBody(BaseModel):
    merchant_id: str = MERCHANT_ID
    policy: Policy = "SAFE"


class MemoryReceiptBody(BaseModel):
    raw_text: str = Field(min_length=1,max_length=160,pattern=r".*\S.*")
    price_cents: int = Field(ge=1,le=100000)
    merchant_type: str = Field(default="supermarket",min_length=1,max_length=60)
    pos_namespace: str = Field(default="demo-pos",min_length=1,max_length=80)
    identifier: str | None = Field(default=None,min_length=1,max_length=80)
    policy: Policy = "SAFE"


class MemoryReviewBody(BaseModel):
    product_id: str = Field(min_length=1,max_length=80)
    action: Literal["confirm","reject"]
    identity_checked: bool = False
    note: str = Field(default="",max_length=500)
    policy: Policy = "SAFE"


class MemoryReverseBody(BaseModel):
    note: str = Field(default="Reverse merchant product review",max_length=500)
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
                "primary_policies":["ONE_SHOT","TWO_STAGE"],
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
            return service.inspect(line_id,merchant_id,policy)
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

    @application.post("/api/merchants/{merchant_id}/memory/receipts")
    def process_memory_receipt(merchant_id: str,body: MemoryReceiptBody):
        try:
            service.merchant(merchant_id)
            line_id = service.memory.db.add_receipt(merchant_id,body.raw_text,body.price_cents,
                body.merchant_type,body.pos_namespace,body.identifier)
            return inspect(merchant_id,line_id,body.policy)
        except KeyError:
            raise HTTPException(404,"Merchant not found") from None

    @application.post("/api/merchants/{merchant_id}/lines/{line_id}/memory-review")
    async def review_product(merchant_id: str,line_id: str,body: MemoryReviewBody):
        try:
            service.merchant(merchant_id)
            line,context = service.input(line_id,merchant_id)
            original = service.decision(line_id,merchant_id,body.policy).model_dump()
            service.memory.review(line,merchant_id,context,body.product_id,body.action,
                                  body.identity_checked,body.note,original)
            await broker.publish(merchant_id,{"type":"memory.reviewed","line_id":line_id})
            return inspect(merchant_id,line_id,body.policy)
        except KeyError:
            raise HTTPException(404,"Merchant, receipt or product not found") from None
        except ValueError as exc:
            raise HTTPException(409,str(exc)) from None

    @application.post("/api/merchants/{merchant_id}/lines/{line_id}/memory-reviews/{event_id}/reverse")
    async def reverse_product_review(merchant_id: str,line_id: str,event_id: int,body: MemoryReverseBody):
        try:
            service.merchant(merchant_id)
            line,context = service.input(line_id,merchant_id)
            events = service.memory.db.audit(merchant_id,context["pos_namespace"],line.merchant_type,
                                            service.memory.assess(line,merchant_id,retrieve=False)["normalized_alias"])
            if event_id not in {event["id"] for event in events}:
                raise KeyError("Review not found for this receipt")
            service.memory.db.reverse(merchant_id,event_id,body.note)
            await broker.publish(merchant_id,{"type":"memory.reversed","line_id":line_id})
            return inspect(merchant_id,line_id,body.policy)
        except KeyError:
            raise HTTPException(404,"Merchant receipt or review not found") from None
        except ValueError as exc:
            raise HTTPException(409,str(exc)) from None

    @application.get("/api/product-memory/evaluation")
    def memory_evaluation():
        path = PROJECT / "app/data/product_memory_evaluation_results.json"
        if not path.exists():
            raise HTTPException(404,"Product memory evaluation has not been recorded")
        return json.loads(path.read_text(encoding="utf-8"))

    @application.get("/api/evaluation")
    def evaluation():
        folder = PROJECT / "results/taxonomy-v2"
        pilot = json.loads((folder/"pilot-30/threshold_summary.json").read_text(encoding="utf-8"))
        comparison = json.loads((folder/"followup-D-vs-TOPDOWN/combined_summary.json").read_text(encoding="utf-8"))
        decisions = json.loads((folder/"pilot-30/offline_decisions.json").read_text(encoding="utf-8"))
        return {"notice":"Exploratory synthetic evaluation — not independent merchant ground truth.",
                "pilot":[r for r in pilot if r["method"]=="A" or r["threshold"]==.85],
                "followup":comparison,
                "matched_comparison":matched_evaluation(catalog,service.engine),
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
