"""Frozen 30-line exploratory pilot: collect remaining calls, then evaluate offline."""

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import shutil
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import requests
import yaml
from dotenv import dotenv_values
from requests.adapters import HTTPAdapter

BASE = Path(__file__).resolve().parent
OUT = BASE / "results/taxonomy-v2/pilot-30"
OLD = BASE / "results/taxonomy-v2/diagnostic-six"
THRESHOLDS = (0.50, 0.70, 0.85, 0.95, 0.99)
SOURCES = ("taxonomy.yaml", "data/lines.csv", "diagnostic_jev.py", "pilot_jev.py")
PROTOCOL = {
    "thresholds": list(THRESHOLDS), "comparison": "probability >= threshold",
    "A": "Force argmax of 27 raw FLAT leaf probabilities; ignore specials; never renormalize; ties use frozen taxonomy order. Not a separately prompted forced-leaf model.",
    "B": "Respect FLAT selected option. unidentifiable abstains; out_of_scope rejects only above threshold; selected leaf commits only above threshold.",
    "C1": "Sum raw FLAT leaf probabilities per parent, preserving special-option mass. Choose argmax among parent sums and specials. For a qualifying parent return its highest-probability leaf if that raw leaf probability also qualifies, otherwise the parent. unidentifiable abstains; out_of_scope is separate rejection. No renormalization.",
    "C2": "Respect TOPDOWN parent choice. unidentifiable abstains; out_of_scope rejects only above threshold. A parent below threshold abstains. Otherwise unspecified_child retains parent; selected child qualifies on its conditional probability or falls back to parent. No joint probability is inferred.",
    "specials": "unidentifiable is abstention; out_of_scope is separate scope rejection; unspecified_child retains a committed parent, including an erroneous parent on insufficient-information cases.",
    "metrics": "Correct leaves and parents separate. Matching-parent child on parent-only truth is overclaim. All taxonomy commitments on insufficient or out-of-scope truth are errors. Scope rejection correctness separate; abstentions never count as correct classification.",
    "coverage": "Taxonomy parent/leaf commitments divided by 30, including errors and overclaims. Scope rejections excluded and reported separately.",
    "accuracy": "(correct_leaf + correct_parent) / taxonomy commitments; does not imply equal specificity. Error rate includes wrong taxonomy decisions and overclaims. Undefined for zero denominator.",
    "score_audit": "Raw-choice errors with any returned selected probability or confidence >=0.90 are flagged with score type. Conditional child confidence alone is not joint evidence. Forced-policy A errors are not labeled confident model mistakes.",
    "tuning": "Thresholds and policies frozen before the 24 remaining lines; no best-threshold selection or prompt changes.",
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module_from(path):
    spec = importlib.util.spec_from_file_location("frozen_jev_diagnostic", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_rows():
    with (BASE / "data/lines.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 30 or [r["id"] for r in rows] != [f"{i:02}" for i in range(1, 31)]:
        raise ValueError("Expected the existing 30 ordered receipt IDs.")
    return rows


def freeze():
    if (OUT / "freeze_manifest.json").exists():
        verify_freeze()
        print("Existing freeze verified; nothing changed.")
        return
    original = read(OLD / "manifest.json")
    for name, expected in original["input_sha256"].items():
        if digest(BASE / name) != expected:
            raise ValueError(f"Existing diagnostic source changed: {name}")
    taxonomy = yaml.safe_load((BASE / "taxonomy.yaml").read_text(encoding="utf-8-sig"))
    module = module_from(BASE / "diagnostic_jev.py")
    prompts = {"flat": module.question(taxonomy, "flat"), "parent": module.question(taxonomy, "parent"),
               "children": {p: module.question(taxonomy, "child", p) for p in taxonomy["parents"]}}
    frozen = OUT / "frozen"
    frozen.mkdir(parents=True, exist_ok=True)
    for name in SOURCES:
        target = frozen / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BASE / name, target)
    write(frozen / "prompts.json", prompts)
    write(frozen / "evaluation_protocol.json", PROTOCOL)
    (OUT / "calls").mkdir(exist_ok=True)
    cached = sorted((OLD / "calls").glob("*.json"))
    if len(cached) != 16:
        raise ValueError("Expected 16 diagnostic cache records.")
    for path in cached:
        target = OUT / "calls" / path.name
        if target.exists() and digest(target) != digest(path):
            raise ValueError("Conflicting pilot cache; refusing to overwrite.")
        shutil.copy2(path, target)
    protected = [p for folder in (BASE / "results/taxonomy-v1", OLD)
                 for p in folder.rglob("*") if p.is_file()]
    manifest = {
        "taxonomy_version": "2.0", "model": module.MODEL, "endpoint": module.ENDPOINT,
        "source_sha256": {name: digest(BASE / name) for name in SOURCES},
        "frozen_sha256": {p.relative_to(OUT).as_posix(): digest(p) for p in frozen.rglob("*") if p.is_file()},
        "protected_history_sha256": {p.relative_to(BASE).as_posix(): digest(p) for p in protected},
        "reused_call_sha256": {p.name: digest(p) for p in cached},
        "existing_ids": original["line_ids"],
        "remaining_ids": [r["id"] for r in source_rows() if r["id"] not in original["line_ids"]],
        "maximum_new_requests": 72,
        "note": "Prompts, category descriptions, data and decision policies frozen before remaining calls.",
    }
    write(OUT / "freeze_manifest.json", manifest)
    verify_freeze()
    print("Frozen taxonomy, data, prompts and evaluation policies; 16 exact cache files reused; no API calls.")


def verify_freeze():
    manifest = read(OUT / "freeze_manifest.json")
    for name, expected in manifest["source_sha256"].items():
        if digest(BASE / name) != expected:
            raise ValueError(f"Frozen source changed: {name}")
    for name, expected in manifest["frozen_sha256"].items():
        if digest(OUT / name) != expected:
            raise ValueError(f"Frozen snapshot changed: {name}")
    for name, expected in manifest["protected_history_sha256"].items():
        if digest(BASE / name) != expected:
            raise ValueError(f"Protected historical artifact changed: {name}")
    for name, expected in manifest["reused_call_sha256"].items():
        if digest(OUT / "calls" / name) != expected:
            raise ValueError(f"Reused cache changed: {name}")
    return manifest


def collect():
    manifest = verify_freeze()
    taxonomy = yaml.safe_load((OUT / "frozen/taxonomy.yaml").read_text(encoding="utf-8-sig"))
    prompts = read(OUT / "frozen/prompts.json")
    module = module_from(OUT / "frozen/diagnostic_jev.py")
    module.OUTPUT = OUT
    module.KEY = (dotenv_values(BASE / ".env", encoding="utf-8-sig", interpolate=False).get("OPENROUTER_API_KEY") or "").strip()
    if not module.KEY:
        raise ValueError("OPENROUTER_API_KEY missing from .env.")
    new_requests = 0
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=0))
        for row in source_rows():
            client = module.CachedCalls(session)
            price = Decimal(row["price"])
            if not price.is_finite():
                raise ValueError("Nonfinite receipt price.")
            state = {"raw_text": row["raw_text"], "price": float(price), "merchant_type": row["merchant_type"]}
            def ask(stage, specification):
                if row["id"] not in manifest["remaining_ids"] and not (OUT / "calls" / f"{row['id']}_{stage}.json").exists():
                    raise ValueError("Original six may only use their existing cache.")
                return client.ask(row["id"], stage, state, specification)
            ask("flat", prompts["flat"])
            parent = ask("parent", prompts["parent"])
            choice = module.answer(parent)["choice"]
            if choice in taxonomy["parents"]:
                ask("child", prompts["children"][choice])
            new_requests += client.new_requests
            if new_requests > manifest["maximum_new_requests"]:
                raise ValueError("Remaining-line request cap exceeded.")
    write(OUT / "collection_summary.json", {
        "new_requests_this_execution": new_requests,
        "original_cache_records_reused": len(manifest["reused_call_sha256"]),
        "unique_cached_requests": len(list((OUT / "calls").glob("*.json"))),
        "remaining_ids": manifest["remaining_ids"],
    })
    verify_freeze()
    print("Collection complete; " + str(new_requests) + " new requests; no prompt/data changes.")


