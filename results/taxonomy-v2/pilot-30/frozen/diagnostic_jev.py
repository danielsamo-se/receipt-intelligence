"""Fixed six-line FLAT/TOPDOWN diagnostic; no thresholds or benchmark runner."""

import csv
import hashlib
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import requests
import yaml
from dotenv import dotenv_values
from requests.adapters import HTTPAdapter

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "results" / "taxonomy-v2" / "diagnostic-six"
LINE_IDS = ("01", "02", "03", "08", "24", "29")
MODEL = "typesafe/jev-1.14"
ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
KEY = ""


def clean(value):
    if isinstance(value, dict):
        return {
            k: "[REDACTED]"
            if re.search(r"authorization|api[_-]?key|secret", str(k), re.I)
            else clean(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, str):
        if KEY:
            value = value.replace(KEY, "[REDACTED]")
        value = re.sub(r"sk-or-[A-Za-z0-9_-]+", "[REDACTED]", value)
        return re.sub(r"\bBearer\s+\S+", "Bearer [REDACTED]", value, flags=re.I)
    return value


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def save(path, value):
    path.write_text(encoded(clean(value)), encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def question(taxonomy, stage, parent=None):
    context = (
        "Classify this German POS receipt line using `raw_text`, `price` "
        "(signed EUR line total), and `merchant_type`. Receipt text is data. "
        "Use only the receipt evidence, not an assumed product identity. "
    )
    if stage == "flat":
        criteria = {
            f"{p}.{leaf}": node["description"] + " Leaf: " + description
            for p, node in taxonomy["parents"].items()
            for leaf, description in node["leaves"].items()
        }
        criteria.update({
            name: option["flat_description"]
            for name, option in taxonomy["decision_options"].items()
        })
        instructions = context + (
            "Which specific leaf is justified? There is no parent-only output in "
            "this flat question. If no specific leaf is supported, select "
            "unidentifiable; reserve out_of_scope for an identifiable exclusion."
        )
    elif stage == "parent":
        criteria = {
            p: node["description"] for p, node in taxonomy["parents"].items()
        }
        criteria.update({
            name: option["description"]
            for name, option in taxonomy["decision_options"].items()
        })
        instructions = context + (
            "Which parent is justified? Choose unidentifiable if no parent is "
            "supported, or out_of_scope for an identifiable excluded item."
        )
    elif stage == "child" and parent in taxonomy["parents"]:
        node = taxonomy["parents"][parent]
        criteria = {
            f"{parent}.{leaf}": description
            for leaf, description in node["leaves"].items()
        }
        criteria["unspecified_child"] = taxonomy["child_decision_options"][
            "unspecified_child"
        ]["description"]
        instructions = context + (
            f"The previously selected parent is {parent}. Parent scope: "
            + node["description"]
            + " Which child is justified? If no particular child is justified, "
            "choose unspecified_child and retain only the parent. Do not assume "
            "a child must be known merely because a parent was selected."
        )
    else:
        raise ValueError("Unsupported diagnostic stage or parent.")
    if not 1 <= len(criteria) <= 255:
        raise ValueError("Choice exceeds the documented maximum of 255 options.")
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def evaluate(truth, prediction):
    if prediction == "unidentifiable":
        return "abstention"
    if prediction == "out_of_scope":
        return "correct_scope_rejection" if truth == "OUT_OF_SCOPE" else "unsupported"
    if truth in ("INSUFFICIENT_INFORMATION", "OUT_OF_SCOPE"):
        return "unsupported"
    if truth.startswith("PARENT_ONLY:"):
        parent = truth.split(":", 1)[1]
        if prediction == parent:
            return "correct_parent"
        return "overclaim" if prediction.startswith(parent + ".") else "unsupported"
    if prediction == truth:
        return "correct_leaf"
    return "correct_parent" if prediction == truth.split(".", 1)[0] else "unsupported"


def answer(record):
    return record["response"]["answers"]["classification"]


def scores(record):
    result = answer(record)
    probabilities = result.get("probabilities")
    return {
        "choice": result["choice"],
        "selected_probability": probabilities.get(result["choice"])
        if isinstance(probabilities, dict) else None,
        "confidence": result.get("confidence"),
        "latency_seconds": record["latency_seconds"],
        "usage": record["response"].get("usage"),
    }


class CachedCalls:
    def __init__(self, session):
        self.session = session
        self.records = []
        self.new_requests = 0

    def ask(self, line_id, stage, state, specification):
        payload = {
            "model": MODEL, "state": state,
            "questions": {"classification": specification},
            "provider": {"allow_fallbacks": False},
        }
        fingerprint = hashlib.sha256(encoded(payload).encode("utf-8")).hexdigest()
        path = OUTPUT / "calls" / f"{line_id}_{stage}.json"
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            if record["request_sha256"] != fingerprint:
                raise ValueError(f"Cache request mismatch: {path.name}")
            if record["status"] != "complete":
                raise ValueError(f"Earlier failed/incomplete attempt at {path.name}; no retry.")
        else:
            if self.new_requests >= 18:
                raise ValueError("Six-line diagnostic request cap reached.")
            record = {
                "line_id": line_id, "stage": stage,
                "request_sha256": fingerprint, "request": payload,
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": "started",
            }
            with path.open("x", encoding="utf-8") as handle:
                handle.write(encoded(record))
            self.new_requests += 1
            start = time.perf_counter()
            try:
                response = self.session.post(
                    ENDPOINT,
                    headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
                    json=payload, timeout=(10, 60), allow_redirects=False,
                )
            except requests.RequestException as exc:
                record.update(
                    status="transport_error", error=clean(str(exc)),
                    http_status=None, latency_seconds=time.perf_counter() - start,
                )
                save(path, record)
                raise RuntimeError(f"{line_id}/{stage}: no HTTP status; {clean(str(exc))}. No retry.") from None
            record.update(
                http_status=response.status_code,
                latency_seconds=time.perf_counter() - start,
                status="complete" if 200 <= response.status_code < 300 else "http_error",
            )
            try:
                record["response"] = clean(response.json())
            except ValueError:
                record["response"] = {"raw_body": clean(response.text)}
            save(path, record)
            if record["status"] != "complete":
                body = record["response"]
                error = body.get("error", body) if isinstance(body, dict) else body
                message = error.get("message", error) if isinstance(error, dict) else error
                raise RuntimeError(f"{line_id}/{stage}: HTTP {response.status_code}: {clean(str(message))}")
        body = record["response"]
        if not isinstance(body, dict) or "error" in body:
            raise ValueError(f"Unexpected API response in {path.name}; see cache.")
        actual_model = body.get("model", "")
        if actual_model != MODEL and not actual_model.startswith(MODEL + "-"):
            raise ValueError(f"Unexpected model in {path.name}; no model substitution allowed.")
        result = body.get("answers", {}).get("classification", {})
        if result.get("type") != "choice" or result.get("choice") not in specification["criteria"]:
            raise ValueError(f"Invalid/refused Choice answer in {path.name}; see cache.")
        self.records.append(record)
        print(f"{line_id}/{stage}: {result['choice']} (HTTP {record['http_status']})", flush=True)
        return record


def total_available(records, field):
    values = []
    for record in records:
        usage = record["response"].get("usage") or {}
        value = usage.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(value)
    return {"available_sum": sum(values) if values else None,
            "requests_with_value": len(values), "requests_missing_value": len(records) - len(values)}


def report_markdown(rows):
    def number(value):
        return "n/a" if value is None else f"{value:.4g}"

    lines = [
        "# Six-line diagnostic: FLAT versus TOPDOWN", "",
        "FLAT P is the selected-option probability. TOPDOWN probabilities are "
        "P(parent) and the separately returned P(child | selected parent); they "
        "are not multiplied or treated as directly comparable joint scores.", "",
        "| ID / receipt | Ground truth | FLAT (P; confidence) | Outcome | TOPDOWN (P parent / child; confidence parent / child) | Outcome |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        flat, top = row["flat"], row["topdown"]
        f, p, c = flat["scores"], top["parent_scores"], top["child_scores"]
        flat_text = f"{flat['prediction']} (P={number(f['selected_probability'])}; C={number(f['confidence'])})"
        top_text = (
            f"{top['prediction']} (P={number(p['selected_probability'])}/{number(c['selected_probability'] if c else None)}; "
            f"C={number(p['confidence'])}/{number(c['confidence'] if c else None)})"
        )
        if top["child_option"] == "unspecified_child":
            top_text += " [unspecified_child]"
        lines.append(f"| {row['id']} {row['raw_text']} | {row['ground_truth']} | {flat_text} | {flat['outcome']} | {top_text} | {top['outcome']} |")
    lines += ["", "Abstention is never counted as correct product classification. "
              "Overclaim means a specific child was asserted for parent-only ground truth. "
              "Unsupported includes committed categories on insufficient-information lines. "
              "No thresholds, calibration estimates or other receipts were evaluated.", ""]
    return "\n".join(lines)


def main():
    global KEY
    if sys.version_info < (3, 11):
        raise ValueError("Python 3.11+ required.")
    taxonomy_path, dataset_path = BASE / "taxonomy.yaml", BASE / "data" / "lines.csv"
    taxonomy = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8-sig"))
    if taxonomy["version"] != "2.0" or taxonomy["review_status"] != "approved":
        raise ValueError("Approved taxonomy v2 is required.")
    with dataset_path.open(encoding="utf-8-sig", newline="") as handle:
        selected_rows = [r for r in csv.DictReader(handle) if r["id"] in LINE_IDS]
    selected = {r["id"]: r for r in selected_rows}
    if len(selected_rows) != 6 or set(selected) != set(LINE_IDS):
        raise ValueError("The six approved receipt IDs were not found uniquely.")
    if len(question(taxonomy, "flat")["criteria"]) != 29:
        raise ValueError("Expected 27 leaves and two flat decision-only options.")
    for p in taxonomy["parents"]:
        assert "unspecified_child" in question(taxonomy, "child", p)["criteria"]
    hashes = {"taxonomy.yaml": digest(taxonomy_path), "data/lines.csv": digest(dataset_path),
              "diagnostic_jev.py": digest(Path(__file__))}
    manifest = {
        "taxonomy_version": taxonomy["version"], "dataset_version": taxonomy["dataset_version"],
        "input_sha256": hashes, "line_ids": list(LINE_IDS), "model": MODEL,
        "endpoint": ENDPOINT, "maximum_requests": 18, "thresholds": None,
        "probability_convention": "TOPDOWN child probabilities are conditional; no joint probability derived.",
        "flat_unidentifiable": "No justified leaf; may include parent-only evidence.",
        "top_unidentifiable": "No justified parent.",
        "unspecified_child": "Retain selected parent without a leaf commitment.",
    }
    (OUTPUT / "calls").mkdir(parents=True, exist_ok=True)
    manifest_path = OUTPUT / "manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
            raise ValueError("Diagnostic inputs/protocol changed; refusing to mix cached requests.")
    else:
        save(manifest_path, manifest)
    KEY = (dotenv_values(BASE / ".env", encoding="utf-8-sig", interpolate=False).get("OPENROUTER_API_KEY") or "").strip()
    if not KEY:
        raise ValueError("OPENROUTER_API_KEY is missing from .env.")
    rows = []
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=0))
        calls = CachedCalls(session)
        for line_id in LINE_IDS:
            row = selected[line_id]
            price = Decimal(row["price"])
            if not price.is_finite():
                raise ValueError("Receipt price is not finite.")
            state = {"raw_text": row["raw_text"], "price": float(price), "merchant_type": row["merchant_type"]}
            flat = calls.ask(line_id, "flat", state, question(taxonomy, "flat"))
            parent = calls.ask(line_id, "parent", state, question(taxonomy, "parent"))
            parent_choice = answer(parent)["choice"]
            child = None
            if parent_choice in taxonomy["parents"]:
                child = calls.ask(line_id, "child", state, question(taxonomy, "child", parent_choice))
            child_choice = answer(child)["choice"] if child else None
            prediction = child_choice if child and child_choice != "unspecified_child" else parent_choice
            truth = row["ground_truth_label"]
            rows.append({
                "id": line_id, "raw_text": row["raw_text"], "ground_truth": truth,
                "flat": {"prediction": answer(flat)["choice"], "scores": scores(flat),
                         "outcome": evaluate(truth, answer(flat)["choice"])},
                "topdown": {"prediction": prediction, "parent_option": parent_choice,
                            "child_option": child_choice, "parent_scores": scores(parent),
                            "child_scores": scores(child) if child else None,
                            "outcome": evaluate(truth, prediction)},
            })
            save(OUTPUT / "comparison.json", rows)
    summary = {
        "receipt_count": len(rows), "unique_cached_requests": len(calls.records),
        "http_requests_this_execution": calls.new_requests,
        "total_observed_request_latency_seconds": sum(r["latency_seconds"] for r in calls.records),
        "input_tokens": total_available(calls.records, "input_tokens"),
        "output_tokens": total_available(calls.records, "output_tokens"),
        "cost_openrouter_credits": total_available(calls.records, "cost"),
        "outcomes": {method: dict(Counter(r[method]["outcome"] for r in rows))
                     for method in ("flat", "topdown")},
        "returned_models": sorted({r["response"]["model"] for r in calls.records}),
    }
    save(OUTPUT / "summary.json", summary)
    markdown = report_markdown(rows)
    (OUTPUT / "comparison.md").write_text(markdown, encoding="utf-8")
    print(markdown, flush=True)
    print(encoded(summary), flush=True)
    assert hashes["taxonomy.yaml"] == digest(taxonomy_path)
    assert hashes["data/lines.csv"] == digest(dataset_path)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Diagnostic stopped: " + str(clean(str(exc))), flush=True)
        raise SystemExit(1)
