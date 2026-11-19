# Final product quality sprint

Branch: `sprint/product-quality-hierarchy`. Frozen responses, taxonomy v2, synthetic labels, prompts, Product Memory catalog/evaluation data and prior findings remain unchanged. No Jev requests, new models, databases or infrastructure were added.

## Main comparison and safeguards

The merchant toggle now uses **One-shot Hierarchical** (`ONE_SHOT`, experiment D) and **Two-stage Hierarchical** (`TWO_STAGE`, experiment TOPDOWN). Both faithfully implement the follow-up's **raw selected choices without thresholds**. The former dashboard SAFE 0.85 policy is a different historical configuration, retained unchanged for technical evidence/API compatibility, alongside **Naive Forced Baseline**. Neither historical method is offered as a merchant toggle.

All 54 inputs have complete paired caches: 30 original and 24 additional. Cache loading validates input state, model, full Choice distributions and exact frozen question configurations. A missing/invalid D or required TOPDOWN response excludes that receipt from **both** comparison cohorts. No unavailable result enters a success/error/abstention denominator; the operational view also discloses excluded count/value rather than comparing different sales populations.

The comparison is not a controlled proof that topology alone causes a difference:

- D has 39 options: 27 leaves, ten parent-only actions and two specials. Its longer prompt repeats parent scopes.
- TOPDOWN has 12 initial options and then conditional child options including `unspecified_child`. Specials end the sequence. Its frozen wording and prompt length differ from D.
- Both use taxonomy v2 and the original descriptions. No thresholds or prompts were changed to improve a result.
- D parent-only scores describe exclusive resolution actions. TOPDOWN broad-parent scores and conditional-child scores are different quantities. Neither scores nor the returned confidence field are calibrated correctness probabilities.
- Original TOPDOWN latency is historical/noncontemporaneous; additional-set method order alternated. Recorded costs are returned OpenRouter credits, not measured production savings.

`evaluation.py` recomputes outcomes and usage from validated caches with separate synthetic sets. Its values match the frozen `combined_summary.json`. Merchant corrections and Product Memory never enter this evaluation. Taxonomy counts include adjustment classifications; operational product-category revenue excludes adjustments.

## Actual results

Category errors include overclaims. Scope rejection errors are separate. Coverage denominator is the paired set; classification accuracy denominator is committed taxonomy categories, including erroneous commitments.

| Matched set | Method | Correct leaf | Correct parent | Category errors | Abstentions | Scope correct/wrong | Coverage | Accuracy on category commits |
|---|---|---:|---:|---:|---:|---:|---|---|
| Original 30/30 | One-shot D | 19 | 4 | 1 | 5 | 1/0 | 24/30 (80%) | 23/24 (95.8%) |
| Original 30/30 | Two-stage TOPDOWN | 17 | 4 | 0 | 8 | 1/0 | 21/30 (70%) | 21/21 (100%) |
| Additional 24/24 | One-shot D | 12 | 1 | 2 | 6 | 2/1 | 15/24 (62.5%) | 13/15 (86.7%) |
| Additional 24/24 | Two-stage TOPDOWN | 11 | 3 | 1 | 7 | 2/0 | 15/24 (62.5%) | 14/15 (93.3%) |

| Set | Method | Requests | Input/output tokens | Returned credits | Median serial receipt latency |
|---|---|---:|---|---:|---:|
| Original 30 | D | 30 | 130,989 / 15,435 | 0.005501538 | 0.256 s |
| Original 30 | TOPDOWN | 51 | 49,562 / 5,619 | 0.002081604 | 0.447 s |
| Additional 24 | D | 24 | 104,853 / 12,346 | 0.004403826 | 0.245 s |
| Additional 24 | TOPDOWN | 39 | 38,502 / 4,362 | 0.001617084 | 0.444 s |

All reported usage and latency fields are present in these caches. Per-receipt TOPDOWN latency sums serial parent/child requests; it is not the median individual-request latency. Missing fields, if encountered, remain missing and have explicit missing counts.

Important observed differences:

- `MOLKEREI ART`: both retain Dairy & eggs. D parent-only score 0.63; TOPDOWN broad-parent 0.94 then `unspecified_child` 0.97. No specific product identity is invented, and no numerical score comparison implies greater reliability.
- `PRINZEN ROLLE`: D commits to bread/bakery at raw score 0.47, incorrectly against the frozen biscuit label; TOPDOWN abstains. Raw-choice category errors can escape the state-based review queue.
- `KARTOFFELGRATIN 400`: both raw methods overclaim a leaf against the cautious parent-only label. TOPDOWN parent score 0.94 does not verify its selected child at 0.54. Historical SAFE would retain the parent at its 0.85 gate; the new primary comparison deliberately does not insert that gate.
- `NASCHBOX MIX 300G` and `TISCHDEKO SORTIERT`: TOPDOWN retains parents; D overclaims the snack leaf or incorrectly rejects table decoration as out of scope. These few coarse/debatable synthetic labels do not establish universal superiority.

No pooled headline accuracy is used. The 54 examples are synthetic and not independently adjudicated merchant ground truth. Proposed parent labels, class balance and prompt design affect these observations. No significance, calibration or production-accuracy claim is justified.

