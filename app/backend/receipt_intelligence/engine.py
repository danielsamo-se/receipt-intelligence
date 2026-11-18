from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .catalog import CachedResponses, Catalog

Policy = Literal["FORCED", "SAFE", "ONE_SHOT", "TWO_STAGE"]
PRIMARY_POLICIES = ("ONE_SHOT", "TWO_STAGE")
POLICY_LABELS = {"ONE_SHOT":"One-shot Hierarchical", "TWO_STAGE":"Two-stage Hierarchical",
                 "FORCED":"Naive Forced Baseline", "SAFE":"Historical SAFE · 0.85 heuristic"}
SAFE_THRESHOLD = 0.85  # Existing frozen C2 policy threshold; not a fitted production guarantee.


class Rule(BaseModel):
    code: str
    explanation: str


class Decision(BaseModel):
    line_id: str
    merchant_id: str
    raw_text: str
    price_cents: int
    merchant_type: str
    dataset: str
    policy: Policy
    node_id: str | None = None
    node_label: str | None = None
    parent_id: str | None = None
    specificity: Literal["leaf", "parent", "none"] = "none"
    outcome: Literal["leaf", "parent_only", "unidentifiable", "out_of_scope", "override"] = "unidentifiable"
    availability: Literal["complete", "partial", "unavailable"] = "complete"
    review_required: bool = True
    assessments: list[dict] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)
    applied_rules: list[Rule] = Field(default_factory=list)
    provenance: dict = Field(default_factory=dict)
    correction: dict | None = None
    underlying_model: dict | None = None
    product_memory: dict | None = None


