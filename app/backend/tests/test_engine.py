import pytest
from fastapi.testclient import TestClient

from receipt_intelligence.api import create_app
from receipt_intelligence.catalog import CachedResponses, Catalog
from receipt_intelligence.engine import DecisionEngine


@pytest.fixture
def catalog():
    return Catalog()


@pytest.fixture
def engine(catalog):
    return DecisionEngine(catalog)


def test_real_cache_and_taxonomy(catalog):
    assert len(catalog.lines) == 54
    assert len(catalog.leaves) == 27
    evidence = CachedResponses(catalog).load(catalog.line("pilot:24"), "parent")
    assert evidence["choice"] == "dairy_eggs"
    assert evidence["probabilities"]["dairy_eggs"] == .94
    assert evidence["model"] == "typesafe/jev-1.14-20261014"
    assert catalog.parent_of("dairy_eggs.yogurt_quark") == "dairy_eggs"


def test_forced_ignores_abstention_without_fabricating_evidence(engine):
    d = engine.resolve("pilot:08", "merchant-a", "FORCED")
    assert d.outcome == "leaf" and d.node_id == "produce.fruit"
    assert d.scores["flat_leaf_probability"] == 0
    assert d.assessments[0]["choice"] == "unidentifiable"
    assert d.review_required
    assert "FORCED_TIE" in [r.code for r in d.applied_rules]


def test_safe_retains_parent_and_conditional_uncertainty(engine):
    d = engine.resolve("pilot:24", "merchant-a", "SAFE")
    assert d.outcome == "parent_only" and d.node_id == "dairy_eggs"
    assert d.assessments[1]["choice"] == "unspecified_child"
    assert d.review_required
    gratin = engine.resolve("holdout:H16", "merchant-a", "SAFE")
    assert gratin.node_id == "prepared_food" and gratin.outcome == "parent_only"
    assert gratin.scores["conditional_child_probability"] == .54


def test_safe_parent_gate_abstention_scope_and_leaf(engine):
    assert engine.resolve("pilot:03", "m", "SAFE").outcome == "unidentifiable"
    assert engine.resolve("pilot:08", "m", "SAFE").node_id is None
    assert engine.resolve("pilot:19", "m", "SAFE").outcome == "out_of_scope"
    assert engine.resolve("pilot:01", "m", "SAFE").node_id == "confectionery_snacks.confectionery"


def test_uncollected_and_missing_caches_are_unavailable(engine, catalog, monkeypatch, tmp_path):
    d = engine.resolve("holdout:H01", "m", "FORCED")
    assert d.availability == "unavailable" and d.outcome == "unidentifiable"
    cache = CachedResponses(catalog)
    monkeypatch.setattr(cache, "path", lambda line, stage: tmp_path / "missing.json")
    d = DecisionEngine(catalog, cache).resolve("pilot:01", "m", "SAFE")
    assert d.availability == "unavailable" and d.node_id is None


def test_backend_starts_and_routes_validate():
    with TestClient(create_app()) as client:
        assert client.get("/api/health").json()["receipt_lines"] == 54
        assert client.get("/api/decision/pilot:24?policy=SAFE").json()["outcome"] == "parent_only"
        assert client.get("/api/decision/no-such-line").status_code == 404
        assert client.get("/api/decision/pilot:01?policy=INVALID").status_code == 422
