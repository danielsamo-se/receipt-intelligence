# D versus TOPDOWN: focused follow-up

Taxonomy v2 and every pre-existing result are unchanged. D has 39 explicit choices: 27 leaves, ten parent-only actions, unidentifiable and out_of_scope. TOPDOWN prompts are reused exactly, including unspecified_child. All questions, the protocol and additional labels were sealed before calls.

The additional 24 descriptions are synthetic and outcome-unseen, with labels authored by the same assistant. This is not independent human-blind ground truth. Collector state contains only raw_text, price and merchant_type; holdout labels are a separate file, hash-verified but not parsed or sent during collection.

Primary results use raw selected choices without threshold tuning. Classification accuracy uses committed taxonomy categories as denominator. Abstentions and correct scope rejections are not correct product classifications. Parent and leaf successes remain separate. TOPDOWN child probabilities are conditional; D parent-choice probabilities mean parent-only resolution and are not the same quantity as TOPDOWN broad-parent probabilities.

## original30 (30 lines)

| Method | Correct leaf | Correct parent | Taxonomy errors | Within-parent overclaims | Abstain | Scope correct/wrong | Taxonomy coverage | Committed accuracy | Parent-only cases retained |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| D | 19 | 4 | 1 | 0 | 5 | 1/0 | 80.0% | 95.8% | 4 |
| TOPDOWN | 17 | 4 | 0 | 0 | 8 | 1/0 | 70.0% | 100.0% | 4 |

Paired counts: {"identical_predictions": 27, "D_more_supported_specificity": 2, "D_only_error": 1}. Specificity ranks compare only supported correct categories or abstention; scope decisions are separate and errors are not scored as information wins.

| Method | Requests | Input/output tokens (missing counts) | Returned cost credits | Sum latency s | Median receipt latency s |
| --- | ---: | --- | ---: | ---: | ---: |
| D | 30 | 130989/15435 (0/0) | 0.005501538 (0 missing) | 9.097 | 0.256 |
| TOPDOWN | 51 | 49562/5619 (0/0) | 0.002081604 (0 missing) | 14.686 | 0.447 |

Important differences/errors (all cases are in the separate comparison.md):

- 13 GRIECH JOG NAT, truth dairy_eggs.yogurt_quark: D dairy_eggs.yogurt_quark (correct_leaf, scores [{"stage": "D", "choice": "dairy_eggs.yogurt_quark", "probability": 0.62, "confidence": 0.61}]); TOPDOWN None (abstention, scores [{"stage": "parent", "choice": "unidentifiable", "probability": 0.74, "confidence": 0.72}]).
- 20 PRINZEN ROLLE, truth confectionery_snacks.sweet_biscuits: D grains.bread_bakery (incorrect_category, scores [{"stage": "D", "choice": "grains.bread_bakery", "probability": 0.47, "confidence": 0.46}]); TOPDOWN None (abstention, scores [{"stage": "parent", "choice": "unidentifiable", "probability": 0.65, "confidence": 0.62}]).
- 22 WC REIN ZITR, truth household.cleaning_supplies: D household.cleaning_supplies (correct_leaf, scores [{"stage": "D", "choice": "household.cleaning_supplies", "probability": 0.65, "confidence": 0.64}]); TOPDOWN None (abstention, scores [{"stage": "parent", "choice": "unidentifiable", "probability": 0.39, "confidence": 0.33}]).

## holdout24 (24 lines)

| Method | Correct leaf | Correct parent | Taxonomy errors | Within-parent overclaims | Abstain | Scope correct/wrong | Taxonomy coverage | Committed accuracy | Parent-only cases retained |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| D | 12 | 1 | 2 | 2 | 6 | 2/1 | 62.5% | 86.7% | 1 |
| TOPDOWN | 11 | 3 | 1 | 1 | 7 | 2/0 | 62.5% | 93.3% | 3 |

Paired counts: {"D_more_supported_specificity": 1, "identical_predictions": 21, "both_error": 1, "D_only_error": 2}. Specificity ranks compare only supported correct categories or abstention; scope decisions are separate and errors are not scored as information wins.

| Method | Requests | Input/output tokens (missing counts) | Returned cost credits | Sum latency s | Median receipt latency s |
| --- | ---: | --- | ---: | ---: | ---: |
| D | 24 | 104853/12346 (0/0) | 0.004403826 (0 missing) | 6.012 | 0.245 |
| TOPDOWN | 39 | 38502/4362 (0/0) | 0.001617084 (0 missing) | 9.195 | 0.444 |

Important differences/errors (all cases are in the separate comparison.md):

- H01 BLAUBEEREN SCHALE 125, truth produce.fruit: D produce.fruit (correct_leaf, scores [{"stage": "D", "choice": "produce.fruit", "probability": 0.49, "confidence": 0.48}]); TOPDOWN None (abstention, scores [{"stage": "parent", "choice": "unidentifiable", "probability": 0.64, "confidence": 0.61}]).
- H16 KARTOFFELGRATIN 400, truth PARENT_ONLY:prepared_food: D prepared_food.potato_sides (overclaim, scores [{"stage": "D", "choice": "prepared_food.potato_sides", "probability": 0.45, "confidence": 0.44}]); TOPDOWN prepared_food.potato_sides (overclaim, scores [{"stage": "parent", "choice": "prepared_food", "probability": 0.94, "confidence": 0.93}, {"stage": "child", "choice": "prepared_food.potato_sides", "probability": 0.54, "confidence": 0.31}]).
- H17 NASCHBOX MIX 300G, truth PARENT_ONLY:confectionery_snacks: D confectionery_snacks.confectionery (overclaim, scores [{"stage": "D", "choice": "confectionery_snacks.confectionery", "probability": 0.4, "confidence": 0.38}]); TOPDOWN confectionery_snacks (correct_parent, scores [{"stage": "parent", "choice": "confectionery_snacks", "probability": 0.77, "confidence": 0.75}, {"stage": "child", "choice": "unspecified_child", "probability": 0.66, "confidence": 0.55}]).
- H19 TISCHDEKO SORTIERT, truth PARENT_ONLY:household: D out_of_scope (incorrect_scope_rejection, scores [{"stage": "D", "choice": "out_of_scope", "probability": 0.38, "confidence": 0.36}]); TOPDOWN household (correct_parent, scores [{"stage": "parent", "choice": "household", "probability": 0.56, "confidence": 0.52}, {"stage": "child", "choice": "unspecified_child", "probability": 0.8, "confidence": 0.7}]).

## Interpretation boundaries

D directly addresses the pilot's output-space disadvantage: it can retain a parent in a single question. Any additional TOPDOWN benefit must now appear in actual paired correctness or specificity, not merely its ability to output parents. This experiment compares complete question designs, not calibrated equivalent probability scales or pure topology alone.
D has a longer 39-option prompt; one call does not guarantee lower token cost. TOPDOWN has serial parent/child round trips but shorter questions. Compare actual returned usage and per-receipt latency. Original TOPDOWN timing is cached/historical; holdout requests alternate which method runs first. Neither timing sample establishes stable production latency.
The new set is synthetic and outcome-blind, not independently labeled or statistically representative. Parent-only labels for gratin, mixed snack boxes, ready-to-drink coffee and table decoration deliberately avoid unsupported precision; some reflect missing leaf coverage within a supported parent. These proposed labels need merchant review. No prompts or labels were changed after seeing outcomes. Results are separated from original30 and no significance or reliable calibration is claimed.