class DecisionEngine:
    def __init__(self, catalog: Catalog, cache: CachedResponses | None = None):
        self.catalog = catalog
        self.cache = cache or CachedResponses(catalog)

    def resolve(self, line_id: str, merchant_id: str, policy: Policy) -> Decision:
        line = self.catalog.line(line_id)
        d = Decision(line_id=line.id, merchant_id=merchant_id, raw_text=line.raw_text,
                     price_cents=line.price_cents, merchant_type=line.merchant_type, dataset=line.dataset, policy=policy)
        d.applied_rules.append(Rule(code="CACHE_ONLY", explanation="Uses real cached Jev responses. No model request is made by this application."))
        d.provenance = {"taxonomy_version": self.catalog.taxonomy["version"], "source_dataset": line.dataset,
                        "mode": "cached", "policy_reference": "pilot-30/frozen/evaluation_protocol.json"}
        if policy in PRIMARY_POLICIES:
            return self.followup(d,line,policy)
        if policy == "FORCED":
            evidence = self.cache.load(line, "flat")
            d.assessments.append(evidence)
            if not evidence["available"]:
                return self.unavailable(d, evidence["error"])
            probabilities = evidence["probabilities"]
            if not all(leaf in probabilities for leaf in self.catalog.leaves):
                return self.unavailable(d, "The FLAT cache does not contain every required leaf probability.")
            leaf = max(self.catalog.leaves, key=lambda key: probabilities[key])
            score = probabilities[leaf]
            d.scores["flat_leaf_probability"] = score
            d.applied_rules.append(Rule(code="FORCED_ARGMAX", explanation="Comparison baseline: always selects the largest raw leaf probability, ignoring abstention and scope options."))
            if evidence["choice"] in ("unidentifiable", "out_of_scope"):
                d.applied_rules.append(Rule(code="SPECIAL_IGNORED", explanation=f"The cached model selected {evidence['choice']}; this baseline still forces a leaf."))
            ties = sum(probabilities[key] == score for key in self.catalog.leaves)
            if ties > 1:
                d.applied_rules.append(Rule(code="FORCED_TIE", explanation=f"{ties} leaves tie at {score:.0%}. The frozen baseline uses taxonomy order, not additional product evidence."))
            self.assign(d, leaf)
            d.review_required = score < SAFE_THRESHOLD or ties > 1 or evidence["choice"] in ("unidentifiable", "out_of_scope")
        else:
            parent = self.cache.load(line, "parent")
            d.assessments.append(parent)
            if not parent["available"]:
                return self.unavailable(d, parent["error"])
            choice = parent["choice"]
            d.applied_rules.append(Rule(code="SAFE_STAGE_THRESHOLDS", explanation=f"SAFE uses the existing TOPDOWN rule with a {SAFE_THRESHOLD:.0%} threshold separately for parent and conditional child probabilities. These are not calibrated accuracy guarantees."))
            if choice in self.catalog.taxonomy["parents"]:
                child = self.cache.load(line, "child")
                d.assessments.append(child)
                if not child["available"]:
                    return self.unavailable(d, child["error"], partial=True)
            else:
                child = None
            score = parent["probabilities"][choice]
            d.scores["parent_probability"] = score
            if choice == "unidentifiable":
                d.applied_rules.append(Rule(code="EXPLICIT_ABSTENTION", explanation="The cached parent question selected unidentifiable. The application assigns no product category."))
            elif score < SAFE_THRESHOLD:
                d.applied_rules.append(Rule(code="PARENT_BELOW_THRESHOLD", explanation=f"The selected parent or scope option has probability {score:.0%}, below {SAFE_THRESHOLD:.0%}. The application leaves the line unresolved."))
            elif choice == "out_of_scope":
                d.outcome, d.review_required = "out_of_scope", False
                d.applied_rules.append(Rule(code="SCOPE_REJECTION", explanation="The cached model selected an identifiable exclusion. Scope rejection is separate from a category assignment."))
            elif child is not None:
                leaf = child["choice"]
                child_score = child["probabilities"][leaf]
                d.scores["conditional_child_probability"] = child_score
                valid_children = {f"{choice}.{k}" for k in self.catalog.taxonomy["parents"][choice]["leaves"]}
                if leaf != "unspecified_child" and leaf not in valid_children:
                    return self.unavailable(d, "Cached child is inconsistent with the selected parent.", partial=True)
                if leaf == "unspecified_child":
                    self.assign(d, choice)
                    d.applied_rules.append(Rule(code="UNSPECIFIED_CHILD", explanation="The model selected a parent and unspecified_child. The application retains the parent without asserting a specific product category."))
                elif child_score < SAFE_THRESHOLD:
                    self.assign(d, choice)
                    d.applied_rules.append(Rule(code="CHILD_BELOW_THRESHOLD", explanation=f"The conditional child probability is {child_score:.0%}, below {SAFE_THRESHOLD:.0%}. The supported parent is retained."))
                else:
                    self.assign(d, leaf)
                    d.applied_rules.append(Rule(code="LEAF_SUPPORTED", explanation="Both policy stages meet the configured probability thresholds. This remains an AI classification, not a merchant-verified product identity."))
        d.provenance["models"] = sorted({a["model"] for a in d.assessments if a.get("available")})
        return d

    def followup(self, d: Decision, line, policy: Policy) -> Decision:
        """Reproduce the frozen D/TOPDOWN follow-up's raw choices, without gates."""
        d.provenance.update(policy_reference="followup-D-vs-TOPDOWN/frozen/protocol.json",
                            experiment_method="D" if policy=="ONE_SHOT" else "TOPDOWN",threshold=None)
        evidence = self.cache.load(line,"D" if policy=="ONE_SHOT" else "topdown_parent")
        d.assessments.append(evidence)
        if not evidence["available"]:
            return self.unavailable(d,evidence["error"])
        choice = evidence["choice"]
        d.scores["selected_action_score" if policy=="ONE_SHOT" else "parent_score"] = evidence["probabilities"][choice]
        d.applied_rules.append(Rule(code="FROZEN_RAW_CHOICE",explanation=f"{POLICY_LABELS[policy]} follows the frozen follow-up's selected actions, without a probability threshold. Scores are not calibrated correctness probabilities."))
        if choice == "unidentifiable":
            d.applied_rules.append(Rule(code="EXPLICIT_ABSTENTION",explanation="Jev selected unidentifiable. No taxonomy category is assigned; this is not a successful classification."))
        elif choice == "out_of_scope":
            d.outcome,d.review_required = "out_of_scope",False
            d.applied_rules.append(Rule(code="SCOPE_REJECTION",explanation="Jev selected out_of_scope. This is separate routing, not a product-category success."))
        elif policy == "ONE_SHOT":
            if choice not in self.catalog.nodes:
                return self.unavailable(d,"The one-shot choice is not a taxonomy node.")
            self.assign(d,choice)
            d.applied_rules.append(Rule(code="ONE_SHOT_RESOLUTION",explanation="A selected parent means parent-only support. A selected leaf supplies that specific classification. No broader-parent probability was inferred by aggregating leaf scores."))
        elif choice in self.catalog.taxonomy["parents"]:
            child = self.cache.load(line,"topdown_child")
            d.assessments.append(child)
            if not child["available"]:
                return self.unavailable(d,child["error"],partial=True)
            selected_child = child["choice"]
            d.scores["conditional_child_score"] = child["probabilities"][selected_child]
            if selected_child == "unspecified_child":
                self.assign(d,choice)
                d.applied_rules.append(Rule(code="UNSPECIFIED_CHILD",explanation="Jev selected a parent and unspecified_child. The policy retains that parent without asserting a specific child."))
            elif selected_child in self.catalog.nodes and self.catalog.nodes[selected_child]["parent_id"]==choice:
                self.assign(d,selected_child)
                d.applied_rules.append(Rule(code="TOPDOWN_RAW_CHILD",explanation="The frozen policy uses the selected conditional child without the old 0.85 gate. A strong parent score does not verify the leaf; this choice remains reviewable."))
            else:
                return self.unavailable(d,"Cached child is inconsistent with the selected parent.",partial=True)
        else:
            return self.unavailable(d,"Unexpected TOPDOWN parent choice.")
        d.provenance["models"] = sorted({a["model"] for a in d.assessments if a.get("available")})
        return d

    def assign(self, decision: Decision, node_id: str) -> None:
        node = self.catalog.nodes[node_id]
        decision.node_id, decision.node_label = node_id, node["label"]
        decision.parent_id = self.catalog.parent_of(node_id)
        decision.specificity = node["level"]
        decision.outcome = "leaf" if node["level"] == "leaf" else "parent_only"
        decision.review_required = node["level"] != "leaf"

    def matched_cohort(self, line_ids) -> dict:
        matched,excluded = [],[]
        for line_id in line_ids:
            decisions = [self.resolve(line_id,"evaluation-cache-check",policy) for policy in PRIMARY_POLICIES]
            if all(d.availability=="complete" for d in decisions):
                matched.append(line_id)
            else:
                excluded.append({"line_id":line_id,"unavailable_methods":[d.policy for d in decisions if d.availability!="complete"]})
        return {"requested_count":len(matched)+len(excluded),"matched_count":len(matched),
                "line_ids":matched,"excluded":excluded,"excluded_count":len(excluded)}

    @staticmethod
    def unavailable(d: Decision, message: str, partial: bool = False) -> Decision:
        d.availability = "partial" if partial else "unavailable"
        d.applied_rules.append(Rule(code="CACHE_UNAVAILABLE", explanation=message + " No replacement result is fabricated."))
        d.provenance["models"] = sorted({a["model"] for a in d.assessments if a.get("available")})
        return d
