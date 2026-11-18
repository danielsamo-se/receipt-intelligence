# Jev Receipt Classification — Step 1 draft

These are the **8-parent/21-leaf taxonomy and 30 receipt lines** from the previous Codex response, saved as usable files. No Jev calls were made.

- `taxonomy.yaml`: the proposed hierarchy and original boundary rules.
- `data/lines.csv`: the 30 source lines and the proposed labels/review notes.

**Review required:** These are Codex's proposed labels, not independently verified ground truth. The source uses `supermarket`, `household_goods`, `bakery`, `drugstore` merchant types. Some parent-only labels use `PARENT_ONLY:<parent>`; unidentifiable rows use `INSUFFICIENT_INFORMATION`.

Do not start model experiments before reviewing the labels. In the earlier Codex response, files could not be written; this ZIP recreates them from the provided output rather than retrieving files from the user's machine.
