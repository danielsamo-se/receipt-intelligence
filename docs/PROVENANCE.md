# Documentation provenance

The root README now introduces the finished Receipt Intelligence product. Its predecessor is preserved **byte-for-byte** in [archive/jev-experiment-readme.md](archive/jev-experiment-readme.md), with SHA-256:

```text
1c44e1abaddad3f2734d16d62116a9746779283d47a770c59d52aac999ecd7cc
```

That is the root README originally committed in `03c3b82`. The archived document's file references are relative to the repository root, as they were originally written. It describes an earlier experiment stage, not the current application.

The unchanged frozen follow-up manifest, `results/taxonomy-v2/followup-D-vs-TOPDOWN/manifest.json`, records this hash under `protected_existing_sha256["README.md"]`. Consequently, the unchanged legacy command:

```powershell
.\.venv\Scripts\python.exe -B app/tools/verify_integrity.py
```

now reports **`Frozen artifact changed: README.md`** for the intentionally replaced landing page. This exception is explicit: no manifest or verification code was changed to hide it. Before replacement, the command passed all 140 hashes, 144 response records, credential scans and ignore checks.

The documentation submission separately verifies the archived README against the original hash and Git blob, and every other manifest hash against its unchanged original path. All 140 recorded content hashes still match their preserved artifacts when that single archival relocation is accounted for. All 144 follow-up responses, reports, credential scans and exclusions remain verified. Historical request timestamps and existing commit author/committer dates are unchanged.

The dashboard image in [assets/dashboard.png](assets/dashboard.png) is an unedited copy of the screenshot captured by the final quality-sprint browser checks. It shows the real local application with synthetic sales assumptions, not actual merchant data or live POS events.

This documentation-only change does not modify application code, datasets, taxonomy, responses, prompts, scoring protocols, manifests or existing history. Updating the legacy verifier to understand the archived README would be a separate code change; it is deliberately outside this submission's scope.
