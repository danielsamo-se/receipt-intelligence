from fastapi import FastAPI, HTTPException

from .catalog import Catalog
from .engine import DecisionEngine, Policy


def create_app() -> FastAPI:
    catalog = Catalog()
    engine = DecisionEngine(catalog)
    application = FastAPI(title="Receipt Intelligence", version="0.1.0")

    @application.get("/api/health")
    def health():
        return {"status": "ok", "mode": "cached_offline", "receipt_lines": len(catalog.lines)}

    @application.get("/api/taxonomy")
    def taxonomy():
        return {"version": catalog.taxonomy["version"], "nodes": list(catalog.nodes.values())}

    @application.get("/api/decision/{line_id}")
    def decision(line_id: str, policy: Policy = "SAFE", merchant_id: str = "nordmarkt-demo"):
        try:
            return engine.resolve(line_id, merchant_id, policy)
        except KeyError:
            raise HTTPException(404, "Receipt line not found") from None

    return application


app = create_app()
