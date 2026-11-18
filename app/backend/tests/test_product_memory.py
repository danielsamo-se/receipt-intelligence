import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from receipt_intelligence.api import create_app
from receipt_intelligence.catalog import ReceiptLine
from receipt_intelligence.product_memory import normalize, pack_sizes
from receipt_intelligence.service import MERCHANT_ID, ReceiptService
from receipt_intelligence.storage import Store


@pytest.fixture
def service(tmp_path):
    return ReceiptService(Store(tmp_path / "memory.sqlite3"))


def receipt(service, text="ERDBEER JOGHURT NM 150 G", identifier=None, namespace="demo-pos"):
    return service.memory.db.add_receipt(MERCHANT_ID,text,79,"supermarket",namespace,identifier)


def review(service, line_id, product="SYN-104", action="confirm", checked=True):
    line,context = service.input(line_id,MERCHANT_ID)
    return service.memory.review(line,MERCHANT_ID,context,product,action,checked,"Checked synthetic catalog",
                                 service.decision(line_id,MERCHANT_ID,"SAFE").model_dump())


def test_exact_identifier_and_alias_bypass_policy_without_loading_model(service,monkeypatch):
    line_id = receipt(service,"ART 123456","SKU-104")
    def forbidden(*args):
        raise AssertionError("Known product must bypass model/cache classification")
    monkeypatch.setattr(service,"model_decision",forbidden)
    for policy in ("FORCED","SAFE"):
        d = service.decision(line_id,MERCHANT_ID,policy)
        assert d.node_id == "dairy_eggs.yogurt_quark" and not d.review_required
        assert d.product_memory["match"]["method"] == "confirmed_identifier"
        assert d.assessments == [] and d.provenance["actual_model_calls"] == 0
    alias = receipt(service,"  nm  erdb jog 150g  ")
    assert service.decision(alias,MERCHANT_ID,"SAFE").product_memory["match"]["method"] == "confirmed_alias"


def test_similarity_never_commits_identity_and_confirmation_persists(service):
    line_id = receipt(service)
    before = service.decision(line_id,MERCHANT_ID,"SAFE")
    assert before.node_id is None and before.review_required
    assert before.product_memory["match"] is None
    assert any(c["product"]["product_id"]=="SYN-104" for c in before.product_memory["candidates"])
    event = review(service,line_id)
    restarted = ReceiptService(Store(service.store.path))
    repeated = receipt(restarted)
    for policy in ("FORCED","SAFE"):
        d = restarted.decision(repeated,MERCHANT_ID,policy)
        assert d.node_id == "dairy_eggs.yogurt_quark" and d.product_memory["model_stage_bypassed"]
    audit = restarted.inspect(repeated,MERCHANT_ID,"SAFE")["decision"].product_memory["audit"]
    assert audit[0]["id"] == event and audit[0]["reversible"]
    assert audit[0]["evidence"]["original_decision"]["node_id"] is None
    assert audit[0]["evidence"]["identity_checked_by_merchant"] is True


def test_merchant_pos_and_type_isolation(service):
    line_id=receipt(service)
    review(service,line_id)
    line,_ = service.input(line_id,MERCHANT_ID)
    assert service.memory.assess(line,"other-merchant")["match"] is None
    assert service.memory.assess(line,MERCHANT_ID,"other-pos")["match"] is None
    other_type = ReceiptLine("other","other","memory_demo",line.raw_text,79,"drugstore")
    assert service.memory.assess(other_type,MERCHANT_ID)["match"] is None
    assert service.memory.db.audit("other-merchant","demo-pos","supermarket",normalize(line.raw_text)) == []
    with pytest.raises(KeyError):
        service.memory.db.receipt("other-merchant",line_id)


@pytest.mark.parametrize("text,identifier",[
    ("CC ZERO 1L","SKU-106"), # known identifier disagrees with exact alias
    ("COCA COLA ZERO 1L","SKU-106"), # variant contradicts known identifier
    ("WMF BRATPF 28CM","SKU-103"),
    ("WMF BRATPF 24CM","SKU-NOT-CONFIRMED"),
    ("BIO ZITRONEN REINIGER 500ML","SKU-108"),
    ("HARIBO POMMES FRITES TK 750G",None),
    ("ERDBEER JOGHURT 500G",None),
    ("ART 004711",None),
    ("MOLKEREI ART",None),
    ("PFAND COCA COLA 1L",None),
])
def test_near_matches_and_contradictions_never_auto_propagate(service,text,identifier):
    line_id=receipt(service,text,identifier)
    d=service.decision(line_id,MERCHANT_ID,"SAFE")
    assert d.product_memory["match"] is None
    assert not d.product_memory["model_stage_bypassed"]
    assert d.outcome != "override"


def test_conflicting_pack_and_generic_alias_cannot_be_confirmed(service):
    for text in ("ERDBEER JOGHURT 500G","JOGHURT","MOLKEREI ART"):
        line_id=receipt(service,text)
        with pytest.raises(ValueError):
            review(service,line_id)
    line_id=receipt(service)
    with pytest.raises(ValueError):
        review(service,line_id,checked=False)


