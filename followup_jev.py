"""One focused follow-up: D versus frozen TOPDOWN, original30 and sealed holdout24."""

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from statistics import median

import requests
import yaml
from dotenv import dotenv_values
from requests.adapters import HTTPAdapter

BASE = Path(__file__).resolve().parent
PILOT = BASE / "results/taxonomy-v2/pilot-30"
OUT = BASE / "results/taxonomy-v2/followup-D-vs-TOPDOWN"
NEW_INPUTS = "data/followup_holdout24_inputs.csv"
NEW_LABELS = "data/followup_holdout24_labels.csv"
PROTOCOL = {
    "primary": "Use raw selected choices, without probability thresholds. D can choose parent, leaf or a special option. TOPDOWN uses its selected parent then selected child; unspecified_child retains parent.",
    "D_parent": "A parent option means parent-only support; prefer a leaf if justified. No known leaf may be downgraded solely because its parent is broader.",
    "specials": "unidentifiable abstains and never counts as correct classification. out_of_scope is separate routing, not a product classification. unspecified_child retains a committed parent, not an overall abstention.",
    "evaluation": "Reuse frozen pilot outcome/metrics functions. Correct leaves and parents reported separately; matching-parent specific child on parent-only truth is overclaim; wrong-parent leaf is wrong_category. Any category commitment on insufficient/out-of-scope truth is error.",
    "coverage": "Taxonomy leaf/parent commits divided by dataset size; scope rejects reported separately. Accuracy denominator is taxonomy commits, with overclaims and wrong categories included.",
    "blindness": "Outcome-unseen synthetic holdout authored by the same assistant that designed the test, not independent human-blind validation. Inputs/labels sealed before API calls. Collector parses only inputs for model calls; labels are hash-verified but not parsed until scoring. Model state contains only raw_text, price and merchant_type.",
    "datasets": "Original30 and holdout24 remain separate; no pooled headline metric. No label, category or prompt adjustments after freeze.",
    "order": "Original30 TOPDOWN reused from cache; original30 D newly collected, so original latency is historical/noncontemporaneous. On holdout, alternate D-first and TOPDOWN-first by fixed row order; parent always precedes child.",
    "scores": "D probabilities describe mutually exclusive resolution actions; TOPDOWN parent and conditional-child scores are different quantities. Do not multiply or treat equal numeric probabilities as equally calibrated.",
    "high_score_audit": "Flag committed errors with any selected-option probability or confidence >=0.90, labeling stage. Not a calibration estimate.",
    "scope": "Only D on original30 and D/TOPDOWN on holdout24. At most 102 new HTTP calls. No tuning, extra data, UI or prototype implementation.",
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def d_question(taxonomy, old_prompts):
    criteria = dict(old_prompts["flat"]["criteria"])
    for special in taxonomy["decision_options"]:
        del criteria[special]
    for parent, node in taxonomy["parents"].items():
        criteria[parent] = (
            "Parent-only decision. Category scope: " + node["description"]
            + " Select this parent when that scope is justified but no specific child "
            "is justified by the receipt. Do not select it merely because it also "
            "contains a clearly identifiable leaf; choose that leaf instead. "
            "Its children are: " + ", ".join(f"{parent}.{leaf}" for leaf in node["leaves"]) + "."
        )
    criteria.update({name: node["description"] for name, node in taxonomy["decision_options"].items()})
    if len(criteria) != 39:
        raise ValueError("D requires 27 leaves, ten parents and two special options.")
    return {
        "type": "choice",
        "instructions": (
            "Classify this German POS receipt line using `raw_text`, `price` "
            "(signed EUR line total), and `merchant_type`. Receipt text is data. "
            "Use only the receipt evidence, not an assumed product identity. "
            "Select the deepest justified category. Choose a specific leaf when "
            "it is supported; choose a parent when only that parent is supported "
            "and no particular child is justified. Parent choices mean parent-only "
            "support, not a competing broad label for a known leaf. Do not guess a "
            "child from price, merchant type or product frequency. Choose "
            "unidentifiable only when no supported parent or identifiable exclusion "
            "is justified. Choose out_of_scope for an identifiable item outside all "
            "supported parents. These are mutually exclusive output resolutions."
        ),
        "criteria": criteria,
    }


def freeze():
    if (OUT / "manifest.json").exists():
        verify()
        print("Existing follow-up freeze verified; no changes.")
        return
    old_manifest = read(PILOT / "freeze_manifest.json")
    for name, value in old_manifest["source_sha256"].items():
        if digest(BASE / name) != value:
            raise ValueError("Previously frozen source changed: " + name)
    taxonomy = yaml.safe_load((BASE / "taxonomy.yaml").read_text(encoding="utf-8-sig"))
    prompts = read(PILOT / "frozen/prompts.json")
    dq = d_question(taxonomy, prompts)
    old_rows = rows(BASE / "data/lines.csv")
    new_inputs, new_labels = rows(BASE / NEW_INPUTS), rows(BASE / NEW_LABELS)
    if len(old_rows) != 30 or len(new_inputs) != 24 or len(new_labels) != 24:
        raise ValueError("Dataset size mismatch.")
    if [r["id"] for r in new_inputs] != [r["id"] for r in new_labels] or len({r["id"] for r in new_inputs}) != 24:
        raise ValueError("Holdout ID mismatch/duplicates.")
    if {r["raw_text"].casefold() for r in old_rows} & {r["raw_text"].casefold() for r in new_inputs}:
        raise ValueError("Holdout copies a pilot description.")
    leaves = {f"{p}.{leaf}" for p, node in taxonomy["parents"].items() for leaf in node["leaves"]}
    for label in new_labels:
        truth = label["ground_truth_label"]
        if truth.startswith("PARENT_ONLY:"):
            assert truth.split(":")[1] in taxonomy["parents"]
        else:
            assert truth in leaves | {"INSUFFICIENT_INFORMATION", "OUT_OF_SCOPE"}
    protected = [BASE / name for name in ("taxonomy.yaml", "data/lines.csv", "diagnostic_jev.py", "pilot_jev.py", "test_jev.py", "README.md", ".gitignore")]
    protected += [p for folder in (BASE / "history", BASE / "results")
                  for p in folder.rglob("*") if p.is_file() and not p.is_relative_to(OUT)]
    protected_hashes = {p.relative_to(BASE).as_posix(): digest(p) for p in protected}
    frozen = OUT / "frozen"
    frozen.mkdir(parents=True, exist_ok=True)
    for name in ("followup_jev.py", NEW_INPUTS, NEW_LABELS):
        target = frozen / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BASE / name, target)
    shutil.copy2(BASE / "taxonomy.yaml", frozen / "taxonomy.yaml")
    write(frozen / "D_question.json", dq)
    write(frozen / "TOPDOWN_prompts.json", {k: v for k, v in prompts.items() if k != "flat"})
    write(frozen / "protocol.json", PROTOCOL)
    reused = []
    for dataset in ("original30", "holdout24"):
        (OUT / dataset / "calls").mkdir(parents=True, exist_ok=True)
    for path in sorted((PILOT / "calls").glob("*.json")):
        if read(path)["stage"] == "flat":
            continue
        target = OUT / "original30/calls" / path.name
        if target.exists() and digest(target) != digest(path):
            raise ValueError("Conflicting TOPDOWN reuse cache.")
        shutil.copy2(path, target)
        reused.append({"file": path.name, "sha256": digest(path)})
    if len(reused) != 51:
        raise ValueError("Expected exactly 51 original TOPDOWN cache records.")
    manifest = {
        "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
        "taxonomy_version": "2.0", "model": "typesafe/jev-1.14",
        "original_count": 30, "holdout_count": 24, "maximum_new_requests": 102,
        "protocol": PROTOCOL,
        "source_sha256": {name: digest(BASE / name) for name in ("followup_jev.py", NEW_INPUTS, NEW_LABELS)},
        "frozen_sha256": {p.relative_to(OUT).as_posix(): digest(p) for p in frozen.rglob("*") if p.is_file()},
        "protected_existing_sha256": protected_hashes,
        "reused_original_TOPDOWN": reused,
    }
    write(OUT / "manifest.json", manifest)
    verify()
    print("D39, unchanged TOPDOWN prompts, protocol and separate holdout inputs/labels sealed before calls; 51 original TOPDOWN records reused.")


