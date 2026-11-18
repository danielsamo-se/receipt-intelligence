# Jev 30-line pilot: concise findings

Completed 65 new requests for the remaining 24 receipt lines. Reused all 16 six-line diagnostic records byte-for-byte: 81 unique successful requests in total (30 FLAT, 30 TOPDOWN parent, 21 TOPDOWN child). All returned typesafe/jev-1.14-20261014. Full probabilities, confidence, measured latency, usage and cost are cached. Taxonomy v2, descriptions, prompts, dataset and offline policies were hash-frozen before collection and verified afterward. Historical v1 results are separate and unchanged.

## Comparison

Coverage below is taxonomy parent/leaf commitments / 30, excluding scope rejection. Errors include overclaims. B/C1/C2 each correctly reject the one out-of-scope cable at every threshold; this is separate from classification success and abstention.

| Method | Threshold | Correct leaf | Correct parent | Errors | Within-parent overclaims included in errors | Abstentions | Taxonomy coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | forced | 20 | 0 | 10 | 3 | 0 | 100.0% |
| B and C1 | 0.5 | 18 | 0 | 0 | 0 | 11 | 60.0% |
| B and C1 | 0.7 | 17 | 0 | 0 | 0 | 12 | 56.7% |
| B and C1 | 0.85 | 15 | 0 | 0 | 0 | 14 | 50.0% |
| B and C1 | 0.95 | 12 | 0 | 0 | 0 | 17 | 40.0% |
| B and C1 | 0.99 | 5 | 0 | 0 | 0 | 24 | 16.7% |
| C2 | 0.5 | 17 | 4 | 0 | 0 | 8 | 70.0% |
| C2 | 0.7 | 14 | 5 | 0 | 0 | 10 | 63.3% |
| C2 | 0.85 | 12 | 5 | 0 | 0 | 12 | 56.7% |
| C2 | 0.95 | 5 | 6 | 0 | 0 | 18 | 36.7% |
| C2 | 0.99 | 1 | 4 | 0 | 0 | 24 | 16.7% |

A is the offline forced argmax among the cached 27 leaf probabilities, ignoring both special options; it is not a separately prompted leaf-only model. It commits 30 leaves, gets 20 correct, makes seven wrong-category decisions and three overclaims: 66.7% classification accuracy and 33.3% error rate. Five errors use a zero-probability leaf, and six errors involve ties; deterministic tie-breaking is an artifact of forcing a decision, not confident evidence.

B, C1 and C2 have no observed erroneous taxonomy commitments, overclaims or false scope rejections at these thresholds. Their committed-classification accuracy is therefore 100% in this sample, alongside substantial abstention and different specificity. Abstentions are never credited as correct classifications. The leaf/parent counts above also give their committed specificity because there are no errors; A still commits 30 leaves despite only 20 being correct.

## Important cases and failures to automate

- All four parent-only lines (24 MOLKEREI ART, 25 OBST/GEMUESE, 26 GETRAENKE, 27 HAUSHALTSWARE): B and C1 abstain. At thresholds 0.50-0.85, C2 returns all four correct parents through explicit unspecified_child. At 0.95 it retains three of these four; at 0.99 it retains two. These are parent successes, not leaf successes. Forced A asserts a leaf on all four parent-only lines: three within-parent overclaims and one wrong-parent leaf (GETRAENKE -> produce.fruit). Under the frozen outcome partition, the latter is counted as wrong_category, not double-counted as overclaim; all four assertions are unjustifiably specific.
- All three insufficient-information lines (08 ART 004711, 28 DIVERSES, 29 AKTION 1): B/C1/C2 abstain at every threshold. A commits unsupported leaves on all three.
- 24 MOLKEREI ART: FLAT puts 0.93 on unidentifiable and only 0.06 total on dairy leaves; C1 cannot manufacture parent support by redistribution. TOPDOWN independently puts 0.94 on dairy_eggs and 0.97 on unspecified_child. Forced A chooses milk_cream at only 0.04, an overclaim.
- 03 WMF PF 24CM: FLAT gets kitchenware at 0.96. TOPDOWN gives household only 0.69, followed by conditional kitchenware probability 0.84. C2 consequently abstains from threshold 0.70 upward while B/C1 still classify correctly at 0.95. Parent gating can lose useful leaf automation.
- 22 WC REIN ZITR: FLAT correctly selects cleaning_supplies at 0.58, so B/C1 classify it at 0.50. TOPDOWN selects unidentifiable at 0.39 and abstains. The structural hierarchy does not improve every example.
- BIO ZITR 500G, GRIECH JOG NAT, POM-BAER ORIGINAL and PRINZEN ROLLE receive explicit unidentifiable from both raw methods despite the proposed leaf labels. These are missed automation opportunities, not incorrect committed classifications. Forced A incorrectly calls POM-BAER a sweet biscuit at 0.05 and PRINZEN ROLLE bread/bakery at 0.20; these are low-probability forced outputs.
- No confidently incorrect raw product/adjustment commitment was observed. The audit checks returned selected probabilities and confidence of at least 0.90, separately labeling conditional child scores; high confidence on an abstention is not a confident product misclassification.

## What the hierarchy contributes

C1 and B produce exactly the same decisions at all five frozen thresholds. Aggregation alone recovered no additional information here. FLAT was explicitly prompted to abstain when no leaf is justified, so substantial probability can go to unidentifiable even when a parent is clear. That mass is not available for parent sums and was not renormalized away.

C2 has a different question/output space: first classify a parent, then explicitly choose a child or unspecified_child. Its parent-retention gain therefore reflects that structure and independently elicited probabilities, not FLAT probability aggregation. C2 can also lose specificity or coverage through parent gating: at 0.95 it commits 5 leaves and 6 parents (36.7% coverage), versus B/C1's 12 leaves (40%). At 0.99 both cover 16.7%, but C2 supplies only one leaf versus five for B/C1. Equal numerical thresholds do not mean equally calibrated support: C2 child probabilities are conditional, not FLAT probabilities or a joint score.

## Observed resource use

| Method | Requests | Input/output tokens | Returned cost, OpenRouter credits | Sum request latency |
| --- | ---: | ---: | ---: | ---: |
| FLAT | 30 | 88,719 / 12,580 | 0.003726198 | 9.451 s |
| TOPDOWN | 51 | 49,562 / 5,619 | 0.002081604 | 14.686 s |

Total returned cost including the reused diagnostic once: 0.005807802 credits. Newly incurred cost for the remaining 24 lines: 0.004652928 credits. No token, cost, probability or confidence fields were missing. Latency totals sum measured HTTP request times, not local setup or report-generation time; TOPDOWN includes multiple requests. Threshold replay was entirely offline.

## Practical reading and limits

The pilot supports investigating parent retention further, particularly for department-only text. It does not show that aggregation by itself helps, and the explicit abstention prompts appear conservative on several recognizable products. A larger, independently labeled and held-out sample is needed before choosing an operating threshold. No production accuracy, calibration or statistical significance is claimed. The data are synthetic/proposed labels, include only one out-of-scope case, leave some categories unrepresented, and the first six cases had already been inspected before this extension. No prompts, descriptions, dataset labels or policies were changed after collection started.

The detailed report is comparison_report.md; full per-line/per-threshold decisions are offline_decisions.json; the exact pre-collection scoring protocol and prompts are under frozen/. Stop after this report; no further calls are part of this run.
