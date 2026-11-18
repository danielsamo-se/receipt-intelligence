# Focused follow-up: can one question with parent options replace TOPDOWN?

Completed the requested follow-up and stopped. Taxonomy v2, its category descriptions, original data and every previous result remain byte-identical. D has one frozen 39-option Choice question: 27 leaves, ten explicitly parent-only choices, unidentifiable and out_of_scope. Existing TOPDOWN prompts were reused exactly. Primary evaluation uses raw selected outputs, with no thresholds fitted after observing these outcomes.

## Actual classification results

Correct leaves and correct parents are separate successes at different resolutions. Category errors include overclaims; false scope rejections are shown separately. Abstentions and correct scope rejections do not count as successful product classifications. Accuracy is (correct leaves + correct parents) / committed taxonomy categories, including erroneous commitments in the denominator.

| Set | Method | Correct leaf | Correct parent | Category errors (overclaims) | Abstain | Scope correct/wrong | Taxonomy coverage | Accuracy on category commits |
| --- | --- | ---: | ---: | --- | ---: | --- | ---: | ---: |
| original30 | D | 19 | 4 | 1 (0) | 5 | 1/0 | 80.0% | 95.8% |
| original30 | TOPDOWN | 17 | 4 | 0 (0) | 8 | 1/0 | 70.0% | 100.0% |
| holdout24 | D | 12 | 1 | 2 (2) | 6 | 2/1 | 62.5% | 86.7% |
| holdout24 | TOPDOWN | 11 | 3 | 1 (1) | 7 | 2/0 | 62.5% | 93.3% |

## What changed after fixing the output-space disadvantage?

On the original 30, both methods retain all four parent-only categories. D and TOPDOWN agree on 27/30 final predictions. D additionally classifies GRIECH JOG NAT (p=0.62) and WC REIN ZITR (p=0.65) correctly, but misclassifies PRINZEN ROLLE as bread/bakery (p=0.47) where TOPDOWN abstains. Thus the earlier parent-retention advantage over leaf-only FLAT largely disappears once a single question can explicitly return parents.

On the additional 24, the methods agree on 21/24 predictions. D recovers blueberries (p=0.49) where TOPDOWN abstains. TOPDOWN has a residual restraint advantage on two cases: it retains the confectionery/snacks parent for NASCHBOX MIX, where D guesses confectionery (p=0.40), and retains household for TISCHDEKO SORTIERT, where D incorrectly rejects it as out of scope (p=0.38). The frozen taxonomy supports household wares broadly even when no listed child fits. D retains one of the four proposed parent-only truths; TOPDOWN retains three.

Both overclaim KARTOFFELGRATIN as potato_sides against the frozen parent-only label. D gives that leaf 0.45; TOPDOWN gives its parent 0.94 but the child only 0.54 (child confidence 0.31). A strong parent score does not justify finer detail. Whether this product should be treated as a conventional side is an important human-label review question; its coarse label was fixed before model calls and has not been changed to favor either method.

All three additional genuinely unidentifiable descriptions (MIXBOX, MAN. PREIS, WARE LT. ETIKETT) produce abstentions from both methods. Both correctly reject shower gel and sports socks as known exclusions. Both also abstain on recognizable soup vegetables, rapeseed oil and dishwasher tablets; this remains a missed-automation limitation, not a correct category prediction.

## Cost and latency

| Set | Method | Requests | Input/output tokens | Returned cost, OpenRouter credits | Median receipt latency |
| --- | --- | ---: | ---: | ---: | ---: |
| original30 | D | 30 | 130,989/15,435 | 0.005501538 | 0.256 s |
| original30 | TOPDOWN | 51 | 49,562/5,619 | 0.002081604 | 0.447 s |
| holdout24 | D | 24 | 104,853/12,346 | 0.004403826 | 0.245 s |
| holdout24 | TOPDOWN | 39 | 38,502/4,362 | 0.001617084 | 0.444 s |

There were 93 new calls and 51 reused historical TOPDOWN calls; all 144 compared request records returned HTTP 200. Newly incurred returned cost was 0.011522448 OpenRouter credits. Every request has a full available probability distribution, confidence, latency, tokens and cost in its cache. No missing fields were estimated.

D uses fewer serial round trips and was faster in this run. TOPDOWN was cheaper despite making more requests because its frozen prompts consume substantially fewer input tokens; the D prompt repeats category scopes across 39 options. Neither cost nor latency advantage should be treated as inherent to the architecture or stable production behavior. Original TOPDOWN timings are historical, so the new-set interleaved run is the more relevant timing comparison. On the new set, method order alternated by row before calls. No joint score was inferred from TOPDOWN stage probabilities, and D parent-only action probabilities are not directly comparable to TOPDOWN broad-parent probabilities.

## How blind and how reliable is the additional set?

The 24 inputs and separate labels were created before any follow-up model outcome, then hash-sealed with both prompt designs and the scoring protocol. Model state had only raw_text, price and merchant_type; labels were not parsed for inference or sent to Jev. The new descriptions use different products and receipt constructions, rather than substitutions of the original brands/article numbers. They include 15 leaf-supported, four parent-only, three insufficient-information and two out-of-scope cases. Inputs, proposed labels and every per-line result are supplied separately for review.

This is outcome-blind synthetic testing, not independent human-blind validation: the same assistant authored the labels and the D prompt, with knowledge of the pilot. Some parent-only truths reflect intentionally cautious labeling or missing leaf coverage (ready-to-drink coffee and table decoration). The apparent TOPDOWN advantage is partly concentrated in these few debatable/coarse cases. It warrants merchant adjudication rather than a claim of statistical significance. No labels, prompts or taxonomy were changed after outcomes.

## Prototype decision

The approach is promising enough for a review-assisted merchant-facing prototype, particularly for parent-level analytics with visible uncertainty and human correction. This follow-up does not establish a universal TOPDOWN advantage over a single question with explicit parent choices. It shows a narrower benefit in restraint and parent retention on the new set, with one fewer correct leaf but fewer unsupported decisions and lower measured token cost. D is simpler in round trips, faster here and sometimes more specific, but made additional mistakes. TOPDOWN is the safer starting candidate under these frozen prompts; D remains a credible alternative when latency matters. Choosing production thresholds or claiming production accuracy requires independently labeled merchant receipts. No UI or prototype has been built by this experiment.

Artifacts: comparison_report.md contains the detailed separate-set tables; original30/comparison.md and holdout24/comparison.md list every case; inputs/labels and D/TOPDOWN prompts are frozen under frozen/; manifest.json proves provenance. Stop here, without further calls or expansion.