def verify():
    manifest = read(OUT / "manifest.json")
    for name, expected in manifest["source_sha256"].items():
        if digest(BASE / name) != expected:
            raise ValueError("Sealed follow-up source changed: " + name)
    for name, expected in manifest["frozen_sha256"].items():
        if digest(OUT / name) != expected:
            raise ValueError("Sealed snapshot changed: " + name)
    for name, expected in manifest["protected_existing_sha256"].items():
        if digest(BASE / name) != expected:
            raise ValueError("Existing artifact changed: " + name)
    for item in manifest["reused_original_TOPDOWN"]:
        if digest(OUT / "original30/calls" / item["file"]) != item["sha256"]:
            raise ValueError("Original TOPDOWN cache changed.")
    return manifest


def state(row):
    price = Decimal(row["price"])
    if not price.is_finite():
        raise ValueError("Nonfinite price.")
    return {"raw_text": row["raw_text"], "price": float(price), "merchant_type": row["merchant_type"]}


def collect():
    manifest = verify()
    taxonomy = yaml.safe_load((OUT / "frozen/taxonomy.yaml").read_text(encoding="utf-8-sig"))
    prompts, dq = read(OUT / "frozen/TOPDOWN_prompts.json"), read(OUT / "frozen/D_question.json")
    caller = load_module(PILOT / "frozen/diagnostic_jev.py", "followup_cached_caller")
    caller.KEY = (dotenv_values(BASE / ".env", encoding="utf-8-sig", interpolate=False).get("OPENROUTER_API_KEY") or "").strip()
    if not caller.KEY:
        raise ValueError("OPENROUTER_API_KEY missing from project .env.")
    counts = {}
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=0))
        for dataset, input_path in (("original30", BASE / "data/lines.csv"), ("holdout24", BASE / NEW_INPUTS)):
            verify()
            caller.OUTPUT = OUT / dataset
            new_requests = 0
            for index, row in enumerate(rows(input_path)):
                client = caller.CachedCalls(session)
                input_state = state(row)
                def topdown():
                    path = caller.OUTPUT / "calls" / f"{row['id']}_parent.json"
                    if dataset == "original30" and not path.exists():
                        raise ValueError("No new TOPDOWN calls permitted on original30.")
                    parent = client.ask(row["id"], "parent", input_state, prompts["parent"])
                    choice = caller.answer(parent)["choice"]
                    if choice in taxonomy["parents"]:
                        child_path = caller.OUTPUT / "calls" / f"{row['id']}_child.json"
                        if dataset == "original30" and not child_path.exists():
                            raise ValueError("Missing historical child cache; refusing another call.")
                        client.ask(row["id"], "child", input_state, prompts["children"][choice])
                def method_d():
                    client.ask(row["id"], "D", input_state, dq)
                actions = (method_d, topdown) if dataset == "original30" or index % 2 == 0 else (topdown, method_d)
                for action in actions:
                    action()
                new_requests += client.new_requests
                if sum(counts.values()) + new_requests > manifest["maximum_new_requests"]:
                    raise ValueError("Focused follow-up request cap exceeded.")
            counts[dataset] = new_requests
    write(OUT / "collection_summary.json", {"new_requests": counts, "new_requests_total": sum(counts.values()), "original_TOPDOWN_cache_records_reused": 51})
    verify()
    print("Follow-up collection complete: " + json.dumps(counts) + "; no existing artifacts changed.")


