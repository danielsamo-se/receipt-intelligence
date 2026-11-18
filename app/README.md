# Receipt Intelligence

Reliable category analytics from imperfect POS descriptions, with visible uncertainty and auditable merchant corrections. A local B2B product prototype for the anybill Tech & AI Product Internship case study.

**Synthetic demonstration data — not actual anybill merchant data.** Nordmarkt Demo is a fictional merchant. The 54 source examples are not a real transaction history or independent merchant ground truth.

## Start the application

Run from `C:\Users\danie\Downloads\jev-experiment-step1` in two PowerShell terminals:

```powershell
Set-Location 'C:\Users\danie\Downloads\jev-experiment-step1'
powershell -NoProfile -ExecutionPolicy Bypass -File .\app\start-backend.ps1
```

```powershell
Set-Location 'C:\Users\danie\Downloads\jev-experiment-step1'
powershell -NoProfile -ExecutionPolicy Bypass -File .\app\start-frontend.ps1
```

Open **http://127.0.0.1:5173**. Backend API documentation: **http://127.0.0.1:8000/docs**. Both servers bind only to loopback; stop them with Ctrl+C.

**Simplest offline presentation:** build once, then use only FastAPI:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\app\build-frontend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\app\start-backend.ps1
```

Open **http://127.0.0.1:8000**. FastAPI serves the React bundle and API/WebSocket routes from one origin. Internet is unnecessary after dependency setup. The product never reads `.env`, calls Jev, or sends data to a model.

The prepared workspace includes Python dependencies, frontend dependencies, and a checksum-verified portable Node.js LTS runtime under ignored `app/.tools/`. The frontend scripts use Node on PATH when available, otherwise the prepared portable runtime. No global Node installation was changed.

### Fresh dependency setup

Python 3.11+ and a current Node.js LTS release are required for development; this workspace was tested with Python 3.13.3 and Node 26.13.1. Install dependencies once while online:

```powershell
py -3 -m venv .venv  # only if .venv does not already exist
.\.venv\Scripts\python.exe -m pip install -r .\app\backend\requirements-dev.txt
Set-Location .\app\frontend
npm ci
```

The lockfile fixes the frontend dependency resolution. `app/backend/requirements.txt` pins runtime packages; `requirements-dev.txt` adds the test/browser tools. Do not place API credentials in the frontend or a Vite environment file.

## Live demo: the main product workflow

1. Open Category Analytics with **Initial examples · 30** and **FORCED**. The first load defaults to FORCED; policy selection is retained after reload. Specific-category value is high because this baseline forces every available line to a leaf, including cases where the cached model chose `unidentifiable`. This is explicitly a comparison baseline.
2. Switch to **SAFE**. The same chart changes. Three cards separate specific-category value, parent-only value, and unresolved/outside-scope value. The policy comparison shows computed changes using the same stored weekly assumptions and active corrections.
3. Search the review queue for **MOLKEREI** and open `MOLKEREI ART`. The inspector shows receipt input, actual Jev parent/child assessments, deterministic policy rules, and final outcome. The cached parent is dairy; its child choice is `unspecified_child`.
4. In **Review & correct**, select **Yogurt & quark**, optionally add a note, and click **Apply correction**. This is the demonstrator acting as the merchant and asserting an exact-line category. It is not a claim that the ambiguous text itself identifies yogurt.
5. The exact modeled value moves from parent-only to specific, the line leaves the review queue, and the audit records original classification, original model snapshot, corrected node, scope and UTC timestamp.
6. Reload. The SQLite correction remains active. Expand **Inspect all receipt lines**, reopen `MOLKEREI ART`, and inspect the merchant-corrected outcome and unchanged Jev evidence. **Undo correction** restores the previous override, or the cached policy if no earlier override exists; audit events remain.

The operational correction never changes the frozen evaluation CSV or labels. It applies only to the exact merchant/receipt-line pair, not fuzzy name matches or unrelated products. Repeated synthetic occurrences of that same example pattern use the same correction.

## Demo Replay

Click **Demo Replay** in the chart header. The feature is labeled **Simulated POS replay — cached real Jev classifications**.

- The backend creates a SQLite-backed replay session and sequentially processes the original six diagnostic examples using the same cached decision service.
- Each received line counts **once** in this separate session view, rather than adding weekly modeled quantities again. The weekly snapshot stays unchanged.
- FastAPI sends actual `receipt.processed` WebSocket events. React receives notifications and refreshes the authoritative REST report. The latest received line, outcome, received count, category values and review queue update.
- Policy/source selection is disabled while replay is running to keep the visible pipeline consistent. Once complete, **Reset replay** clears membership and increments its generation; **Weekly snapshot** exits the session view.
- A unique `(session_id, line_id)` key and generation checks prevent duplicate/stale events from adding value twice. Restart/reset does not merge sessions.
- If WebSocket connection fails, the UI explicitly shows **REST fallback** and polls during replay. Saving corrections and ordinary analytics work through REST independently.
- Interrupted sessions retain their stored members and are marked interrupted on server restart. Reset starts a controlled replay again. Run one backend process; this is not a distributed event system.

## Policy and data semantics

**FORCED** reproduces the existing A baseline: argmax among the 27 raw FLAT leaf probabilities, ignoring the two special options. Ties use the original taxonomy order; a zero-probability forced result is exposed as such. The 29-option FLAT cache exists only for the original 30 lines. FORCED therefore leaves the additional 24 unavailable; it never silently substitutes D probabilities or fabricates calls. The default original-30 view supports the main demo; SAFE covers all 54 examples.

**SAFE** implements the already evaluated C2 TOPDOWN rule at **0.85 per stage**, selected as an explicit exploratory demo operating point, not an optimized/calibrated production threshold:

- `unidentifiable` → no category, requires review.
- Supported parent below threshold → policy abstention.
- `out_of_scope` above threshold → scope rejection, not classification success.
- Supported parent with `unspecified_child` or a below-threshold child → parent-only.
- Parent and conditional child meeting their thresholds → leaf assignment, still an AI assessment rather than verified product identity.
- Missing/invalid required cache → visibly unavailable/unresolved; no model fallback.
- A valid active merchant/line correction takes precedence over either policy. Underlying cached evidence remains inspectable.

The `leaf`, `parent_only`, `unidentifiable`, `out_of_scope`, and `override` outcomes map to a typed React component registry. This is **schema-driven/adaptive UI**, not genuinely model-generated UI. No model generates executable frontend code.

### Sales assumptions and reconciliation

`app/data/synthetic_sales.json` is a tracked ledger with fixed seed **20261118**, one stored integer quantity per example, source-input hashes, and an illustrative week. Quantities mean occurrences of a printed receipt line, not individual units inside its multipack. `tools/create_sales_assumptions.py` refuses to replace an existing ledger and does not use evaluation labels.

Four explicit deposit/discount descriptions have separate assumed POS record types. Other positive-price descriptions are modeled sales candidates, including unresolved and outside-scope value; this is a demonstration assumption, not a product-identity claim. Deposits, returned deposits and discounts are excluded from product-category revenue regardless of classifier output. The fixed source set contains no ordinary merchandise-return example; such returns are outside the supported taxonomy rather than silently treated as product-category revenue. A category correction cannot change these assumed POS record types.

All arithmetic uses integer cents:

```text
modeled sales value = specific value + parent-only value + unresolved/outside value
net receipt value   = modeled sales value + signed receipt adjustments
line value          = stored price in cents × stored quantity
```

Unresolved includes explicit abstention, below-threshold decisions, outside-scope items and unavailable caches, with a separate backend breakdown. None is treated as a verified product classification. Review prioritization sorts the actual modeled line value. Percentage shares are rounded for display; monetary totals reconcile exactly.

## Architecture

- `backend/receipt_intelligence/catalog.py`: immutable CSV/taxonomy loading and validated cache adapters.
- `engine.py`: reusable typed policy decisions, probabilities, provenance and deterministic rule explanations. No model client or API-key access.
- `storage.py`: SQLite append-only correction events, active merchant/line pointers, revision counters, replay sessions and unique memberships.
- `service.py`: override precedence, exact-cent aggregation, review priorities and policy comparisons.
- `api.py`: FastAPI REST, WebSocket notifications and optional serving of the built React app.
- `replay.py`: small in-process event broker and controlled cached-example replay worker.
- `frontend/src/decisionRegistry.tsx`: exhaustive typed outcome-to-component mapping.
- `Inspector.tsx`: original evidence, distributions, applied rules, correction and undo workflow.

REST is authoritative; WebSockets notify the client to refetch. There is no database copy of the experiment labels and no inference-time use of proposed ground truth. The separate Evaluation evidence view reads existing result summaries and clearly labels exploratory counts and methodological limits.

Mutable state defaults to ignored **`app/.local/demo.sqlite3`**. Set `RECEIPT_DB_PATH` or use `start-backend.ps1 -DatabasePath app/.artifacts/my-test.sqlite3` for an isolated database. Unit and browser tests use isolated project-local databases; test corrections do not populate the default demo database.

## Tests and verification

Run backend tests with a fresh project-local temp directory (avoids Windows restrictions on the system pytest temp folder):

```powershell
.\.venv\Scripts\python.exe -B -m pytest app/backend/tests -q -p no:cacheprovider --basetemp=app/.artifacts/my-fresh-test-run
powershell -NoProfile -ExecutionPolicy Bypass -File .\app\build-frontend.ps1
.\.venv\Scripts\python.exe -B .\app\tools\verify_integrity.py
```

Use a new `--basetemp` directory for each invocation. The tests cover cache loading/mapping, exact alignment with all frozen pilot A/C2 decisions, SAFE parent and child gates, parent-only/abstention/scope behavior, missing caches, override scope/precedence, persistence, multi-step undo, audit history, exact report reconciliation, WebSocket event delivery, correction notifications, replay reset/deduplication/stale generations and REST-only replay.

For a genuine browser test, start a backend with an **isolated** database, then start Vite or use the built frontend served at port 8000:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\app\start-backend.ps1 -DatabasePath app/.artifacts/browser-demo.sqlite3
# In another terminal, after the server is ready:
.\.venv\Scripts\python.exe -B .\app\tools\verify_demo_browser.py --url http://127.0.0.1:8000
```