## Product clarity fixes

- The Inspector starts with final outcome, specificity and source, followed by **Receipt input → Product Memory → Jev assessment → Policy → Final outcome**.
- Model outputs, deterministic policy rules, merchant catalog mappings and exact-line overrides are identified separately. Full probabilities, raw responses and hashes remain available in collapsed disclosures. No internal model reasoning is invented.
- New inputs with no cache say **Needs verification**. The technical detail says **No cached Jev response available in offline demo. No live model call was made.** This is missing evidence, not low confidence.
- The review queue identifies the selected method and ranks its own parent-only/verification-required merchandise states by stored synthetic quantity × price. It is not an independent risk model. Confirmed mappings leave the queue; scope rejections are separate and can contribute to unassigned value without becoming review items. Parent-only value remains categorized at parent level while still reviewable.
- Dashboard totals are operational synthetic sales, not evaluation correctness. Evaluation ignores mutable feedback. Merchant confirmations do not establish general model accuracy or independent ground truth.
- The prior Product Memory development evaluation is preserved and explicitly labeled **historical SAFE at 0.85**. Its scripted confirmations and unavailable model-only caches are not reinterpreted as new primary-method results or measured savings.

## Restart

Stop your existing Receipt Intelligence backend with Ctrl+C in its terminal. From PowerShell:

```powershell
# Run from the repository root.
powershell -NoProfile -ExecutionPolicy Bypass -File .\app\build-frontend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\app\start-backend.ps1
```

Open **http://127.0.0.1:8000** and hard-refresh. This serves the built UI and API from one local process. If using Vite for development, start `app/start-frontend.ps1` separately and open port 5173. Dependency setup and optional local embedding preparation remain documented in README/Product Memory. No internet is needed in the prepared workspace.

## 2–3 minute presentation

1. **0:00–0:30 — Sales and scope.** Initial 30 examples; switch One-shot → Two-stage. Point out the same 30/30 paired inputs, same synthetic quantities, three specificity totals and one updated chart. More specific value is not automatically more correct.
2. **0:30–1:05 — Uncertainty.** Search review for `MOLKEREI`, open it. Both methods retain Dairy, and Two-stage selected `unspecified_child`. Show the prominent parent-only outcome and provenance; open probabilities only if asked. If demonstrating an exact-line correction, select Yogurt & quark as an explicit merchant assertion, observe the report/queue change, then undo; do not claim the receipt text identified yogurt.
3. **1:05–2:15 — Product Memory.** Close the drawer, expand **Process a new POS description**, process the unknown yogurt alias. It needs verification because the offline demo has no cache, not because of a returned low score. Show lexical/semantic suggestions and the identity-check requirement. Confirm `SYN-104` after the simulated catalog check. Close and process the same alias again; a new receipt reuses the mapping. Show merchant-scoped provenance/audit, then reverse. This does not add weekly revenue or demonstrate measured API savings.
4. **2:15–2:45 — Engineering/evidence.** Optionally run the six-event replay or open Evaluation evidence. State that both architectures have trade-offs; costs/latencies are historical, and the synthetic samples are exploratory. The prototype extends normalization/review workflows; it does not replace anybill production infrastructure.

If an operational alias was confirmed earlier, inspect and reverse it before demonstrating the unknown state. Never delete audit history or mutate frozen labels to reset the story.

## Verification and remaining challenges

The original **42 backend tests passed before edits** and remain unchanged/passing. **49 tests pass** after adding seven targeted checks covering all 108 D/TOPDOWN decisions, raw-policy versus old threshold semantics, matched cohort exclusion, exact frozen prompt validation, metric/cost/latency reconciliation, selected-method review states and Product Memory precedence. Production TypeScript/Vite build passed.

Actual browser checks passed for both primary methods, 30/30 and 24/24 cohorts, prominent inspector outcomes, collapsed distributions and full evidence access, SQLite correction → reload → undo, Product Memory confirm → new receipt reuse → reverse/reject/undo, conflicting identifier protection, unchanged weekly totals, six real WebSocket events, reset/deduplication, REST fallback, and mobile overflow/error checks. Browser public-internet requests were blocked, and tests used an isolated database on port 8001.

Integrity/credential verification checks all **144 follow-up cached responses**, **140 frozen provenance hashes**, tracked sources and the built frontend. No secret is printed. Local test servers are stopped after verification; existing user servers are not stopped automatically.

A CPTO can reasonably challenge the synthetic labels and class balance, lack of independently validated merchant data, raw leaf errors that evade state-based review, absent live-cache fallback, incomplete identifier/variant conflict rules, merchant attestation quality, and local single-worker/single-demo-merchant deployment. The Product Memory comparison has only six existing Jev-cache inputs and scripted oracle confirmations. These remain explicit limits, not reasons to fabricate performance or broaden this sprint.

The subsequent documentation submission replaces the landing README and preserves its original bytes in the documentation archive. The pre-push audit updates only the verifier's historical README lookup to that archive, retaining the original expected hash. See [documentation provenance](../docs/PROVENANCE.md); manifests, cached evidence and the quality-sprint results above remain unchanged.
