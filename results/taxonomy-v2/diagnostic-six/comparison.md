# Six-line diagnostic: FLAT versus TOPDOWN

FLAT P is the selected-option probability. TOPDOWN probabilities are P(parent) and the separately returned P(child | selected parent); they are not multiplied or treated as directly comparable joint scores.

| ID / receipt | Ground truth | FLAT (P; confidence) | Outcome | TOPDOWN (P parent / child; confidence parent / child) | Outcome |
| --- | --- | --- | --- | --- | --- |
| 01 HARIBO SAURE POMMES | confectionery_snacks.confectionery | confectionery_snacks.confectionery (P=0.97; C=0.97) | correct_leaf | confectionery_snacks.confectionery (P=0.99/0.88; C=0.99/0.84) | correct_leaf |
| 02 POMMES FRITES TK | prepared_food.potato_sides | prepared_food.potato_sides (P=0.99; C=0.99) | correct_leaf | prepared_food.potato_sides (P=0.94/0.93; C=0.93/0.89) | correct_leaf |
| 03 WMF PF 24CM | household.kitchenware | household.kitchenware (P=0.96; C=0.96) | correct_leaf | household.kitchenware (P=0.69/0.84; C=0.66/0.76) | correct_leaf |
| 08 ART 004711 | INSUFFICIENT_INFORMATION | unidentifiable (P=0.99; C=0.99) | abstention | unidentifiable (P=1/n/a; C=1/n/a) | abstention |
| 24 MOLKEREI ART | PARENT_ONLY:dairy_eggs | unidentifiable (P=0.93; C=0.93) | abstention | dairy_eggs (P=0.94/0.97; C=0.93/0.96) [unspecified_child] | correct_parent |
| 29 AKTION 1 | INSUFFICIENT_INFORMATION | unidentifiable (P=1; C=1) | abstention | unidentifiable (P=0.99/n/a; C=0.99/n/a) | abstention |

Abstention is never counted as correct product classification. Overclaim means a specific child was asserted for parent-only ground truth. Unsupported includes committed categories on insufficient-information lines. No thresholds, calibration estimates or other receipts were evaluated.
