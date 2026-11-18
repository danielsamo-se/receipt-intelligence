"""Create a tracked synthetic quantity ledger once, without using evaluation labels."""
import csv
import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
target = ROOT / "app/data/synthetic_sales.json"
if target.exists():
    raise SystemExit("Assumptions already exist; refusing to replace them.")
rng = random.Random(20261118)
sources = {"pilot":"data/lines.csv","holdout":"data/followup_holdout24_inputs.csv"}
adjustments = {("LEERGUT","-0.25"):"deposit_return",("PFAND","0.25"):"deposit_charge",("COUPON 10%","-0.80"):"discount",("MENGENRABATT 2+1","-1.29"):"discount"}
items = {}
for dataset, name in sources.items():
    with (ROOT/name).open(encoding="utf-8-sig",newline="") as handle:
        for row in csv.DictReader(handle):
            items[f"{dataset}:{row['id']}"] = {"weekly_quantity":rng.randint(8,96),
                "record_type":adjustments.get((row["raw_text"],row["price"]),"sale")}
target.parent.mkdir(parents=True,exist_ok=True)
target.write_text(json.dumps({"version":1,"seed":20261118,"merchant_id":"nordmarkt-demo","merchant_name":"Nordmarkt Demo",
    "period_label":"Illustrative week · 9–15 Nov 2026","quantity_meaning":"Modeled occurrences of the printed receipt line, not individual units inside a pack.",
    "notice":"Synthetic demonstration data — not actual anybill merchant data.",
    "record_type_assumption":"Four explicit deposit/discount descriptions are typed separately. Other positive-priced lines are modeled sales candidates, including unresolved and outside-scope value; this does not establish product identity.",
    "source_sha256":{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources.values()},"items":items},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"Stored deterministic assumptions for {len(items)} receipt patterns; no evaluation labels used.")