def result(record):
    return record["response"]["answers"]["classification"]


def load_calls(row, taxonomy):
    records = {}
    for stage in ("flat", "parent"):
        records[stage] = read(OUT / "calls" / f"{row['id']}_{stage}.json")
    parent = result(records["parent"])["choice"]
    if parent in taxonomy["parents"]:
        records["child"] = read(OUT / "calls" / f"{row['id']}_child.json")
    for record in records.values():
        if record["status"] != "complete" or record["http_status"] != 200:
            raise ValueError("Cannot evaluate an unsuccessful call.")
        answer = result(record)
        probabilities = answer.get("probabilities")
        options = record["request"]["questions"]["classification"]["criteria"]
        if not isinstance(probabilities, dict) or set(probabilities) != set(options):
            raise ValueError("Required probabilities missing; no values will be invented.")
        if any(not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in probabilities.values()):
            raise ValueError("Invalid returned probability.")
        if not math.isclose(sum(probabilities.values()), 1, abs_tol=1e-6):
            raise ValueError("Probability mass is not normalized; refusing to silently rescale.")
    return records


def decision(prediction, reason, **scores):
    return {"prediction": prediction, "reason": reason, **scores}


def policy(method, threshold, calls, taxonomy):
    parents = taxonomy["parents"]
    leaves = [f"{p}.{leaf}" for p, node in parents.items() for leaf in node["leaves"]]
    flat = result(calls["flat"])
    probabilities = flat["probabilities"]
    if method == "A":
        leaf = max(leaves, key=lambda x: probabilities[x])
        ties = sum(probabilities[x] == probabilities[leaf] for x in leaves)
        return decision(leaf, "forced_leaf_argmax", score=probabilities[leaf], tie_count=ties)
    if method == "B":
        choice = flat["choice"]
        score = probabilities[choice]
        if choice == "unidentifiable":
            return decision(None, "explicit_unidentifiable", score=score)
        return decision(choice if score >= threshold else None,
                        "flat_choice" if score >= threshold else "below_threshold", score=score)
    if method == "C1":
        groups = {p: sum(probabilities[f"{p}.{leaf}"] for leaf in node["leaves"])
                  for p, node in parents.items()}
        groups.update({x: probabilities[x] for x in ("unidentifiable", "out_of_scope")})
        choice = max(groups, key=groups.get)
        score = groups[choice]
        if choice == "unidentifiable":
            return decision(None, "explicit_unidentifiable", parent_score=score)
        if score < threshold:
            return decision(None, "parent_or_scope_below_threshold", parent_score=score)
        if choice == "out_of_scope":
            return decision(choice, "scope_rejection", parent_score=score)
        candidates = [f"{choice}.{leaf}" for leaf in parents[choice]["leaves"]]
        leaf = max(candidates, key=lambda x: probabilities[x])
        if probabilities[leaf] >= threshold:
            return decision(leaf, "aggregated_parent_and_leaf_supported", parent_score=score, leaf_score=probabilities[leaf])
        return decision(choice, "aggregated_parent_only", parent_score=score, leaf_score=probabilities[leaf])
    if method == "C2":
        top = result(calls["parent"])
        choice = top["choice"]
        score = top["probabilities"][choice]
        if choice == "unidentifiable":
            return decision(None, "explicit_unidentifiable", parent_score=score)
        if score < threshold:
            return decision(None, "parent_or_scope_below_threshold", parent_score=score)
        if choice == "out_of_scope":
            return decision(choice, "scope_rejection", parent_score=score)
        child = result(calls["child"])
        leaf = child["choice"]
        child_score = child["probabilities"][leaf]
        if leaf == "unspecified_child":
            return decision(choice, "explicit_unspecified_child", parent_score=score, conditional_child_score=child_score)
        if child_score >= threshold:
            return decision(leaf, "parent_and_conditional_child_supported", parent_score=score, conditional_child_score=child_score)
        return decision(choice, "conditional_child_below_threshold", parent_score=score, conditional_child_score=child_score)
    raise ValueError("Unknown comparison method.")