def test_reject_reverse_confirm_and_reverse_are_append_only(service):
    line_id=receipt(service)
    rejection=review(service,line_id,action="reject",checked=False)
    d=service.decision(line_id,MERCHANT_ID,"SAFE")
    candidate=next(c for c in d.product_memory["candidates"] if c["product"]["product_id"]=="SYN-104")
    assert candidate["rejected"] and not candidate["eligible_for_confirmation"]
    with pytest.raises(ValueError): review(service,line_id)
    with pytest.raises(ValueError): service.memory.db.reverse("other-merchant",rejection,"")
    service.memory.db.reverse(MERCHANT_ID,rejection,"Undo rejection")
    confirmation=review(service,line_id)
    assert service.decision(line_id,MERCHANT_ID,"SAFE").product_memory["match"]
    service.memory.db.reverse(MERCHANT_ID,confirmation,"Wrong SKU checked")
    with pytest.raises(ValueError): service.memory.db.reverse(MERCHANT_ID,confirmation,"Repeat")
    restarted=ReceiptService(Store(service.store.path))
    d=restarted.inspect(line_id,MERCHANT_ID,"SAFE")["decision"]
    assert not d.product_memory["match"] and d.review_required
    assert [e["action"] for e in d.product_memory["audit"]]==["reverse","confirm","reverse","reject"]


def test_line_override_has_precedence_and_undo_restores_product_memory(service):
    line_id=receipt(service)
    review(service,line_id)
    service.set_override(line_id,MERCHANT_ID,"SAFE","dairy_eggs","Line-level correction")
    for policy in ("SAFE","FORCED"):
        d=service.decision(line_id,MERCHANT_ID,policy)
        assert d.node_id=="dairy_eggs" and d.specificity=="parent"
        assert d.product_memory["status"]=="line_override_precedence"
    service.undo(line_id,MERCHANT_ID,"SAFE")
    assert service.decision(line_id,MERCHANT_ID,"SAFE").node_id=="dairy_eggs.yogurt_quark"


def test_existing_jev_fallbacks_and_weekly_reconciliation_are_unchanged(service):
    baseline=service.report(MERCHANT_ID,"SAFE","all")
    for policy in ("FORCED","SAFE"):
        for line_id in service.catalog.lines:
            actual=service.decision(line_id,MERCHANT_ID,policy,retrieve=False)
            expected=service.engine.resolve(line_id,MERCHANT_ID,policy)
            assert (actual.node_id,actual.outcome,actual.specificity)==(expected.node_id,expected.outcome,expected.specificity)
    line_id=receipt(service)
    review(service,line_id)
    after=service.report(MERCHANT_ID,"SAFE","all")
    assert after["totals"]==baseline["totals"] and after["line_count"]==54


def test_lexical_fallback_does_not_break_existing_policy(service):
    class UnavailableEncoder:
        def vector(self,*args): return None
        def status(self): return {"available":False,"error":"Test: no local model"}
    service.memory.encoder=UnavailableEncoder()
    line_id=receipt(service)
    d=service.decision(line_id,MERCHANT_ID,"SAFE")
    assert d.product_memory["retrieval_mode"]=="lexical_only" and d.review_required
    assert d.product_memory["candidates"][0]["semantic_cosine"] is None
    assert service.decision("pilot:24",MERCHANT_ID,"SAFE").outcome=="parent_only"


def test_rest_confirm_reload_reprocess_reverse_and_validation(tmp_path):
    database=tmp_path / "api.sqlite3"
    base=f"/api/merchants/{MERCHANT_ID}"
    with TestClient(create_app(database)) as client:
        created=client.post(base+"/memory/receipts",json={"raw_text":"ERDBEER JOGHURT NM 150 G","price_cents":79}).json()
        line_id=created["decision"]["line_id"]
        endpoint=base+f"/lines/{line_id}"
        assert not created["included_in_weekly_analytics"]
        assert client.post(endpoint+"/memory-review",json={"product_id":"SYN-104","action":"confirm"}).status_code==409
        response=client.post(endpoint+"/memory-review",json={"product_id":"SYN-104","action":"confirm","identity_checked":True})
        assert response.status_code==200 and response.json()["decision"]["product_memory"]["model_stage_bypassed"]
        event=response.json()["decision"]["product_memory"]["audit"][0]["id"]
    with TestClient(create_app(database)) as client:
        assert client.get(endpoint).json()["decision"]["node_id"]=="dairy_eggs.yogurt_quark"
        other=client.post(base+"/memory/receipts",json={"raw_text":"ART 999","price_cents":79}).json()["decision"]["line_id"]
        assert client.post(base+f"/lines/{other}/memory-reviews/{event}/reverse",json={}).status_code==404
        assert client.post(endpoint+f"/memory-reviews/{event}/reverse",json={}).status_code==200
        assert client.get(endpoint).json()["decision"]["node_id"] is None
        assert client.post("/api/merchants/other/memory/receipts",json={"raw_text":"A","price_cents":1}).status_code==404
        assert client.post(base+"/memory/receipts",json={"raw_text":"  ","price_cents":79}).status_code==422


def test_identity_normalization_retains_distinguishing_details():
    assert normalize("  CC  ZERO 1L ")=="cc zero 1l"
    assert normalize("CC ZERO 1 L")!=normalize("CC ZERO 1L")
    assert normalize("CC ORIGINAL 1L")!=normalize("CC ZERO 1L")
    assert pack_sizes("0,5 KG 1000ML")=={"500g","1l"}
