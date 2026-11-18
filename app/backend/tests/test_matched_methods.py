import json

import pytest

from receipt_intelligence.catalog import CachedResponses, Catalog, PROJECT
from receipt_intelligence.engine import DecisionEngine, PRIMARY_POLICIES
from receipt_intelligence.evaluation import matched_evaluation
from receipt_intelligence.service import MERCHANT_ID, ReceiptService
from receipt_intelligence.storage import Store


def test_every_raw_prediction_reproduces_frozen_followup():
    catalog=Catalog()
    engine=DecisionEngine(catalog)
    folder=PROJECT / "results/taxonomy-v2/followup-D-vs-TOPDOWN"
    for sample,dataset in (("original30","pilot"),("holdout24","holdout")):
        for row in json.loads((folder/sample/"per_line.json").read_text(encoding="utf-8")):
            for policy,method in (("ONE_SHOT","D"),("TWO_STAGE","TOPDOWN")):
                d=engine.resolve(f"{dataset}:{row['id']}",MERCHANT_ID,policy)
                assert d.availability=="complete"
                expected=row[method]["prediction"]
                actual=d.node_id or ("out_of_scope" if d.outcome=="out_of_scope" else None)
                assert actual==expected
                assert d.provenance["threshold"] is None


def test_raw_choices_are_not_silently_gated_and_parent_scores_are_not_leaf_scores():
    engine=DecisionEngine(Catalog())
    assert engine.resolve("pilot:20",MERCHANT_ID,"ONE_SHOT").node_id=="grains.bread_bakery"
    raw=engine.resolve("holdout:H16",MERCHANT_ID,"TWO_STAGE")
    assert raw.node_id=="prepared_food.potato_sides" and raw.scores["conditional_child_score"]==.54
    assert engine.resolve("holdout:H16",MERCHANT_ID,"SAFE").node_id=="prepared_food"
    for policy in PRIMARY_POLICIES:
        dairy=engine.resolve("pilot:24",MERCHANT_ID,policy)
        assert dairy.node_id=="dairy_eggs" and dairy.specificity=="parent" and dairy.review_required
        assert engine.resolve("pilot:08",MERCHANT_ID,policy).outcome=="unidentifiable"
        assert engine.resolve("pilot:19",MERCHANT_ID,policy).outcome=="out_of_scope"


def test_matched_metrics_costs_and_latencies_reconcile_with_frozen_summary():
    catalog=Catalog()
    comparison=matched_evaluation(catalog,DecisionEngine(catalog))
    historical=json.loads((PROJECT / "results/taxonomy-v2/followup-D-vs-TOPDOWN/combined_summary.json").read_text(encoding="utf-8"))
    for sample,size in (("original30",30),("holdout24",24)):
        current=comparison["samples"][sample]
        assert current["cohort"]["matched_count"]==size and not current["cohort"]["excluded"]
        for policy,method in (("ONE_SHOT","D"),("TWO_STAGE","TOPDOWN")):
            actual,expected=current["methods"][policy],historical[sample]["methods"][method]
            for key in ("correct_leaf","correct_parent","incorrect_category","overclaim","abstention",
                        "correct_scope_rejection","incorrect_scope_rejection","taxonomy_commitments",
                        "leaf_commitments","parent_commitments","taxonomy_coverage","classification_accuracy",
                        "median_receipt_latency_seconds"):
                assert actual[key]==expected[key],(sample,method,key)
            assert actual["requests"]==expected["usage"]["requests"]
            for key in ("input_tokens","output_tokens","cost"):
                assert actual["usage"][key]["available_sum"]==pytest.approx(expected["usage"][key]["available_sum"])
                assert actual["usage"][key]["missing_requests"]==0
            assert sum(actual[k] for k in ("correct_leaf","correct_parent","incorrect_category","overclaim","abstention","correct_scope_rejection","incorrect_scope_rejection"))==size


