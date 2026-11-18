from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .catalog import Catalog, PROJECT
from .engine import Decision, DecisionEngine, Policy, Rule, SAFE_THRESHOLD
from .storage import Store

NOTICE = "Synthetic demonstration data — not actual anybill merchant data."
MERCHANT_ID = "nordmarkt-demo"


class ReceiptService:
    def __init__(self, store: Store, catalog: Catalog | None = None):
        self.store = store
        self.catalog = catalog or Catalog()
        self.engine = DecisionEngine(self.catalog)
        self.assumptions = json.loads((PROJECT / "app/data/synthetic_sales.json").read_text(encoding="utf-8"))
        for name, sha in self.assumptions["source_sha256"].items():
            if hashlib.sha256((PROJECT / name).read_bytes()).hexdigest() != sha:
                raise ValueError("Sales assumptions do not match frozen inputs: " + name)
        if set(self.assumptions["items"]) != set(self.catalog.lines):
            raise ValueError("Synthetic quantities do not cover all receipt lines.")

    @staticmethod
    def merchant(merchant_id: str):
        if merchant_id != MERCHANT_ID:
            raise KeyError("Demo merchant not found")

    def decision(self, line_id: str, merchant_id: str, policy: Policy, active: dict | None = None) -> Decision:
        self.merchant(merchant_id)
        base = self.engine.resolve(line_id, merchant_id, policy)
        if active is None:
            _, active = self.store.snapshot(merchant_id)
        correction = active.get(line_id)
        if correction:
            original = base.model_dump()
            self.engine.assign(base, correction["node_id"])
            base.outcome, base.review_required = "override", False
            base.underlying_model = original
            base.correction = {**correction, "scope": "merchant_and_exact_receipt_line",
                               "independent_ground_truth": False}
            base.applied_rules.append(Rule(code="MERCHANT_OVERRIDE", explanation="An active merchant correction for this exact receipt line takes precedence over the cached model policy. It does not apply to similar product names or other merchants."))
        return base

    def set_override(self, line_id: str, merchant_id: str, policy: Policy, node_id: str, note: str) -> int:
        self.merchant(merchant_id)
        self.catalog.line(line_id)
        if node_id not in self.catalog.nodes:
            raise ValueError("Select a valid taxonomy parent or leaf.")
        node = self.catalog.nodes[node_id]
        record_type = self.assumptions["items"][line_id]["record_type"]
        if (record_type == "sale") != (node["kind"] == "merchandise"):
            raise ValueError("A category correction cannot change the assumed POS record type. Merchandise and receipt adjustments stay separate.")
        if record_type != "sale" and node["level"] == "leaf" and node_id != f"adjustments.{record_type}":
            raise ValueError("The correction must preserve this assumed adjustment type.")
        base = self.engine.resolve(line_id, merchant_id, policy)
        return self.store.set_override(merchant_id,line_id,node_id,policy,base.model_dump(),note)

    def undo(self, line_id: str, merchant_id: str, policy: Policy) -> int:
        self.merchant(merchant_id)
        base = self.engine.resolve(line_id, merchant_id, policy)
        return self.store.undo(merchant_id,line_id,policy,base.model_dump())

    @staticmethod
    def compact(d: Decision, quantity: int, record_type: str) -> dict:
        data = d.model_dump(exclude={"assessments","underlying_model","applied_rules","provenance"})
        data.update(quantity=quantity, value_cents=d.price_cents*quantity, record_type=record_type,
                    reason=d.applied_rules[-1].explanation if d.applied_rules else "")
        return data

    def build_report(self, merchant_id: str, policy: Policy, dataset: str, active: dict, revision: int,
                     member_ids: set[str] | None = None) -> dict:
        totals = {key: 0 for key in ("sales_value_cents","leaf_value_cents","parent_value_cents","unresolved_value_cents","adjustment_value_cents","net_receipt_value_cents")}
        breakdown = {key: 0 for key in ("unidentifiable","out_of_scope","unavailable")}
        categories, summaries = {}, []
        for line in self.catalog.lines.values():
            if dataset != "all" and line.dataset != dataset:
                continue
            if member_ids is not None and line.id not in member_ids:
                continue
            assumption = self.assumptions["items"][line.id]
            quantity = 1 if member_ids is not None else assumption["weekly_quantity"]
            d = self.decision(line.id,merchant_id,policy,active)
            summary = self.compact(d,quantity,assumption["record_type"])
            summaries.append(summary)
            value = summary["value_cents"]
            totals["net_receipt_value_cents"] += value
            if assumption["record_type"] != "sale":
                totals["adjustment_value_cents"] += value
                continue
            totals["sales_value_cents"] += value
            if d.node_id and self.catalog.nodes[d.node_id]["kind"] == "merchandise":
                bucket = "leaf_value_cents" if d.specificity == "leaf" else "parent_value_cents"
                totals[bucket] += value
                parent = self.catalog.parent_of(d.node_id)
                category = categories.setdefault(parent, {"id":parent,"label":self.catalog.nodes[parent]["label"],"leaf_value_cents":0,"parent_value_cents":0,"corrected_value_cents":0})
                category[bucket] += value
                if d.outcome == "override":
                    category["corrected_value_cents"] += value
            else:
                totals["unresolved_value_cents"] += value
                reason = "unavailable" if d.availability != "complete" else "out_of_scope" if d.outcome == "out_of_scope" else "unidentifiable"
                breakdown[reason] += value
        assert totals["sales_value_cents"] == totals["leaf_value_cents"] + totals["parent_value_cents"] + totals["unresolved_value_cents"]
        assert totals["net_receipt_value_cents"] == totals["sales_value_cents"] + totals["adjustment_value_cents"]
        queue = sorted((s for s in summaries if s["review_required"] and s["record_type"] == "sale"), key=lambda s: (-s["value_cents"],s["line_id"]))
        return {"merchant_id":merchant_id,"policy":policy,"dataset":dataset,"revision":revision,"notice":NOTICE,
                "period_label":"Replay session · one occurrence per received line" if member_ids is not None else self.assumptions["period_label"],
                "mode":"replay" if member_ids is not None else "weekly", "totals":totals,
                "unresolved_breakdown":breakdown,"categories":sorted(categories.values(),key=lambda c:-(c["leaf_value_cents"]+c["parent_value_cents"])),
                "review_queue":queue,"lines":summaries,"line_count":len(summaries),
                "correction_count":sum(s["outcome"]=="override" for s in summaries),
                "safe_threshold":SAFE_THRESHOLD}

    def report(self, merchant_id: str, policy: Policy, dataset: str = "pilot", member_ids: set[str] | None = None) -> dict:
        self.merchant(merchant_id)
        revision, active = self.store.snapshot(merchant_id)
        report = self.build_report(merchant_id,policy,dataset,active,revision,member_ids)
        other_policy = "SAFE" if policy == "FORCED" else "FORCED"
        other = self.build_report(merchant_id,other_policy,dataset,active,revision,member_ids)
        report["comparison"] = {"other_policy":other_policy,"totals":other["totals"],
                                "changed_line_count":sum((a["node_id"],a["outcome"]) != (b["node_id"],b["outcome"]) for a,b in zip(report["lines"],other["lines"]))}
        return report