def outcome(truth, prediction):
    if prediction is None:
        return "abstention"
    if prediction == "out_of_scope":
        return "correct_scope_rejection" if truth == "OUT_OF_SCOPE" else "incorrect_scope_rejection"
    if truth in ("INSUFFICIENT_INFORMATION", "OUT_OF_SCOPE"):
        return "incorrect_category"
    if truth.startswith("PARENT_ONLY:"):
        parent = truth.split(":", 1)[1]
        if prediction == parent:
            return "correct_parent"
        return "overclaim" if prediction.startswith(parent + ".") else "incorrect_category"
    if truth == prediction:
        return "correct_leaf"
    return "correct_parent" if prediction == truth.split(".")[0] else "incorrect_category"


def metrics(decisions, taxonomy):
    counts = Counter(d["outcome"] for d in decisions)
    leaf_commits = sum(d["prediction"] is not None and "." in d["prediction"] for d in decisions)
    parent_commits = sum(d["prediction"] in taxonomy["parents"] for d in decisions)
    commitments = leaf_commits + parent_commits
    errors = counts["incorrect_category"] + counts["overclaim"]
    scope = counts["correct_scope_rejection"] + counts["incorrect_scope_rejection"]
    correct = counts["correct_leaf"] + counts["correct_parent"]
    merchandise = sum(d["prediction"] is not None and d["prediction"] != "out_of_scope"
                      and d["prediction"].split(".")[0] != "adjustments" for d in decisions)
    return {
        **{key: counts[key] for key in ("correct_leaf", "correct_parent", "incorrect_category", "overclaim", "correct_scope_rejection", "incorrect_scope_rejection", "abstention")},
        "taxonomy_commitments": commitments, "leaf_commitments": leaf_commits, "parent_commitments": parent_commits,
        "merchandise_commitments": merchandise, "adjustment_commitments": commitments - merchandise,
        "taxonomy_coverage": commitments / len(decisions),
        "scope_rejection_coverage": scope / len(decisions),
        "classification_accuracy": correct / commitments if commitments else None,
        "classification_error_rate": errors / commitments if commitments else None,
        "overall_nonabstaining_error_rate": (errors + counts["incorrect_scope_rejection"]) / (commitments + scope) if commitments + scope else None,
        "leaf_commit_share": leaf_commits / commitments if commitments else None,
        "insufficient_taxonomy_commits": sum(d["ground_truth"] == "INSUFFICIENT_INFORMATION" and d["prediction"] not in (None, "out_of_scope") for d in decisions),
        "parent_only_overclaims": counts["overclaim"],
    }


