# Jev taxonomy-v2 exploratory 30-line pilot

Frozen taxonomy, descriptions, prompts and evaluation policies. Six prior diagnostic receipts reused exact cached calls; only the remaining 24 received new requests. No v1 results used.

## Policies and denominators

- **A:** Force argmax of 27 raw FLAT leaf probabilities; ignore specials; never renormalize; ties use frozen taxonomy order. Not a separately prompted forced-leaf model.
- **B:** Respect FLAT selected option. unidentifiable abstains; out_of_scope rejects only above threshold; selected leaf commits only above threshold.
- **C1:** Sum raw FLAT leaf probabilities per parent, preserving special-option mass. Choose argmax among parent sums and specials. For a qualifying parent return its highest-probability leaf if that raw leaf probability also qualifies, otherwise the parent. unidentifiable abstains; out_of_scope is separate rejection. No renormalization.
- **C2:** Respect TOPDOWN parent choice. unidentifiable abstains; out_of_scope rejects only above threshold. A parent below threshold abstains. Otherwise unspecified_child retains parent; selected child qualifies on its conditional probability or falls back to parent. No joint probability is inferred.
- **specials:** unidentifiable is abstention; out_of_scope is separate scope rejection; unspecified_child retains a committed parent, including an erroneous parent on insufficient-information cases.
- **coverage:** Taxonomy parent/leaf commitments divided by 30, including errors and overclaims. Scope rejections excluded and reported separately.
- **accuracy:** (correct_leaf + correct_parent) / taxonomy commitments; does not imply equal specificity. Error rate includes wrong taxonomy decisions and overclaims. Undefined for zero denominator.

C2 uses separate parent and conditional-child thresholds, not a calibrated joint probability. Equal numerical thresholds across C1/C2 do not imply equal confidence. Model confidence is recorded but not used as a probability threshold.

## Actual counts across all 30 receipts

Errors below are wrong taxonomy commitments plus overclaims. Scope correctness/errors are separate. Correct leaves and parents must remain separate when comparing specificity.

| Method | t | Correct leaf | Correct parent | Taxonomy errors | Overclaims within errors | Leaf/parent commits | Abstain | Scope correct/wrong | Taxonomy coverage | Classification accuracy |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: |
| A | forced | 20 | 0 | 10 | 3 | 30/0 | 0 | 0/0 | 100.0% | 66.7% |
| B | 0.5 | 18 | 0 | 0 | 0 | 18/0 | 11 | 1/0 | 60.0% | 100.0% |
| B | 0.7 | 17 | 0 | 0 | 0 | 17/0 | 12 | 1/0 | 56.7% | 100.0% |
| B | 0.85 | 15 | 0 | 0 | 0 | 15/0 | 14 | 1/0 | 50.0% | 100.0% |
| B | 0.95 | 12 | 0 | 0 | 0 | 12/0 | 17 | 1/0 | 40.0% | 100.0% |
| B | 0.99 | 5 | 0 | 0 | 0 | 5/0 | 24 | 1/0 | 16.7% | 100.0% |
| C1 | 0.5 | 18 | 0 | 0 | 0 | 18/0 | 11 | 1/0 | 60.0% | 100.0% |
| C1 | 0.7 | 17 | 0 | 0 | 0 | 17/0 | 12 | 1/0 | 56.7% | 100.0% |
| C1 | 0.85 | 15 | 0 | 0 | 0 | 15/0 | 14 | 1/0 | 50.0% | 100.0% |
| C1 | 0.95 | 12 | 0 | 0 | 0 | 12/0 | 17 | 1/0 | 40.0% | 100.0% |
| C1 | 0.99 | 5 | 0 | 0 | 0 | 5/0 | 24 | 1/0 | 16.7% | 100.0% |
| C2 | 0.5 | 17 | 4 | 0 | 0 | 17/4 | 8 | 1/0 | 70.0% | 100.0% |
| C2 | 0.7 | 14 | 5 | 0 | 0 | 14/5 | 10 | 1/0 | 63.3% | 100.0% |
| C2 | 0.85 | 12 | 5 | 0 | 0 | 12/5 | 12 | 1/0 | 56.7% | 100.0% |
| C2 | 0.95 | 5 | 6 | 0 | 0 | 5/6 | 18 | 1/0 | 36.7% | 100.0% |
| C2 | 0.99 | 1 | 4 | 0 | 0 | 1/4 | 24 | 1/0 | 16.7% | 100.0% |

