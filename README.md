# Jev receipt classification: taxonomy and dataset v2.0

Status: taxonomy v2 approved by the user for the fixed six-line diagnostic. That diagnostic is complete: 16 successful API requests for IDs 01, 02, 03, 08, 24 and 29 only. The original single successful call remains isolated under v1.0.

## Current files

- taxonomy.yaml: 10 retail parents (9 merchandise, 1 receipt-adjustment), 27 leaves, 2 top-level decision-only options, and a separate unspecified_child child option. Approval is recorded as review_status: approved.
- data/lines.csv: exactly 30 synthetic, manually reviewable lines: 22 leaf-supported, 4 parent-only, 3 insufficient-information, 1 identifiable out-of-scope.
- test_jev.py: retained single-receipt tester; not invoked by the diagnostic.
- diagnostic_jev.py: fixed six-line FLAT/TOPDOWN diagnostic, with exact-request caching, no automatic retries, no thresholds and no arbitrary receipt selection.
- results/taxonomy-v2/diagnostic-six/: all 16 request/response cache records, an input/protocol manifest, comparison.json, comparison.md and summary.json.

All essential category boundaries are in the parent/leaf descriptions in taxonomy.yaml. The tester sends the full parent descriptions, including exclusions, rather than a separate notes list. Ground-truth labels and review notes never belong in model input; use only raw_text, price (signed EUR line total), and merchant_type.

## What changed

The former pantry parent was split into confectionery_snacks, prepared_food and cooking_ingredients. Parent-level output now distinguishes snack purchases, meals/side dishes and cooking ingredients. HARIBO SAURE POMMES and POMMES FRITES TK therefore have different parents.

Three merchandise parents have at least three potentially confusable leaves: confectionery_snacks (3), dairy_eggs (4), and beverages (5). Each also has at least three represented leaves in this sample. The adjustment parent has three separately defined leaves as well.

Rows 09, 15 and 19 replace easy examples with vegetable lasagne, a savory snack and an electronic cable. WMF PF 24CM now uses supermarket context. All four parent-only rows (24-27) and all three insufficient-information rows (08, 28, 29) are preserved unchanged.

## Decision-only options and ground truth

The two top-level options are not taxonomy parents or leaves and do not count as product classifications. Their descriptions explicitly distinguish parent-level versus leaf-level uncertainty:

- unidentifiable: explicit abstention. At TOPDOWN parent level, no parent is justified. In FLAT, no specific leaf is justified; this includes parent-only evidence because FLAT has no parent-only output. These stage-specific descriptions are saved with each actual request. Do not assume Jev will choose the option reliably.
- out_of_scope: an identifiable item or adjustment with no supported parent. This is a scope rejection, not an abstention or a successful product classification. USB-C KABEL 1M is the single labeled example; its electronic identity is known, unlike ART 004711.

TOPDOWN child questions have a separate unspecified_child option. It retains the selected parent without asserting a child; it is not top-level unidentifiable and is not an overall abstention. On parent-only ground truth it can produce a correct parent decision; on insufficient-information ground truth the retained parent is still unsupported. Child calls run only after an actual parent is selected.

CSV ground-truth encoding:

- parent.leaf: that leaf is supported; its parent is also supported. This does not assert an exact SKU.
- PARENT_ONLY:parent: the parent is supported; no particular child is justified.
- INSUFFICIENT_INFORMATION: no category or known exclusion is justified.
- OUT_OF_SCOPE: identifiable item outside every supported parent.

## Evaluation rules for the later approved experiment

Keep the following outcomes separate; do not award partial leaf credit:

| Ground truth | Decision | Outcome |
| --- | --- | --- |
| Known leaf | Exact leaf | correct_leaf: correct specific classification |
| Known leaf | Its parent | correct_parent: correct, less specific classification |
| Known leaf | Another leaf or parent | wrong_category |
| Parent only | Exact supported parent | correct_parent |
| Parent only | A child of that parent | overclaim, even if plausible; never correct_leaf |
| Parent only | A category outside that parent | wrong_category |
| Insufficient information | Any taxonomy parent or leaf, including adjustments | wrong_category |
| Insufficient information | out_of_scope | wrong_scope_rejection: unjustified assertion of known exclusion |
| Out of scope | out_of_scope | correct_scope_rejection; never a correct product classification |
| Out of scope | Any taxonomy parent or leaf | wrong_category |
| Any supported case | out_of_scope | wrong_scope_rejection |
| Any case | unidentifiable or threshold-based abstention | abstention; never a correct product classification |

Report these quantities independently, with explicit denominators:

- Counts: correct_leaf, correct_parent, wrong_category, overclaim, correct_scope_rejection, wrong_scope_rejection, and abstention. Split merchandise and receipt adjustments where relevant. Distinguish explicit unidentifiable from threshold-based abstention.
- Taxonomy automation coverage: number of committed taxonomy parent/leaf decisions divided by all 30 lines. Include erroneous commits and overclaims in coverage. Exclude both decision-only options. Report scope-rejection coverage separately rather than hiding it in product automation.
- Classification accuracy: (correct_leaf + correct_parent) / all committed taxonomy parent/leaf decisions. Overclaims and wrong-category decisions stay in the denominator and are not correct. The classification error rate is (wrong_category + overclaim) / that same denominator.
- Scope routing: report correct and wrong scope rejections separately. A separate overall non-abstaining decision error rate is (wrong_category + overclaim + wrong_scope_rejection) / (taxonomy commitments + scope rejections). Label this distinctly from classification accuracy.
- Specificity: report numbers of leaf and parent commitments, correct leaf and correct parent decisions, and overclaims. Leaf-commit share is leaf commitments / all taxonomy commitments; it is not accuracy. Include wrong and overclaim leaf commitments in this specificity measure rather than making a system appear less specific by dropping its mistakes.
- Insufficient-information safety check: report false taxonomy commitments out of the 3 insufficient-information lines, and unjustified out_of_scope selections separately. An abstention on one of these lines is appropriate behavior, but is still not a correct product classification.
- If a denominator is zero, report the metric as undefined rather than zero or 100%.

No threshold sweep, model calibration claim, or performance estimate is justified by this data preparation. Confidence is not assumed to be the probability of correctness on receipts.

## History and version separation

Original artifacts are retained without byte changes:

- history/taxonomy-v1/taxonomy.yaml
- history/taxonomy-v1/data/lines.csv
- history/taxonomy-v1/README.md
- history/taxonomy-v1/test_jev.py
- results/taxonomy-v1/first_jev_response.json
- results/taxonomy-v1/first_jev_metadata.json

results/taxonomy-v1/manifest.json assigns the original call to taxonomy/dataset v1.0 retrospectively, records artifact SHA256 hashes, and marks it historical-only and excluded from revised-taxonomy results. The original metadata's stored request and input hashes remain unchanged. There is no current unversioned result to reuse. The six-line v2 diagnostic is stored separately under results/taxonomy-v2/diagnostic-six/ with version fields and input hashes; it does not reuse v1 probabilities.

The user approved taxonomy v2 and this six-line diagnostic. The status has been updated accordingly; this does not authorize other experiments. History snapshots are provenance, not instructions to run an old script.

## Remaining ambiguity and pilot limits

- BIO ZITR 500G supports fruit, but not a particular citrus species or exact product.
- WMF PF 24CM supports kitchenware without resolving pan versus pot; supermarket context cannot resolve that abbreviation.
- KOKOSMILCH 400ML uses the conventional culinary interpretation. The label remains proposed: merchant article evidence identifying a drinking product would move it to beverages.plant_drinks. The item text alone cannot establish brand, package or formulation.
- A household-wares department label supports household without identifying kitchenware versus cleaning supplies; unsupported finer detail must remain unknown.
- Five leaves have no leaf-labeled example: produce.vegetables, grains.dry_staples, dairy_eggs.eggs, cooking_ingredients.oils_fats and beverages.alcoholic. They keep the taxonomy meaningful without expanding this 30-line pilot; their performance cannot be assessed here.
- One out-of-scope example can check technical behavior, not estimate reliable open-set detection. Likewise, 30 lines cannot establish calibration or production accuracy.

The requested six-line diagnostic is complete. Stop here; no additional receipt calls, UI or full A/B/C threshold evaluation is authorized by this diagnostic run.

## Observed six-line diagnostic

Both methods returned correct leaves for 01, 02 and 03, and abstained on insufficient-information rows 08 and 29. For parent-only row 24, FLAT abstained while TOPDOWN selected dairy_eggs followed by unspecified_child, retaining a correct parent decision. There were no overclaims or unsupported decisions in these six cases. Abstentions are not counted as correct product classifications.

FLAT used 6 requests; TOPDOWN used 6 parent and 4 child requests, skipping child calls after unidentifiable. All 16 returned HTTP 200 from typesafe/jev-1.14-20261014. Every request returned a full distribution over its actual options and a confidence value. The cache preserves all returned response fields, including usage and cost, and measured request latency. No missing probabilities or confidence values were inferred.

TOPDOWN child probabilities are separately returned conditional scores for the selected parent. No joint probability was derived, and these scores are not assumed comparable to FLAT probabilities. This run uses raw choices without confidence/probability thresholds.

Reported costs: FLAT 0.000745374 OpenRouter credits; TOPDOWN 0.0004095; total 0.001154874. Input/output tokens: 27,497/3,613 total. Sum of measured request latencies: 4.697 seconds (FLAT 2.038; TOPDOWN 2.659), excluding local setup and report generation. These are observations from a single small run, not reliable cost, latency, calibration or accuracy estimates.

## Frozen 30-line pilot extension

The user subsequently authorized the remaining 24 lines and an offline A/B/C1/C2 comparison. That extension is complete. Taxonomy, descriptions, existing prompts, dataset and decision policies were frozen before those calls and verified unchanged. See results/taxonomy-v2/pilot-30/findings.md for the concise report, comparison_report.md for all threshold tables, and freeze_manifest.json for hashes and protocol provenance. The earlier six-line diagnostic artifacts and v1 results remain unchanged. No additional calls are authorized by this completed run.