def usage_summary(records):
    result = {"requests": len(records), "latency_sum_seconds": sum(r["latency_seconds"] for r in records)}
    latencies = sorted(r["latency_seconds"] for r in records)
    result["latency_median_seconds"] = (latencies[(len(latencies)-1)//2] + latencies[len(latencies)//2]) / 2 if latencies else None
    for field in ("input_tokens", "output_tokens", "cost"):
        values = [(r["response"].get("usage") or {}).get(field) for r in records]
        known = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
        result[field] = {"available_sum": sum(known) if known else None, "missing_requests": len(values) - len(known)}
    return result


def evaluate():
    verify_freeze()
    taxonomy = yaml.safe_load((OUT / "frozen/taxonomy.yaml").read_text(encoding="utf-8-sig"))
    rows = source_rows()
    calls = {row["id"]: load_calls(row, taxonomy) for row in rows}
    all_decisions, summaries = [], []
    for method in ("A", "B", "C1", "C2"):
        for threshold in ((None,) if method == "A" else THRESHOLDS):
            decisions = []
            for row in rows:
                d = policy(method, threshold, calls[row["id"]], taxonomy)
                d.update(id=row["id"], raw_text=row["raw_text"], ground_truth=row["ground_truth_label"], method=method, threshold=threshold)
                d["outcome"] = outcome(d["ground_truth"], d["prediction"])
                decisions.append(d)
            summaries.append({"method": method, "threshold": threshold, **metrics(decisions, taxonomy)})
            all_decisions.extend(decisions)
    write(OUT / "offline_decisions.json", all_decisions)
    write(OUT / "threshold_summary.json", summaries)
    derived, audit = {}, []
    for row in rows:
        rcalls = calls[row["id"]]
        flat = result(rcalls["flat"])
        derived[row["id"]] = {p: sum(flat["probabilities"][f"{p}.{leaf}"] for leaf in node["leaves"])
                              for p, node in taxonomy["parents"].items()}
        derived[row["id"]].update({name: flat["probabilities"][name] for name in ("unidentifiable", "out_of_scope")})
        for method in ("B", "C2"):
            d = policy(method, 0.0, rcalls, taxonomy)
            verdict = outcome(row["ground_truth_label"], d["prediction"])
            selected_records = [rcalls["flat"]] if method == "B" else [rcalls[k] for k in ("parent", "child") if k in rcalls]
            raw_scores = [{"stage": r["stage"], "choice": result(r)["choice"],
                           "probability": result(r)["probabilities"][result(r)["choice"]],
                           "confidence": result(r).get("confidence")} for r in selected_records]
            audit.append({"id": row["id"], "raw_text": row["raw_text"], "method": method,
                          "ground_truth": row["ground_truth_label"], **d, "outcome": verdict,
                          "raw_scores": raw_scores,
                          "high_score_error": verdict in ("incorrect_category", "overclaim", "incorrect_scope_rejection")
                          and any(s["probability"] >= .9 or (s["confidence"] is not None and s["confidence"] >= .9) for s in raw_scores)})
    write(OUT / "derived_parent_probabilities.json", {"derived_from_flat_without_renormalization": derived})
    write(OUT / "raw_choice_audit.json", audit)
    flat_records = [rcalls["flat"] for rcalls in calls.values()]
    top_records = [rcalls[k] for rcalls in calls.values() for k in ("parent", "child") if k in rcalls]
    usage = {"FLAT": usage_summary(flat_records), "TOPDOWN": usage_summary(top_records),
             "collection": read(OUT / "collection_summary.json"),
             "returned_models": sorted({r["response"]["model"] for r in flat_records + top_records})}
    write(OUT / "usage_summary.json", usage)
    report = render_report(summaries, all_decisions, rows, audit, derived, usage)
    (OUT / "comparison_report.md").write_text(report, encoding="utf-8")
    verify_freeze()
    print(report)


def render_report(summaries, decisions, rows, audit, derived, usage):
    lines = ["# Jev taxonomy-v2 exploratory 30-line pilot", "",
             "Frozen taxonomy, descriptions, prompts and evaluation policies. Six prior diagnostic receipts reused exact cached calls; only the remaining 24 received new requests. No v1 results used.", "",
             "## Policies and denominators", ""]
    lines.extend(f"- **{name}:** {PROTOCOL[name]}" for name in ("A", "B", "C1", "C2", "specials", "coverage", "accuracy"))
    lines += ["", "C2 uses separate parent and conditional-child thresholds, not a calibrated joint probability. Equal numerical thresholds across C1/C2 do not imply equal confidence. Model confidence is recorded but not used as a probability threshold.", "",
              "## Actual counts across all 30 receipts", "",
              "Errors below are wrong taxonomy commitments plus overclaims. Scope correctness/errors are separate. Correct leaves and parents must remain separate when comparing specificity.", "",
              "| Method | t | Correct leaf | Correct parent | Taxonomy errors | Overclaims within errors | Leaf/parent commits | Abstain | Scope correct/wrong | Taxonomy coverage | Classification accuracy |",
              "| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: |"]
    for s in summaries:
        pct = lambda x: "undefined" if x is None else f"{100*x:.1f}%"
        lines.append(f"| {s['method']} | {s['threshold'] if s['threshold'] is not None else 'forced'} | {s['correct_leaf']} | {s['correct_parent']} | {s['incorrect_category']+s['overclaim']} | {s['overclaim']} | {s['leaf_commitments']}/{s['parent_commitments']} | {s['abstention']} | {s['correct_scope_rejection']}/{s['incorrect_scope_rejection']} | {pct(s['taxonomy_coverage'])} | {pct(s['classification_accuracy'])} |")
    lines += ["", "Machine-readable threshold_summary.json also records classification and non-abstaining error rates, leaf-commit share, merchandise/adjustment commitments, and false commitments on insufficient-information rows.", "",
              "## Parent-only, insufficient-information and out-of-scope cases", "",
              "These raw choices are shown without a threshold, exposing explicit model abstention/parent retention before threshold effects.", "",
              "| ID / receipt | Ground truth | FLAT raw choice (p) | TOPDOWN raw result (parent p; child choice/p) | FLAT parent mass / unidentifiable mass |",
              "| --- | --- | --- | --- | --- |"]
    for row in rows:
        truth = row["ground_truth_label"]
        if not (truth.startswith("PARENT_ONLY:") or truth in ("INSUFFICIENT_INFORMATION", "OUT_OF_SCOPE")):
            continue
        f = next(a for a in audit if a["id"] == row["id"] and a["method"] == "B")
        t = next(a for a in audit if a["id"] == row["id"] and a["method"] == "C2")
        fs, ps = f["raw_scores"][0], t["raw_scores"][0]
        child = t["raw_scores"][1] if len(t["raw_scores"]) > 1 else None
        child_text = f"{child['choice']}/{child['probability']:.4g}" if child else "not called"
        parent_mass = f"{derived[row['id']][truth.split(':',1)[1]]:.4g}" if truth.startswith("PARENT_ONLY:") else "n/a"
        lines.append(f"| {row['id']} {row['raw_text']} | {truth} | {fs['choice']} ({fs['probability']:.4g}) | {t['prediction'] or 'abstain'} ({ps['probability']:.4g}; {child_text}) | {parent_mass} / {derived[row['id']]['unidentifiable']:.4g} |")
    lines += ["", "## Error and high-score audit", ""]
    errors = [a for a in audit if a["outcome"] in ("incorrect_category", "overclaim", "incorrect_scope_rejection")]
    if errors:
        for a in errors:
            lines.append(f"- {a['id']} {a['raw_text']}, {'FLAT' if a['method']=='B' else 'TOPDOWN'}: {a['prediction']}; truth {a['ground_truth']}; {a['outcome']}; raw scores {json.dumps(a['raw_scores'])}; high-score flag {a['high_score_error']}.")
    else:
        lines.append("No raw-choice taxonomy errors, overclaims or false scope rejections were observed. This is not evidence they cannot occur.")
    forced = [d for d in decisions if d["method"] == "A" and d["outcome"] not in ("correct_leaf", "correct_parent")]
    lines.append(f"A forced {len(forced)} erroneous/overclaim leaf commitments. {sum(d.get('score')==0 for d in forced)} had zero returned probability for the selected leaf; {sum(d.get('tie_count',1)>1 for d in forced)} involved a leaf tie. These are offline policy artifacts, not confident model mistakes. Tie-breaking uses frozen taxonomy order.")
    lines += ["", "## Structural interpretation", "",
              "C1 versus B isolates aggregation/fallback on the same FLAT responses. Parent sums retain original probability mass: unidentifiable/out_of_scope mass is never redistributed among products. High FLAT unidentifiable probability can prevent any parent from qualifying, even when receipt text supports a parent.",
              "C2 asks a different parent question and offers unspecified_child explicitly in a second question. Parent retention may therefore come from a different output space, different probability allocation, or an explicit unspecified_child selection, not FLAT probability aggregation. Conditional child scores can be high inside a weak or incorrect parent; parent thresholds are enforced separately.", ""]
    for threshold in THRESHOLDS:
        b = {d["id"]: d for d in decisions if d["method"]=="B" and d["threshold"]==threshold}
        c1 = [d for d in decisions if d["method"]=="C1" and d["threshold"]==threshold and d["outcome"]=="correct_parent" and b[d["id"]]["outcome"]=="abstention"]
        c2 = [d for d in decisions if d["method"]=="C2" and d["threshold"]==threshold and d["outcome"]=="correct_parent" and b[d["id"]]["outcome"]=="abstention"]
        lines.append(f"- t={threshold}: C1 recovers parent information over B abstention on IDs {[d['id'] for d in c1]}; C2 does so on IDs {[d['id'] for d in c2]}.")
    lines += ["", "## Observed API usage and latency", "",
              "Totals include the six diagnostic receipts once, using their original cached measurements. Threshold replay incurs no model calls. Costs below are returned OpenRouter credits; missing usage is reported explicitly rather than estimated.", "",
              "| Calls | Requests | Input tokens | Output tokens | Cost credits | Sum latency s | Median request latency s |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for method in ("FLAT", "TOPDOWN"):
        u = usage[method]
        value = lambda key: str(u[key]["available_sum"]) + (f" ({u[key]['missing_requests']} missing)" if u[key]["missing_requests"] else "")
        lines.append(f"| {method} | {u['requests']} | {value('input_tokens')} | {value('output_tokens')} | {value('cost')} | {u['latency_sum_seconds']:.3f} | {u['latency_median_seconds']:.3f} |")
    lines += ["", f"Collection: {usage['collection']['new_requests_this_execution']} new requests in the collection execution; 16 original cache records reused. Returned models: {usage['returned_models']}.", "",
              "## Limits", "",
              "This hand-built 30-line pilot has 22 leaf-supported, four parent-only, three insufficient-information and one out-of-scope case. It is neither a random sample nor a held-out test: the first six cases already informed the diagnostic design. Some leaves have no examples. The coconut-milk label remains a proposed culinary interpretation. No prompts, descriptions, labels, thresholds or policies were tuned to the remaining results. No statistical significance, reliable calibration or production accuracy is claimed.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("freeze", "collect", "evaluate"))
    args = parser.parse_args()
    try:
        {"freeze": freeze, "collect": collect, "evaluate": evaluate}[args.action]()
    except Exception as exc:
        # API exception strings from the frozen caller are already sanitized.
        print("Pilot stopped: " + str(exc), flush=True)
        raise SystemExit(1)
