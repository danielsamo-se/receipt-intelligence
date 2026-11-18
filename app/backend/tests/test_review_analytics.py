import json

import pytest
from fastapi.testclient import TestClient

from receipt_intelligence.api import create_app
from receipt_intelligence.service import MERCHANT_ID, ReceiptService
from receipt_intelligence.storage import Store


@pytest.fixture
def database(tmp_path):
    return tmp_path / "test.sqlite3"


@pytest.fixture
def service(database):
    return ReceiptService(Store(database))


def test_exact_override_precedence_scope_persistence_and_audit(service,database):
    before = service.decision("pilot:24",MERCHANT_ID,"SAFE")
    assert before.outcome == "parent_only"
    service.set_override("pilot:24",MERCHANT_ID,"SAFE","dairy_eggs.yogurt_quark","Merchant checked this exact line")
    for policy in ("SAFE","FORCED"):
        d = ReceiptService(Store(database)).decision("pilot:24",MERCHANT_ID,policy)
        assert d.outcome == "override" and d.specificity == "leaf" and not d.review_required
        assert d.node_id == "dairy_eggs.yogurt_quark"
        assert d.underlying_model["policy"] == policy
        assert d.assessments[0]["available"]
    assert service.decision("pilot:25",MERCHANT_ID,"SAFE").outcome != "override"
    service.store.set_override("other-merchant","pilot:13","dairy_eggs.cheese","SAFE",{},"other scope")
    assert service.decision("pilot:13",MERCHANT_ID,"SAFE").outcome != "override"
    audit = service.store.audit(MERCHANT_ID,"pilot:24")
    assert audit[0]["original_classification"]["outcome"] == "parent_only"
    assert audit[0]["created_at"] and audit[0]["original_model_decision"]["assessments"]


def test_multiple_corrections_undo_restore_and_persist(service,database):
    service.set_override("pilot:24",MERCHANT_ID,"SAFE","dairy_eggs.yogurt_quark","")
    service.set_override("pilot:24",MERCHANT_ID,"SAFE","dairy_eggs.cheese","")
    service.undo("pilot:24",MERCHANT_ID,"SAFE")
    assert ReceiptService(Store(database)).decision("pilot:24",MERCHANT_ID,"SAFE").node_id == "dairy_eggs.yogurt_quark"
    service.undo("pilot:24",MERCHANT_ID,"SAFE")
    assert service.decision("pilot:24",MERCHANT_ID,"SAFE").outcome == "parent_only"
    assert [e["action"] for e in service.store.audit(MERCHANT_ID,"pilot:24")] == ["undo","undo","set","set"]
    with pytest.raises(ValueError):
        service.undo("pilot:24",MERCHANT_ID,"SAFE")


def test_invalid_corrections_do_not_create_events(service):
    for node in ("not_a_category","adjustments.discount"):
        with pytest.raises(ValueError):
            service.set_override("pilot:24",MERCHANT_ID,"SAFE",node,"")
    assert service.store.audit(MERCHANT_ID,"pilot:24") == []
    with pytest.raises(KeyError):
        service.set_override("bad-line",MERCHANT_ID,"SAFE","produce.fruit","")


@pytest.mark.parametrize("policy",["SAFE","FORCED"])
@pytest.mark.parametrize("dataset",["pilot","holdout","all"])
def test_reporting_reconciles_and_excludes_adjustments(service,policy,dataset):
    report = service.report(MERCHANT_ID,policy,dataset)
    t = report["totals"]
    expected_sales = sum(r["value_cents"] for r in report["lines"] if r["record_type"]=="sale")
    expected_adjustments = sum(r["value_cents"] for r in report["lines"] if r["record_type"]!="sale")
    assert t["sales_value_cents"] == expected_sales
    assert t["adjustment_value_cents"] == expected_adjustments
    assert t["sales_value_cents"] == t["leaf_value_cents"]+t["parent_value_cents"]+t["unresolved_value_cents"]
    assert t["net_receipt_value_cents"] == expected_sales+expected_adjustments
    assert sum(c["leaf_value_cents"]+c["parent_value_cents"] for c in report["categories"]) == t["leaf_value_cents"]+t["parent_value_cents"]
    assert "adjustments" not in {c["id"] for c in report["categories"]}


def test_correction_moves_exact_sales_value_and_clears_review(service):
    report = service.report(MERCHANT_ID,"SAFE")
    line = next(r for r in report["lines"] if r["line_id"]=="pilot:24")
    service.set_override("pilot:24",MERCHANT_ID,"SAFE","dairy_eggs.yogurt_quark","")
    after = service.report(MERCHANT_ID,"SAFE")
    assert after["totals"]["leaf_value_cents"]-report["totals"]["leaf_value_cents"] == line["value_cents"]
    assert report["totals"]["parent_value_cents"]-after["totals"]["parent_value_cents"] == line["value_cents"]
    assert report["totals"]["net_receipt_value_cents"] == after["totals"]["net_receipt_value_cents"]
    assert "pilot:24" not in {r["line_id"] for r in after["review_queue"]}
    assert [r["value_cents"] for r in after["review_queue"]] == sorted([r["value_cents"] for r in after["review_queue"]],reverse=True)


def test_rest_correction_reload_and_undo(database):
    url=f"/api/merchants/{MERCHANT_ID}/lines/pilot:24"
    with TestClient(create_app(database)) as client:
        assert client.post(url+"/corrections",json={"node_id":"dairy_eggs.yogurt_quark","policy":"SAFE"}).status_code==200
    with TestClient(create_app(database)) as client:
        assert client.get(url).json()["decision"]["outcome"]=="override"
        assert client.post(url+"/undo",json={"policy":"SAFE"}).status_code==200
        assert client.get(url).json()["decision"]["outcome"]=="parent_only"
        assert client.post(url+"/corrections",json={"node_id":"invented"}).status_code==422
        assert client.get('/api/merchants/not-this-merchant/report').status_code==404
        assert client.get('/api/evaluation').json()["pilot"][0]["method"]=="A"
