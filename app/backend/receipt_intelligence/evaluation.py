"""Read-only evaluation of matched real caches, separate from operational overrides."""
import json
import statistics

from .engine import PRIMARY_POLICIES, POLICY_LABELS


def outcome(decision, truth, catalog):
    if decision.outcome == "out_of_scope":
        return "correct_scope_rejection" if truth=="OUT_OF_SCOPE" else "incorrect_scope_rejection"
    if decision.node_id is None:
        return "abstention"
    if truth in ("INSUFFICIENT_INFORMATION","OUT_OF_SCOPE"):
        return "incorrect_category"
    if truth.startswith("PARENT_ONLY:"):
        parent = truth.split(":",1)[1]
        if decision.node_id == parent:
            return "correct_parent"
        return "overclaim" if decision.parent_id==parent else "incorrect_category"
    if decision.node_id == truth:
        return "correct_leaf"
    return "correct_parent" if decision.node_id==catalog.parent_of(truth) else "incorrect_category"


def matched_evaluation(catalog, engine):
    root = catalog.root / "results/taxonomy-v2/followup-D-vs-TOPDOWN"
    samples = {}
    for sample,dataset in (("original30","pilot"),("holdout24","holdout")):
        frozen = json.loads((root / sample / "per_line.json").read_text(encoding="utf-8"))
        truths = {f"{dataset}:{r['id']}":r["ground_truth"] for r in frozen}
        cohort = engine.matched_cohort(list(truths))
        methods = {}
        cases = []
        for policy in PRIMARY_POLICIES:
            counts = {key:0 for key in ("correct_leaf","correct_parent","incorrect_category","overclaim",
                      "abstention","correct_scope_rejection","incorrect_scope_rejection")}
            assessments,receipt_latencies = [],[]
            leaf_commits = parent_commits = 0
            for line_id in cohort["line_ids"]:
                d = engine.resolve(line_id,"frozen-evaluation-no-merchant-feedback",policy)
                result = outcome(d,truths[line_id],catalog)
                counts[result] += 1
                leaf_commits += d.specificity=="leaf"
                parent_commits += d.specificity=="parent"
                assessments.extend(d.assessments)
                times = [a.get("latency_seconds") for a in d.assessments]
                if all(t is not None for t in times):
                    receipt_latencies.append(sum(times))
                cases.append({"line_id":line_id,"policy":policy,"truth":truths[line_id],
                              "prediction":d.node_id or d.outcome,"outcome":result})
            commits = leaf_commits+parent_commits
            count = cohort["matched_count"]
            usage = {}
            for key in ("input_tokens","output_tokens","cost"):
                values = [a.get("usage",{}).get(key) for a in assessments]
                usage[key] = {"available_sum":sum(v for v in values if v is not None),
                              "missing_requests":sum(v is None for v in values)}
            methods[policy] = {**counts,"label":POLICY_LABELS[policy],"denominator":count,
                "taxonomy_commitments":commits,"leaf_commitments":leaf_commits,"parent_commitments":parent_commits,
                "taxonomy_coverage":commits/count if count else None,
                "classification_accuracy":(counts["correct_leaf"]+counts["correct_parent"])/commits if commits else None,
                "requests":len(assessments),"usage":usage,
                "median_receipt_latency_seconds":statistics.median(receipt_latencies) if receipt_latencies else None,
                "latency_missing_receipts":count-len(receipt_latencies)}
            assert sum(counts.values()) == count
        samples[sample] = {"cohort":cohort,"methods":methods,"cases":cases}
    return {"samples":samples,"policy":"Frozen selected actions; no probability threshold for either method.",
        "differences":[
            "Same taxonomy v2: 27 leaves and 10 parents. D uses one 39-option question including both special options; parent choices mean parent-only resolution.",
            "TOPDOWN uses a 12-option parent question, then a conditional child question with unspecified_child. No child request follows a special parent choice.",
            "Frozen wording and prompt length differ. D repeats parent scopes across its longer option set; this is a comparison of complete question designs, not topology alone.",
            "D scores describe mutually exclusive resolution actions. TOPDOWN parent and conditional child scores describe different quantities. None is a calibrated correctness probability.",
            "The former dashboard SAFE policy used an exploratory 0.85 gate per stage. That historical policy is retained in technical evaluation and is not applied to this raw-choice comparison.",
            "Original TOPDOWN latency is historical/noncontemporaneous. Additional-set collection alternated method order. Returned cost is OpenRouter credits, not measured production savings."],
        "limitations":["30 original and 24 additional synthetic examples, reported separately; labels are not independent merchant ground truth.",
            "Only complete paired caches enter each denominator. Missing predictions are excluded, never counted as abstentions, errors or successes.",
            "Category counts include receipt-adjustment classifications. Operational category-sales reporting excludes adjustments and applies merchant feedback; this evaluation does neither.",
            "Scope rejections are separate from category success. Parent-only decisions are not correct leaf assignments. Overclaims are category errors.",
            "No statistical significance, production accuracy, calibration, universal method superiority or production savings claim."],
        "sources":["results/taxonomy-v2/followup-D-vs-TOPDOWN/frozen/protocol.json",
                   "results/taxonomy-v2/followup-D-vs-TOPDOWN/frozen/D_question.json",
                   "results/taxonomy-v2/followup-D-vs-TOPDOWN/frozen/TOPDOWN_prompts.json"]}
