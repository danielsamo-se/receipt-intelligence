from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .catalog import Catalog, PROJECT
from .engine import Decision, DecisionEngine, Policy, Rule, SAFE_THRESHOLD, PRIMARY_POLICIES, POLICY_LABELS
from .product_memory import ProductMemory, normalize
from .storage import Store

NOTICE = "Synthetic demonstration data — not actual anybill merchant data."
MERCHANT_ID = "nordmarkt-demo"


class ReceiptService:
    def __init__(self, store: Store, catalog: Catalog | None = None):
        self.store = store
        self.catalog = catalog or Catalog()
        self.engine = DecisionEngine(self.catalog)
        self.memory = ProductMemory(store,self.catalog)
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

    def input(self, line_id: str, merchant_id: str):
        if line_id in self.catalog.lines:
            return self.catalog.line(line_id), {"pos_namespace":"demo-pos","identifier":None}
        return self.memory.db.receipt(merchant_id,line_id)

    def model_decision(self, line_id: str, merchant_id: str, policy: Policy) -> Decision:
        line,_ = self.input(line_id,merchant_id)
        # Only identical complete input state can reuse an existing cached response.
        cached = self.catalog.lines.get(line_id) or next((item for item in self.catalog.lines.values()
            if (item.raw_text,item.price_cents,item.merchant_type)==(line.raw_text,line.price_cents,line.merchant_type)),None)
        if cached:
            decision = self.engine.resolve(cached.id,merchant_id,policy)
            decision.line_id,decision.dataset = line.id,line.dataset
            if cached.id != line.id:
                decision.provenance["exact_input_cache_source"] = cached.id
            return decision
        decision = Decision(line_id=line.id,merchant_id=merchant_id,raw_text=line.raw_text,
            price_cents=line.price_cents,merchant_type=line.merchant_type,dataset=line.dataset,policy=policy)
        decision.provenance = {"mode":"no_matching_cache","taxonomy_version":self.catalog.taxonomy["version"],"actual_model_calls":0}
        return self.engine.unavailable(decision,"This new input has no identical Jev cache. Merchant review is required.")

    def decision(self, line_id: str, merchant_id: str, policy: Policy, active: dict | None = None,
                 retrieve: bool = True) -> Decision:
        self.merchant(merchant_id)
        line,context = self.input(line_id,merchant_id)
        if active is None:
            _, active = self.store.snapshot(merchant_id)
        correction = active.get(line_id)
        memory = self.memory.assess(line,merchant_id,context["pos_namespace"],context.get("identifier"),retrieve=retrieve and not correction)
        if correction:
            base = self.model_decision(line_id,merchant_id,policy)
            original = base.model_dump()
            self.engine.assign(base, correction["node_id"])
            base.outcome, base.review_required = "override", False
            base.underlying_model = original
            base.correction = {**correction, "scope": "merchant_and_exact_receipt_line",
                               "independent_ground_truth": False}
            base.applied_rules.append(Rule(code="MERCHANT_OVERRIDE", explanation="An active merchant correction for this exact receipt line takes precedence over the cached model policy. It does not apply to similar product names or other merchants."))
            memory["status"] = "line_override_precedence"
            memory["model_stage_bypassed"] = False
        elif memory["match"]:
            product = memory["match"]["product"]
            base = Decision(line_id=line.id,merchant_id=merchant_id,raw_text=line.raw_text,price_cents=line.price_cents,
                merchant_type=line.merchant_type,dataset=line.dataset,policy=policy)
            self.engine.assign(base,product["node_id"])
            base.outcome,base.review_required = "override",False
            base.provenance = {"mode":"merchant_product_memory","taxonomy_version":self.catalog.taxonomy["version"],
                "product_id":product["product_id"],"source":product["source"],"actual_model_calls":0}
            base.applied_rules.append(Rule(code="CONFIRMED_PRODUCT_MEMORY",explanation="An exact confirmed identifier or alias in this merchant/POS scope supplies the catalog classification. Similarity did not establish identity. The Jev policy stage was bypassed."))
        else:
            base = self.model_decision(line_id,merchant_id,policy)
            base.applied_rules.insert(0,Rule(code="MEMORY_NOT_TRUSTED",explanation="No safe exact confirmed product mapping. Retrieval candidates are suggestions only; the existing cached Jev policy or review determines the outcome."))
        base.product_memory = memory
        return base

    def inspect(self, line_id: str, merchant_id: str, policy: Policy) -> dict:
        decision = self.decision(line_id,merchant_id,policy)
        line,context = self.input(line_id,merchant_id)
        memory = decision.product_memory
        memory["audit"] = self.memory.db.audit(merchant_id,context["pos_namespace"],line.merchant_type,normalize(line.raw_text))
        if memory["match"]:
            # Inspection-only comparison, never used to establish the mapped outcome.
            decision.underlying_model = self.model_decision(line_id,merchant_id,policy).model_dump()
        assumption = self.assumptions["items"].get(line_id)
        return {"decision":decision,"sales_assumption":assumption or {"weekly_quantity":0,"record_type":"sale"},
                "audit":self.store.audit(merchant_id,line_id),"included_in_weekly_analytics":assumption is not None}

    def set_override(self, line_id: str, merchant_id: str, policy: Policy, node_id: str, note: str) -> int:
        self.merchant(merchant_id)
        self.input(line_id,merchant_id)
        if node_id not in self.catalog.nodes:
            raise ValueError("Select a valid taxonomy parent or leaf.")
        node = self.catalog.nodes[node_id]
        record_type = self.assumptions["items"].get(line_id,{"record_type":"sale"})["record_type"]
        if (record_type == "sale") != (node["kind"] == "merchandise"):
            raise ValueError("A category correction cannot change the assumed POS record type. Merchandise and receipt adjustments stay separate.")
        if record_type != "sale" and node["level"] == "leaf" and node_id != f"adjustments.{record_type}":
            raise ValueError("The correction must preserve this assumed adjustment type.")
        base = self.model_decision(line_id, merchant_id, policy)
        before = self.decision(line_id,merchant_id,policy,retrieve=False).model_dump()
        return self.store.set_override(merchant_id,line_id,node_id,policy,base.model_dump(),note,before)

    def undo(self, line_id: str, merchant_id: str, policy: Policy) -> int:
        self.merchant(merchant_id)
        base = self.model_decision(line_id, merchant_id, policy)
        return self.store.undo(merchant_id,line_id,policy,base.model_dump())

    @staticmethod
    def compact(d: Decision, quantity: int, record_type: str) -> dict:
        data = d.model_dump(exclude={"assessments","underlying_model","applied_rules","provenance"})
        data.update(quantity=quantity, value_cents=d.price_cents*quantity, record_type=record_type,
                    reason=d.applied_rules[-1].explanation if d.applied_rules else "")
        return data

    def build_report(self, merchant_id: str, policy: Policy, dataset: str, active: dict, revision: int,
                     member_ids: set[str] | None = None, weekly_filter: bool = False) -> dict:
        is_replay = member_ids is not None and not weekly_filter
        totals = {key: 0 for key in ("sales_value_cents","leaf_value_cents","parent_value_cents","unresolved_value_cents","adjustment_value_cents","net_receipt_value_cents")}
        breakdown = {key: 0 for key in ("unidentifiable","out_of_scope","unavailable")}
        categories, summaries = {}, []
        for line in self.catalog.lines.values():
            if dataset != "all" and line.dataset != dataset:
                continue
            if member_ids is not None and line.id not in member_ids:
                continue
            assumption = self.assumptions["items"][line.id]
            quantity = 1 if is_replay else assumption["weekly_quantity"]
            d = self.decision(line.id,merchant_id,policy,active,retrieve=False)
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
                "period_label":"Replay session · one occurrence per received line" if is_replay else self.assumptions["period_label"],
                "mode":"replay" if is_replay else "weekly", "totals":totals,
                "unresolved_breakdown":breakdown,"categories":sorted(categories.values(),key=lambda c:-(c["leaf_value_cents"]+c["parent_value_cents"])),
                "review_queue":queue,"lines":summaries,"line_count":len(summaries),
                "correction_count":sum(s["outcome"]=="override" for s in summaries),
                "safe_threshold":SAFE_THRESHOLD}

    def report(self, merchant_id: str, policy: Policy, dataset: str = "pilot", member_ids: set[str] | None = None,
               replay_id: str | None = None) -> dict:
        self.merchant(merchant_id)
        session = None
        if replay_id:
            revision,active,session = self.store.report_context(merchant_id,replay_id)
            member_ids = set(session["line_ids"])
        else:
            revision, active = self.store.snapshot(merchant_id)
        cohort = None
        if policy in PRIMARY_POLICIES:
            requested = [line.id for line in self.catalog.lines.values() if (dataset=="all" or line.dataset==dataset)
                         and (member_ids is None or line.id in member_ids)]
            cohort = self.engine.matched_cohort(requested)
            cohort["excluded_sales_value_cents"] = sum(self.catalog.line(item["line_id"]).price_cents *
                (1 if session else self.assumptions["items"][item["line_id"]]["weekly_quantity"])
                for item in cohort["excluded"] if self.assumptions["items"][item["line_id"]]["record_type"]=="sale")
            # Missing paired predictions are excluded before computing either side's totals.
            allowed = set(cohort["line_ids"])
            member_ids = allowed
        report = self.build_report(merchant_id,policy,dataset,active,revision,member_ids,
                                   weekly_filter=cohort is not None and session is None)
        other_policy = {"ONE_SHOT":"TWO_STAGE","TWO_STAGE":"ONE_SHOT","FORCED":"SAFE","SAFE":"FORCED"}[policy]
        other = self.build_report(merchant_id,other_policy,dataset,active,revision,member_ids,
                                  weekly_filter=cohort is not None and session is None)
        report["comparison"] = {"other_policy":other_policy,"totals":other["totals"],
                                "cohort":cohort,"threshold":None if cohort is not None else SAFE_THRESHOLD,
                                "changed_line_count":sum((a["node_id"],a["outcome"]) != (b["node_id"],b["outcome"]) for a,b in zip(report["lines"],other["lines"]))}
        report["review_policy"] = {"policy":policy,"label":POLICY_LABELS[policy],
            "criteria":"Selected policy's parent-only or verification-required merchandise lines; confirmed mappings and scope rejections are excluded. Ranked by stored synthetic sales impact."}
        report["replay"] = session
        return report