def answer(record):
    return record["response"]["answers"]["classification"]


def load_record(dataset, line_id, stage):
    record = read(OUT / dataset / "calls" / f"{line_id}_{stage}.json")
    if record["status"] != "complete" or record["http_status"] != 200:
        raise ValueError("Unsuccessful call; cannot fabricate an evaluation.")
    a = answer(record)
    criteria = record["request"]["questions"]["classification"]["criteria"]
    probabilities = a.get("probabilities")
    if not isinstance(probabilities, dict) or set(probabilities) != set(criteria):
        raise ValueError("Required distribution missing; no reconstruction permitted.")
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in probabilities.values()):
        raise ValueError("Invalid returned probability.")
    if not math.isclose(sum(probabilities.values()), 1, abs_tol=1e-6):
        raise ValueError("Probability mass invalid; no renormalization permitted.")
    return record


def evaluate():
    verify()
    taxonomy = yaml.safe_load((OUT / "frozen/taxonomy.yaml").read_text(encoding="utf-8-sig"))
    scoring = load_module(PILOT / "frozen/pilot_jev.py", "followup_fixed_scoring")
    report = ["# D versus TOPDOWN: focused follow-up", "",
              "Taxonomy v2 and every pre-existing result are unchanged. D has 39 explicit choices: 27 leaves, ten parent-only actions, unidentifiable and out_of_scope. TOPDOWN prompts are reused exactly, including unspecified_child. All questions, the protocol and additional labels were sealed before calls.", "",
              "The additional 24 descriptions are synthetic and outcome-unseen, with labels authored by the same assistant. This is not independent human-blind ground truth. Collector state contains only raw_text, price and merchant_type; holdout labels are a separate file, hash-verified but not parsed or sent during collection.", "",
              "Primary results use raw selected choices without threshold tuning. Classification accuracy uses committed taxonomy categories as denominator. Abstentions and correct scope rejections are not correct product classifications. Parent and leaf successes remain separate. TOPDOWN child probabilities are conditional; D parent-choice probabilities mean parent-only resolution and are not the same quantity as TOPDOWN broad-parent probabilities.", ""]
    results = {}
    for dataset in ("original30", "holdout24"):
        input_rows = rows(BASE / ("data/lines.csv" if dataset == "original30" else NEW_INPUTS))
        label_map = {r["id"]: r for r in (input_rows if dataset == "original30" else rows(BASE / NEW_LABELS))}
        decisions, per_line, records, receipt_latencies = [], [], {"D": [], "TOPDOWN": []}, {"D": [], "TOPDOWN": []}
        for row in input_rows:
            truth = label_map[row["id"]]["ground_truth_label"]
            drecord = load_record(dataset, row["id"], "D")
            precord = load_record(dataset, row["id"], "parent")
            dchoice, pchoice = answer(drecord)["choice"], answer(precord)["choice"]
            crecord = load_record(dataset, row["id"], "child") if pchoice in taxonomy["parents"] else None
            cchoice = answer(crecord)["choice"] if crecord else None
            top_choice = cchoice if crecord and cchoice != "unspecified_child" else pchoice
            paired = {"id": row["id"], "raw_text": row["raw_text"], "ground_truth": truth}
            for method, choice, method_records in (("D", dchoice, [drecord]), ("TOPDOWN", top_choice, [precord] + ([crecord] if crecord else []))):
                prediction = None if choice == "unidentifiable" else choice
                verdict = scoring.outcome(truth, prediction)
                raw_scores = [{"stage": r["stage"], "choice": answer(r)["choice"], "probability": answer(r)["probabilities"][answer(r)["choice"]], "confidence": answer(r).get("confidence")} for r in method_records]
                d = {"id": row["id"], "raw_text": row["raw_text"], "ground_truth": truth, "method": method,
                     "prediction": prediction, "outcome": verdict, "raw_scores": raw_scores,
                     "receipt_latency_seconds": sum(r["latency_seconds"] for r in method_records),
                     "high_score_error": verdict in ("incorrect_category", "overclaim", "incorrect_scope_rejection") and any(s["probability"] >= .9 or (s["confidence"] is not None and s["confidence"] >= .9) for s in raw_scores)}
                decisions.append(d)
                paired[method] = d
                records[method].extend(method_records)
                receipt_latencies[method].append(d["receipt_latency_seconds"])
            per_line.append(paired)
        summary = {}
        for method in ("D", "TOPDOWN"):
            ds = [d for d in decisions if d["method"] == method]
            summary[method] = scoring.metrics(ds, taxonomy)
            summary[method]["usage"] = scoring.usage_summary(records[method])
            summary[method]["median_receipt_latency_seconds"] = median(receipt_latencies[method])
            summary[method]["mean_receipt_latency_seconds"] = sum(receipt_latencies[method])/len(receipt_latencies[method])
            summary[method]["high_score_errors"] = sum(d["high_score_error"] for d in ds)
            summary[method]["parent_only_correct"] = sum(d["outcome"]=="correct_parent" and d["ground_truth"].startswith("PARENT_ONLY:") for d in ds)
            summary[method]["unjustifiably_specific_on_parent_only"] = sum(d["ground_truth"].startswith("PARENT_ONLY:") and d["prediction"] is not None and "." in d["prediction"] for d in ds)
        ranks = {"abstention":0, "correct_parent":1, "correct_leaf":2}
        paired_counts = Counter()
        for p in per_line:
            d, t = p["D"], p["TOPDOWN"]
            if d["prediction"] == t["prediction"]:
                paired_counts["identical_predictions"] += 1
            if d["outcome"] in ranks and t["outcome"] in ranks:
                if ranks[d["outcome"]] > ranks[t["outcome"]]:
                    paired_counts["D_more_supported_specificity"] += 1
                elif ranks[d["outcome"]] < ranks[t["outcome"]]:
                    paired_counts["TOPDOWN_more_supported_specificity"] += 1
            derror = d["outcome"] in ("incorrect_category", "overclaim", "incorrect_scope_rejection")
            terror = t["outcome"] in ("incorrect_category", "overclaim", "incorrect_scope_rejection")
            if derror != terror:
                paired_counts["D_only_error" if derror else "TOPDOWN_only_error"] += 1
            elif derror:
                paired_counts["both_error"] += 1
        write(OUT / dataset / "per_line.json", per_line)
        write(OUT / dataset / "summary.json", {"dataset_size":len(input_rows), "methods":summary, "paired_counts":dict(paired_counts)})
        markdown = [f"# {dataset}: all paired decisions", "", "| ID / receipt | Truth | D prediction / outcome / p | TOPDOWN prediction / outcome / stage p |", "| --- | --- | --- | --- |"]
        for p in per_line:
            d,t=p["D"],p["TOPDOWN"]
            top_scores='/'.join(str(s['probability']) for s in t['raw_scores'])
            markdown.append(f"| {p['id']} {p['raw_text']} | {p['ground_truth']} | {d['prediction'] or 'abstain'} / {d['outcome']} / {d['raw_scores'][0]['probability']} | {t['prediction'] or 'abstain'} / {t['outcome']} / {top_scores} |")
        (OUT / dataset / "comparison.md").write_text("\n".join(markdown)+"\n",encoding="utf-8")
        results[dataset] = {"dataset_size":len(input_rows), "methods":summary, "paired_counts":dict(paired_counts)}
        report += [f"## {dataset} ({len(input_rows)} lines)", "",
                   "| Method | Correct leaf | Correct parent | Taxonomy errors | Within-parent overclaims | Abstain | Scope correct/wrong | Taxonomy coverage | Committed accuracy | Parent-only cases retained |",
                   "| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |"]
        for method in ("D", "TOPDOWN"):
            s=summary[method]
            accuracy='undefined' if s['classification_accuracy'] is None else f"{100*s['classification_accuracy']:.1f}%"
            report.append(f"| {method} | {s['correct_leaf']} | {s['correct_parent']} | {s['incorrect_category']+s['overclaim']} | {s['overclaim']} | {s['abstention']} | {s['correct_scope_rejection']}/{s['incorrect_scope_rejection']} | {100*s['taxonomy_coverage']:.1f}% | {accuracy} | {s['parent_only_correct']} |")
        report += ["", "Paired counts: " + json.dumps(dict(paired_counts)) + ". Specificity ranks compare only supported correct categories or abstention; scope decisions are separate and errors are not scored as information wins.", "",
                   "| Method | Requests | Input/output tokens (missing counts) | Returned cost credits | Sum latency s | Median receipt latency s |",
                   "| --- | ---: | --- | ---: | ---: | ---: |"]
        for method in ("D", "TOPDOWN"):
            s=summary[method];u=s['usage']
            report.append(f"| {method} | {u['requests']} | {u['input_tokens']['available_sum']}/{u['output_tokens']['available_sum']} ({u['input_tokens']['missing_requests']}/{u['output_tokens']['missing_requests']}) | {u['cost']['available_sum']} ({u['cost']['missing_requests']} missing) | {u['latency_sum_seconds']:.3f} | {s['median_receipt_latency_seconds']:.3f} |")
        differences=[p for p in per_line if p['D']['prediction']!=p['TOPDOWN']['prediction'] or p['D']['high_score_error'] or p['TOPDOWN']['high_score_error']]
        report += ["", "Important differences/errors (all cases are in the separate comparison.md):", ""]
        if not differences:
            report.append("No differing predictions or high-score errors.")
        for p in differences[:10]:
            report.append(f"- {p['id']} {p['raw_text']}, truth {p['ground_truth']}: D {p['D']['prediction']} ({p['D']['outcome']}, scores {json.dumps(p['D']['raw_scores'])}); TOPDOWN {p['TOPDOWN']['prediction']} ({p['TOPDOWN']['outcome']}, scores {json.dumps(p['TOPDOWN']['raw_scores'])}).")
        report += [""]
    write(OUT / "combined_summary.json", results)
    report += ["## Interpretation boundaries", "",
               "D directly addresses the pilot's output-space disadvantage: it can retain a parent in a single question. Any additional TOPDOWN benefit must now appear in actual paired correctness or specificity, not merely its ability to output parents. This experiment compares complete question designs, not calibrated equivalent probability scales or pure topology alone.",
               "D has a longer 39-option prompt; one call does not guarantee lower token cost. TOPDOWN has serial parent/child round trips but shorter questions. Compare actual returned usage and per-receipt latency. Original TOPDOWN timing is cached/historical; holdout requests alternate which method runs first. Neither timing sample establishes stable production latency.",
               "The new set is synthetic and outcome-blind, not independently labeled or statistically representative. Parent-only labels for gratin, mixed snack boxes, ready-to-drink coffee and table decoration deliberately avoid unsupported precision; some reflect missing leaf coverage within a supported parent. These proposed labels need merchant review. No prompts or labels were changed after seeing outcomes. Results are separated from original30 and no significance or reliable calibration is claimed.", ""]
    (OUT / "comparison_report.md").write_text("\n".join(report),encoding="utf-8")
    verify()
    print("\n".join(report))


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("freeze","collect","evaluate"))
    args=parser.parse_args()
    try:
        {"freeze":freeze,"collect":collect,"evaluate":evaluate}[args.action]()
    except Exception as exc:
        print("Follow-up stopped: " + str(exc),flush=True)
        raise SystemExit(1)
