# Merchant Product Memory

An extension of the existing Receipt Intelligence application, not a replacement classifier or a new Jev experiment. The merchant catalog, receipt inputs and evaluation are explicitly synthetic. No live Jev requests or embedding API calls are made.

## Try the end-to-end flow

Start the application using the existing [README commands](README.md#start-the-application). In the prepared workspace the model and built frontend are already available offline. A running backend must be restarted after pulling these local changes.

1. On Category Analytics, expand **Process a new POS description**. Keep **Unknown yogurt alias**: `ERDBEER JOGHURT NM 150 G`, €0.79. Click **Process description**.
2. The Decision Inspector prominently shows **Needs verification**, then **No trusted mapping**, lexical/semantic suggestions and the technical reason: **No cached Jev response available in offline demo. No live model call was made.** Missing demo evidence does not mean low model confidence.
3. Examine `SYN-104`, Nordmarkt Erdbeerjoghurt 150 g. For this synthetic demonstration, act as the merchant checking the actual catalog: tick **I checked this exact product in the merchant catalog**, then **Confirm product**. The checkbox is a merchant attestation, not independent validation.
4. The outcome immediately becomes **Product memory**. Canonical identifier, confirmed classification, merchant/POS scope, timestamp, confirmation evidence and audit entry are inspectable. The cached model stage is bypassed.
5. Close the Inspector, reload, and process the same description again. This creates a distinct stored receipt and reuses the exact confirmed alias. Both One-shot and Two-stage Hierarchical honor merchant knowledge, as do the preserved historical policies. No Jev request is needed or made.
6. **Reverse confirmation** revokes that alias for future decisions while keeping its audit event. **Not this product** persists a candidate rejection for the exact alias/product scope; **Undo rejection** restores the possibility of review.

Other synthetic presets demonstrate **Known merchant SKU** (`SKU-104`) and **Identifier / variant conflict**: `CC ZERO 1L` paired with original-cola `SKU-106`. The latter stays unresolved even though the zero-cola alias matches exactly. A 500 g yogurt cannot reuse the 150 g identity.

One-off inputs are persisted separately and excluded from weekly revenue and replay totals. They do not modify any original CSV, evaluation label, sales quantity, cached response, prompt or taxonomy. Exact scoped aliases confirmed for an original receipt can affect operational analytics through the same decision service, while frozen evaluation reports remain unchanged.

## Cascade and matching scope

1. An active merchant correction for the exact receipt-line ID wins.
2. A confirmed merchant/POS identifier, or exact confirmed alias, may supply its catalog classification if safety checks pass.
3. Otherwise hybrid retrieval produces up to three suggestions. The selected frozen One-shot or Two-stage Hierarchical policy supplies a category where an identical complete input cache exists; otherwise the status is Needs verification. Historical FORCED/SAFE are retained only for technical evidence/API compatibility.

Canonical products and classifications are merchant-scoped in the existing SQLite file. Identifiers are unique within `(merchant, POS namespace, identifier)`. Aliases are unique within `(merchant, POS namespace, merchant type, normalized receipt text)`. Normalization uses Unicode NFKC, case folding and whitespace collapsing only: it retains punctuation, word order, units, numbers and distinguishing variants. `1L` and `1 L` are separate identities until individually confirmed, although retrieval can suggest their relationship.

Similarity never creates or updates an identity mapping. A confirmed mapping bypasses model classification rather than changing prompts or recomputing cached responses. Parent classifications remain parent-level. Historical SAFE 0.85 rules, abstention/scope behavior, exact-line override workflow and WebSocket replay are preserved; the main methods now faithfully replay the frozen follow-up's raw selected actions without thresholds.

Guards reject explicit pack/diameter, family, brand and variant conflicts, merchandise/adjustment confusion, conflicting confirmed identifier/alias pairs and unknown supplied identifiers. An alias missing catalog pack size or distinguishing variant cannot be confirmed as a reusable product identity. Opaque or generic descriptions cannot create broad aliases. A verified identifier can resolve an opaque description, provided the text has no explicit contradiction.

These guards are conservative demonstration rules, **not a complete identity resolution system**. POS namespaces must be assigned correctly; the prototype does not detect SKU recycling, barcode fraud, every German abbreviation or all possible product variants. A merchant can still make a mistaken attestation; reversal is available, and no confirmation becomes independent evaluation ground truth.

## Persistence and audit

`memory_store.py` adds tables to the same SQLite database as the existing corrections/replay infrastructure: canonical products, scoped identifiers, active aliases, append-only product review events, active review pointers and one-off receipt inputs. No additional database server is introduced.

The eight catalog products are imported idempotently from `data/product_memory_catalog.json`, with a source declaring synthetic confirmation assumptions and UTC import timestamps. Product IDs such as `SYN-104` and identifiers such as `SKU-104` are fictional merchant identifiers, not real GTINs. Runtime startup never replaces a merchant-confirmed alias or reseeds a reversed confirmation.

Confirm/reject/reverse writes are transactional. A confirmation records the receipt input, candidate scores, embedding revision, original structured classification, merchant attestation, optional note and timestamp. Reversal removes the active alias/review pointer while retaining the original evidence. Receipts processed before confirmation are not rewritten; future decisions resolve against current merchant knowledge, and audit events preserve the earlier decision snapshot. Exact-line corrections continue to retain their separate original-model snapshot and now record the pre-correction memory outcome as applicable.

REST remains authoritative. Product review writes emit merchant-scoped WebSocket notifications to refresh analytics; all review operations also work without the socket. One fictional merchant is exposed by the demo API, with isolation enforced in storage and covered in tests. This is not an authenticated multi-tenant deployment.

## Embeddings and hybrid ranking

The local model is **intfloat/multilingual-e5-small**, pinned to revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`, with the publisher's quantized ONNX weights and tokenizer checksummed in `data/embedding_model.json`. It produces 384-dimensional normalized embeddings on CPU using ONNX Runtime and tokenizers; attention-mask mean pooling and `query:` / `passage:` prefixes follow the [publisher's model card](https://huggingface.co/intfloat/multilingual-e5-small). Its [published ONNX files](https://huggingface.co/intfloat/multilingual-e5-small/tree/614241f622f53c4eeff9890bdc4f31cfecc418b3/onnx) avoid a PyTorch installation. License: MIT.

The model supports multilingual text including German, making it a reasonable general-purpose starting point for these short descriptions. It is **not trained or validated specifically for German POS identity resolution**. Abbreviations, numbers, brands, negation and near-identical variants are weaknesses; high cosine is not equivalence. Local input length is capped at 128 tokens for this short-description workflow.

Lexical retrieval combines character trigrams and token overlap. Ranking uses fixed weights of 0.6 lexical / 0.4 raw semantic cosine, with up to three candidates. These ranking weights and the development cases were written before recording the evaluation; they were not optimized against its outcomes. Cosines and ranking scores are not probabilities or calibrated confidence values. A bounded local vector cache and a linear cosine scan over the tiny merchant catalog suffice; SQLite stores business knowledge, not a separate vector database.

Runtime never downloads models or calls Hugging Face. If local embedding assets are missing, the Inspector explicitly reports lexical-only retrieval and the cached model/review fallback remains available. For a fresh machine, install the pinned runtime dependencies, then explicitly download and verify approximately 135 MB once:

```powershell
# Run from the repository root.
.\.venv\Scripts\python.exe -m pip install -r app/backend/requirements-dev.txt
.\.venv\Scripts\python.exe -B app/tools/prepare_embeddings.py
```

Weights remain in ignored `app/.local/embeddings/`. Canonical product and query vectors are computed locally and cached in memory. No receipt text is sent off-device. This feature is **product retrieval and confirmed mapping reuse**, not RAG: retrieved evidence is not incorporated into model inference.

## Compact synthetic evaluation

Source: `data/product_memory_evaluation_cases.json`; actual recorded results and per-case candidate scores: `data/product_memory_evaluation_results.json`. This earlier Product Memory development check remains unchanged and explicitly uses **historical SAFE at 0.85**, not the new raw-choice D/TOPDOWN comparison. The secondary **Evaluation evidence** view displays the same data. Inputs, catalog and embedding lock hashes are recorded.

| Pipeline, 24 cases | Exact identities | Wrong identities | Correct leaf | Correct parent | Review required | Jev-stage bypasses |
|---|---:|---:|---:|---:|---:|---:|
| Existing cached SAFE only | 0 | 0 | 2 | 1 | 22 | 0 |
| Memory before new review | 6 | 0 | 8 | 1 | 16 | 6 |
| Repeat after scripted catalog review | 12 | 0 | 14 | 1 | 10 | 12 |

Initial mappings comprise three exact aliases and three known identifiers. Six eligible new-alias suggestions were retrieved in the top three and then accepted by a **scripted oracle** using stipulated synthetic catalog identities. These are not observed human acceptances, an independent test set or autonomous matching successes. Wrong or unsupported identity suggestions are never auto-accepted.

Only **six cases have real cached Jev responses**. The other 18 model-only results are explicitly unavailable; no new inference was run. Consequently this comparison demonstrates reuse and review mechanics, **not superiority over live Jev on unseen descriptions**. Both present pipelines make zero Jev requests. Actual model calls avoided and API costs are **zero**; Jev-stage bypass counts indicate where a future live fallback could be skipped, not measured production savings. Local CPU cost is unmeasured.

The median recorded local durations were approximately 0.86 ms for cache-only processing, 8.68 ms for initial memory processing and 3.16 ms for repeat processing across this small mixed set. They exclude encoder startup, include differing decision paths, and are not a controlled production latency benchmark. Retrieval adds local work; no speedup over a simple file cache is claimed.

Important false-positive examples: `WMF PFANNE 28CM` retrieved the 24 cm pan at cosine **0.903**, and `BIO ZITRONEN REINIGER 500ML` retrieved fresh lemons at **0.903**. Both were blocked. `ERDBEER JOG 500G` retrieved the 150 g yogurt at **0.873**, blocked by size. These illustrate why semantic similarity alone must not propagate merchant corrections.

To reproduce in an isolated temporary database without changing operational merchant memory:

```powershell
.\.venv\Scripts\python.exe -B app/tools/evaluate_product_memory.py --output app/.artifacts/product-memory-recheck.json
```

The script never edits frozen experiments or original labels. It refuses to record a semantic evaluation if the real local encoder is unavailable. Results are exploratory development evidence and do not establish production error rates, calibration or savings.

## Verification

The Product Memory milestone passed 42 backend tests, production frontend build and both browser flows. The subsequent [quality sprint](PRODUCT_QUALITY.md) passed 49 backend tests and reverified both flows using the new primary methods. Browser tests use an isolated SQLite file on port 8001 and block public-internet page requests.

```powershell
.\.venv\Scripts\python.exe -B -m pytest app/backend/tests -q -p no:cacheprovider --basetemp=app/.artifacts/my-fresh-memory-test
powershell -NoProfile -ExecutionPolicy Bypass -File app/build-frontend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File app/start-backend.ps1 -Port 8001 -DatabasePath app/.artifacts/my-isolated-memory-demo.sqlite3
# In another terminal:
.\.venv\Scripts\python.exe -B app/tools/verify_product_memory_browser.py --url http://127.0.0.1:8001
.\.venv\Scripts\python.exe -B app/tools/verify_demo_browser.py --url http://127.0.0.1:8001
.\.venv\Scripts\python.exe -B app/tools/verify_integrity.py
```

Use a fresh test directory/database for independent runs. Browser confirmation is reversed before completion. There is no catalog administration UI, live model fallback, distributed index, authentication, new analytics panel or automatic fuzzy correction propagation.

Documentation submission note: the original root README is now archived byte-for-byte. The unchanged legacy integrity command above flags the new landing page's README hash; all frozen experiment evidence remains intact. See [documentation provenance](../docs/PROVENANCE.md).
