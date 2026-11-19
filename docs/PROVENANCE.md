# Documentation provenance

The root README now introduces the finished Receipt Intelligence product. Its predecessor is preserved **byte-for-byte** in [archive/jev-experiment-readme.md](archive/jev-experiment-readme.md), with SHA-256:

```text
1c44e1abaddad3f2734d16d62116a9746779283d47a770c59d52aac999ecd7cc
```

That is the root README originally committed in `03c3b82`. The archived document's file references are relative to the repository root, as they were originally written. It describes an earlier experiment stage, not the current application.

The unchanged frozen follow-up manifest, `results/taxonomy-v2/followup-D-vs-TOPDOWN/manifest.json`, records this hash under `protected_existing_sha256["README.md"]`. The verifier explicitly maps **only that historical entry** to the archive. Run:

```powershell
.\.venv\Scripts\python.exe -B app/tools/verify_integrity.py
```

The command checks all 140 provenance hashes, 144 response records, credential scans and ignore rules. Its output identifies the archive path used for the original README. No recorded hash was updated, skipped or accepted on failure; an altered/missing archive still fails verification, and every other artifact uses its original path.

The documentation submission originally exposed a failure because the legacy verifier looked for the old README at the root. The pre-push audit fixes that lookup rather than modifying historical evidence. The archived README is also verified against its original Git blob. Historical request timestamps and existing commit author/committer dates remain unchanged.

The dashboard image in [assets/dashboard.png](assets/dashboard.png) is an unedited copy of the screenshot captured by the final quality-sprint browser checks. It shows the real local application with synthetic sales assumptions, not actual merchant data or live POS events.

The README submission itself changed only documentation and a screenshot. The subsequent pre-push audit adds the narrow verifier lookup adjustment and updates these notes. Neither change modifies application behavior, datasets, taxonomy, responses, prompts, scoring protocols, manifests or existing history.