The browser test uses installed Microsoft Edge in a fresh headless context; if Edge is unavailable, install Playwright Chromium and change the launch channel in that local test tool. It executes FORCED → SAFE → inspect → persistent correction → reload → undo, checks six actual WebSocket frames, resets without double counting, tests a blocked-socket REST fallback and a 390px viewport. Public-internet browser requests are blocked. Screenshots are saved under ignored `app/.artifacts/screenshots/`. No test runs a Jev request.

`verify_integrity.py` checks the frozen follow-up and prior-artifact hashes, the 144 response caches, both experiment reports, tracked/built files for secrets and all required Git exclusions. The original root README and `.gitignore` remain unchanged to preserve their provenance hashes; product-only exclusions live in `app/.gitignore`.

## Deliberate limits

- No authentication, cloud hosting, Docker, new model calls, live POS integration, unrestricted generative UI or new model experiments.
- Local single-worker demo, one fictional merchant; merchant-scoped keys are not a production multi-tenant security system.
- Synthetic occurrences and proposed labels cannot establish production accuracy, calibration or statistical significance. Neither TOPDOWN nor D is claimed universally superior.
- SAFE 0.85 is a visible exploratory setting. A parent decision and an abstention are never relabeled as verified leaf successes.
- No generalized product identity mapping, fuzzy correction propagation or quantity/record-type editing. Merchant feedback is operational, not automatically new evaluation ground truth.
- Replay is a simulation with existing cached responses, not production POS traffic. WebSocket notifications are in-process and not a durable distributed event log; SQLite remains authoritative for visible session membership and audit history.
- Node/dependency downloads are setup-only. After preparation, built-app operation, corrections, analytics and replay work without internet or `.env` credentials.

## Executed verification in this workspace

- 22 backend tests passed, including exact agreement with every frozen pilot A and C2 decision at the selected operating point.
- TypeScript checking and Vite production build passed.
- The browser workflow passed against Vite development mode and against the packaged FastAPI-served frontend at port 8000.
- Actual browser actions verified policy switching, full probability inspection, SQLite correction, queue removal, reload persistence, retained model evidence, undo, outside-scope rendering and honest unavailability of the additional-set forced baseline.
- Six actual WebSocket receipt events were observed; reset retained exactly six unique lines and identical totals. Blocking the socket still completed replay via REST. The 390px layout had no horizontal overflow. Browser contexts blocked public-internet requests; no application page errors occurred.
- Read-only provenance/secret verification passed: 140 frozen hash checks, 144 response caches, tracked/built credential scans and Git ignore rules.
- The backend test run emits one upstream Starlette TestClient deprecation warning for its HTTPX compatibility bridge. All tests pass; it does not affect the serving runtime.
- Test servers used isolated ignored SQLite files. The default merchant demo database was not populated with browser-test corrections. No Jev requests or new experiments were performed, and no Git remote was pushed.
