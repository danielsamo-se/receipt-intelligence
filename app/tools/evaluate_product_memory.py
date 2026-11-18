"""Small reproducible offline product-memory check. No Jev client or live inference."""
import argparse
import hashlib
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "app/backend"))
from receipt_intelligence.embeddings import embeddings
from receipt_intelligence.service import MERCHANT_ID, ReceiptService
from receipt_intelligence.storage import Store


def category_result(decision, truth, catalog):
    if decision.node_id is None:
        return "abstention" # Never a classification success, even if the truth is unknown.
    if truth is None:
        return "unsupported"
    if decision.node_id == truth:
        return "correct_leaf" if decision.specificity=="leaf" else "correct_parent"
    if truth in catalog.nodes and catalog.nodes[truth]["level"]=="parent" and decision.parent_id==truth:
        return "overclaim"
    if decision.specificity=="parent" and catalog.parent_of(truth)==decision.node_id:
        return "correct_parent"
    return "incorrect"


def run(output: Path):
    source=ROOT / "app/data/product_memory_evaluation_cases.json"
    specification=json.loads(source.read_text(encoding="utf-8"))
    embeddings.vector("Produktbeschreibung","query")
    if not embeddings.status()["available"]:
        raise RuntimeError("Evaluation requires actual local semantic embeddings: "+str(embeddings.status()["error"]))
    artifacts=ROOT / "app/.artifacts"
    artifacts.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="memory-evaluation-",dir=artifacts) as temporary:
        service=ReceiptService(Store(Path(temporary)/"evaluation.sqlite3"))
        rows=[]
        for case in specification["cases"]:
            line_id=service.memory.db.add_receipt(MERCHANT_ID,case["raw_text"],case["price_cents"],"supermarket","demo-pos",case.get("identifier"))
            started=time.perf_counter()
            baseline=service.model_decision(line_id,MERCHANT_ID,"SAFE")
            model_latency=time.perf_counter()-started
            started=time.perf_counter()
            before=service.decision(line_id,MERCHANT_ID,"SAFE")
            retrieval_latency=time.perf_counter()-started
            candidates=before.product_memory["candidates"]
            top=candidates[0]["product"]["product_id"] if candidates else None
            candidate=next((c for c in candidates if c["product"]["product_id"]==case["product_id"] and c["eligible_for_confirmation"]),None)
            simulated_acceptance=False
            if candidate and not before.product_memory["match"]:
                line,context=service.input(line_id,MERCHANT_ID)
                service.memory.review(line,MERCHANT_ID,context,case["product_id"],"confirm",True,
                    "SCRIPTED ORACLE REVIEW: stipulated synthetic catalog identity",before.model_dump())
                simulated_acceptance=True
            started=time.perf_counter()
            after=service.decision(line_id,MERCHANT_ID,"SAFE")
            repeat_latency=time.perf_counter()-started
            def result(d):
                match=d.product_memory["match"] if d.product_memory else None
                return {"node_id":d.node_id,"specificity":d.specificity,"review_required":d.review_required,
                        "cache_available":bool(d.assessments and all(a["available"] for a in d.assessments)),
                        "category_result":category_result(d,case["category"],service.catalog),
                        "matched_product_id":match["product"]["product_id"] if match else None,
                        "match_method":match["method"] if match else None,
                        "jev_stage_bypassed":bool(d.product_memory and d.product_memory["model_stage_bypassed"])}
            rows.append({"id":case["id"],"group":case["group"],"raw_text":case["raw_text"],
                "expected_product":case["product_id"],"expected_category":case["category"],
                "model_only":result(baseline),"memory_before_review":result(before),"memory_after_scripted_review":result(after),
                "top_suggestion":top,"candidate_products":[{"id":c["product"]["product_id"],"lexical":c["lexical_score"],
                    "semantic_cosine":c["semantic_cosine"],"eligible":c["eligible_for_confirmation"],"blocked_reasons":c["blocked_reasons"]} for c in candidates],
                "scripted_accepted_suggestion":simulated_acceptance,
                "latency_seconds":{"model_only_cache":model_latency,"memory_first":retrieval_latency,"memory_repeat":repeat_latency}})
        def summary(method):
            items=[r[method] for r in rows]
            return {"receipts":len(items),"exact_product_matches":sum(bool(r["matched_product_id"]) for r in items),
                "incorrect_product_matches":sum(bool(r[method]["matched_product_id"]) and r[method]["matched_product_id"]!=r["expected_product"] for r in rows),
                "correct_leaf":sum(r["category_result"]=="correct_leaf" for r in items),
                "correct_parent":sum(r["category_result"]=="correct_parent" for r in items),
                "incorrect_or_unsupported":sum(r["category_result"] in ("incorrect","unsupported","overclaim") for r in items),
                "overclaims":sum(r["category_result"]=="overclaim" for r in items),
                "abstentions":sum(r["category_result"]=="abstention" for r in items),
                "review_required":sum(r["review_required"] for r in items),
                "jev_stage_bypasses":sum(r["jev_stage_bypassed"] for r in items),
                "actual_model_calls":0,"actual_model_calls_avoided":0}
        report={"notice":specification["notice"],"protocol":specification["protocol"],"policy":"SAFE at frozen 0.85 per stage",
            "source_sha256":{name:hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                ("app/data/product_memory_evaluation_cases.json","app/data/product_memory_catalog.json","app/data/embedding_model.json")},
            "embedding":embeddings.status(),"retrieval":{"lexical_weight":.6,"semantic_weight":.4,"top_k":3,
                "automatic_similarity_reuse":False},
            "summary":{method:summary(method) for method in ("model_only","memory_before_review","memory_after_scripted_review")},
            "scripted_accepted_suggestions":sum(r["scripted_accepted_suggestion"] for r in rows),
            "actual_human_accepted_suggestions":0,
            "existing_jev_cache_inputs":sum(bool(r["model_only"]["cache_available"]) for r in rows),
            "unseen_inputs_without_jev_cache":sum(not r["model_only"]["cache_available"] for r in rows),
            "known_identity_top3_recall":{"eligible_retrieved":sum(r["scripted_accepted_suggestion"] for r in rows if r["group"]=="new_alias"),
                "labeled_new_aliases":sum(r["group"]=="new_alias" for r in rows)},
            "median_local_latency_seconds":{key:statistics.median(r["latency_seconds"][key] for r in rows) for key in
                ("model_only_cache","memory_first","memory_repeat")},
            "cost":{"jev_api_cost":0,"embedding_api_cost":0,"local_cpu_cost":None},
            "limitations":["Small synthetic development check; no production accuracy, acceptance-rate or cost-saving claim.",
                "Only six cases have existing real Jev cache responses. The other model-only results are unavailable, not invented predictions.",
                "Scripted review uses stipulated labels, not a human study; post-review gains demonstrate persistence and reuse, not autonomous matching.",
                "Jev-stage bypasses would avoid fallback inference in a future live integration. Both current pipelines make zero model calls, so actual avoided calls are zero.",
                "Cosine and lexical scores are retrieval scores, not identity probabilities. Attribute guards are intentionally conservative and incomplete."],
            "cases":rows}
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({k:report[k] for k in ("summary","scripted_accepted_suggestions","existing_jev_cache_inputs","unseen_inputs_without_jev_cache","median_local_latency_seconds")},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=ROOT / "app/data/product_memory_evaluation_results.json")
    run(parser.parse_args().output)