def test_missing_pair_is_excluded_from_both_metrics_and_business_denominators(tmp_path,monkeypatch):
    service=ReceiptService(Store(tmp_path/"paired.sqlite3"))
    original=service.engine.cache.load
    def missing(line,stage):
        if line.id=="pilot:20" and stage=="D":
            return {"stage":stage,"available":False,"error":"Test: missing cached response"}
        return original(line,stage)
    monkeypatch.setattr(service.engine.cache,"load",missing)
    comparison=matched_evaluation(service.catalog,service.engine)
    sample=comparison["samples"]["original30"]
    assert sample["cohort"]["matched_count"]==29 and sample["cohort"]["excluded_count"]==1
    assert sample["methods"]["ONE_SHOT"]["incorrect_category"]==0
    assert sample["methods"]["TWO_STAGE"]["abstention"]==7
    for policy in PRIMARY_POLICIES:
        report=service.report(MERCHANT_ID,policy)
        assert report["line_count"]==29 and report["mode"]=="weekly"
        assert "pilot:20" not in {r["line_id"] for r in report["lines"]}
        assert report["comparison"]["cohort"]["excluded_count"]==1
        assert report["totals"]["sales_value_cents"]==sum(r["value_cents"] for r in report["lines"] if r["record_type"]=="sale")
        assert all(r["quantity"]==service.assumptions["items"][r["line_id"]]["weekly_quantity"] for r in report["lines"])


def test_changed_prompt_is_not_used_as_a_matched_cache(tmp_path,monkeypatch):
    catalog=Catalog()
    cache=CachedResponses(catalog)
    original=cache.path
    line=catalog.line("pilot:01")
    record=json.loads(original(line,"D").read_text(encoding="utf-8"))
    record["request"]["questions"]["classification"]["instructions"]+=" Changed configuration."
    altered=tmp_path/"altered.json"
    altered.write_text(json.dumps(record),encoding="utf-8")
    monkeypatch.setattr(cache,"path",lambda item,stage:altered if item.id==line.id and stage=="D" else original(item,stage))
    assert not cache.load(line,"D")["available"]
    assert DecisionEngine(catalog,cache).matched_cohort([line.id])["matched_count"]==0


@pytest.mark.parametrize("policy",PRIMARY_POLICIES)
def test_review_queue_and_values_use_selected_method_and_clear_confirmed_mapping(tmp_path,policy):
    service=ReceiptService(Store(tmp_path/f"{policy}.sqlite3"))
    before=service.report(MERCHANT_ID,policy,"all")
    assert before["line_count"]==54 and before["comparison"]["cohort"]["matched_count"]==54
    assert before["review_policy"]["policy"]==policy
    expected={r["line_id"] for r in before["lines"] if r["record_type"]=="sale" and r["review_required"]}
    assert {r["line_id"] for r in before["review_queue"]}==expected
    assert all(r["outcome"] in ("parent_only","unidentifiable") for r in before["review_queue"])
    service.set_override("pilot:24",MERCHANT_ID,policy,"dairy_eggs.yogurt_quark","Exact-line review")
    after=service.report(MERCHANT_ID,policy,"all")
    assert "pilot:24" not in {r["line_id"] for r in after["review_queue"]}
    assert before["totals"]["net_receipt_value_cents"]==after["totals"]["net_receipt_value_cents"]
    # Evaluation is model-only and must ignore operational feedback.
    assert matched_evaluation(service.catalog,service.engine)["samples"]["original30"]["methods"][policy]["correct_parent"]==4
    line_id=service.memory.db.add_receipt(MERCHANT_ID,"ERDBEER JOGHURT NM 150 G",79,"supermarket","demo-pos",None)
    line,context=service.input(line_id,MERCHANT_ID)
    service.memory.review(line,MERCHANT_ID,context,"SYN-104","confirm",True,"Checked catalog",service.decision(line_id,MERCHANT_ID,policy).model_dump())
    repeated=service.memory.db.add_receipt(MERCHANT_ID,line.raw_text,79,"supermarket","demo-pos",None)
    result=service.decision(repeated,MERCHANT_ID,policy)
    assert result.product_memory["model_stage_bypassed"] and not result.review_required
    assert result.node_id=="dairy_eggs.yogurt_quark" and result.assessments==[]