Machine-readable threshold_summary.json also records classification and non-abstaining error rates, leaf-commit share, merchandise/adjustment commitments, and false commitments on insufficient-information rows.

## Parent-only, insufficient-information and out-of-scope cases

These raw choices are shown without a threshold, exposing explicit model abstention/parent retention before threshold effects.

| ID / receipt | Ground truth | FLAT raw choice (p) | TOPDOWN raw result (parent p; child choice/p) | FLAT parent mass / unidentifiable mass |
| --- | --- | --- | --- | --- |
| 08 ART 004711 | INSUFFICIENT_INFORMATION | unidentifiable (0.99) | abstain (1; not called) | n/a / 0.99 |
| 19 USB-C KABEL 1M | OUT_OF_SCOPE | out_of_scope (0.99) | out_of_scope (1; not called) | n/a / 0.01 |
| 24 MOLKEREI ART | PARENT_ONLY:dairy_eggs | unidentifiable (0.93) | dairy_eggs (0.94; unspecified_child/0.97) | 0.06 / 0.93 |
| 25 OBST/GEMUESE | PARENT_ONLY:produce | unidentifiable (0.99) | produce (0.96; unspecified_child/0.99) | 0.01 / 0.99 |
| 26 GETRAENKE | PARENT_ONLY:beverages | unidentifiable (1) | beverages (1; unspecified_child/1) | 0 / 1 |
| 27 HAUSHALTSWARE | PARENT_ONLY:household | unidentifiable (0.98) | household (0.99; unspecified_child/1) | 0.02 / 0.98 |
| 28 DIVERSES | INSUFFICIENT_INFORMATION | unidentifiable (0.99) | abstain (0.97; not called) | n/a / 0.99 |
| 29 AKTION 1 | INSUFFICIENT_INFORMATION | unidentifiable (1) | abstain (0.99; not called) | n/a / 1 |

## Error and high-score audit

No raw-choice taxonomy errors, overclaims or false scope rejections were observed. This is not evidence they cannot occur.
A forced 10 erroneous/overclaim leaf commitments. 5 had zero returned probability for the selected leaf; 6 involved a leaf tie. These are offline policy artifacts, not confident model mistakes. Tie-breaking uses frozen taxonomy order.

## Structural interpretation

C1 versus B isolates aggregation/fallback on the same FLAT responses. Parent sums retain original probability mass: unidentifiable/out_of_scope mass is never redistributed among products. High FLAT unidentifiable probability can prevent any parent from qualifying, even when receipt text supports a parent.
C2 asks a different parent question and offers unspecified_child explicitly in a second question. Parent retention may therefore come from a different output space, different probability allocation, or an explicit unspecified_child selection, not FLAT probability aggregation. Conditional child scores can be high inside a weak or incorrect parent; parent thresholds are enforced separately.

- t=0.5: C1 recovers parent information over B abstention on IDs []; C2 does so on IDs ['24', '25', '26', '27'].
- t=0.7: C1 recovers parent information over B abstention on IDs []; C2 does so on IDs ['24', '25', '26', '27'].
- t=0.85: C1 recovers parent information over B abstention on IDs []; C2 does so on IDs ['24', '25', '26', '27'].
- t=0.95: C1 recovers parent information over B abstention on IDs []; C2 does so on IDs ['17', '25', '26', '27'].
- t=0.99: C1 recovers parent information over B abstention on IDs []; C2 does so on IDs ['01', '26', '27'].

## Observed API usage and latency

Totals include the six diagnostic receipts once, using their original cached measurements. Threshold replay incurs no model calls. Costs below are returned OpenRouter credits; missing usage is reported explicitly rather than estimated.

| Calls | Requests | Input tokens | Output tokens | Cost credits | Sum latency s | Median request latency s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| FLAT | 30 | 88719 | 12580 | 0.003726198 | 9.451 | 0.233 |
| TOPDOWN | 51 | 49562 | 5619 | 0.002081604 | 14.686 | 0.231 |

Collection: 65 new requests in the collection execution; 16 original cache records reused. Returned models: ['typesafe/jev-1.14-20261014'].

## Limits

This hand-built 30-line pilot has 22 leaf-supported, four parent-only, three insufficient-information and one out-of-scope case. It is neither a random sample nor a held-out test: the first six cases already informed the diagnostic design. Some leaves have no examples. The coconut-milk label remains a proposed culinary interpretation. No prompts, descriptions, labels, thresholds or policies were tuned to the remaining results. No statistical significance, reliable calibration or production accuracy is claimed.
