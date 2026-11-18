from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml

PROJECT = Path(__file__).resolve().parents[3]
PARENT_LABELS = {
    "produce": "Fresh produce", "grains": "Bakery & cereal staples",
    "dairy_eggs": "Dairy & eggs", "meat_fish": "Meat & fish",
    "confectionery_snacks": "Confectionery & snacks", "prepared_food": "Prepared food",
    "cooking_ingredients": "Cooking ingredients", "beverages": "Beverages",
    "household": "Household", "adjustments": "Receipt adjustments",
}
LEAF_LABELS = {
    "milk_cream": "Milk & cream", "yogurt_quark": "Yogurt & quark", "meat_sausage": "Meat & cold cuts",
    "fish_seafood": "Fish & seafood", "bread_bakery": "Bread & bakery", "dry_staples": "Dry cereal staples",
    "sweet_biscuits": "Sweet biscuits", "savory_snacks": "Savory snacks", "potato_sides": "Potato side dishes",
    "meals_soups": "Meals & soups", "oils_fats": "Cooking oils & fats", "sauces_bases_seasonings": "Sauces, bases & seasonings",
    "water_soft_drinks": "Water & soft drinks", "juice_shots": "Juices & shots", "plant_drinks": "Plant drinks",
    "coffee_tea": "Coffee & tea", "kitchenware": "Kitchenware", "cleaning_supplies": "Cleaning supplies",
    "deposit_charge": "Deposit charge", "deposit_return": "Deposit return", "discount": "Discount",
}


@dataclass(frozen=True)
class ReceiptLine:
    id: str
    source_id: str
    dataset: str
    raw_text: str
    price_cents: int
    merchant_type: str


class Catalog:
    """Reads immutable experiment inputs; evaluation labels never enter decisions."""

    def __init__(self, root: Path = PROJECT):
        self.root = root
        self.taxonomy = yaml.safe_load((root / "taxonomy.yaml").read_text(encoding="utf-8-sig"))
        self.nodes: dict[str, dict] = {}
        self.leaves: list[str] = []
        for parent, data in self.taxonomy["parents"].items():
            self.nodes[parent] = {"id": parent, "label": PARENT_LABELS.get(parent, parent), "parent_id": None,
                                  "level": "parent", "kind": data["kind"], "description": data["description"]}
            for leaf, description in data["leaves"].items():
                key = f"{parent}.{leaf}"
                self.leaves.append(key)
                self.nodes[key] = {"id": key, "label": LEAF_LABELS.get(leaf, leaf.replace("_", " ").capitalize()),
                                   "parent_id": parent, "level": "leaf", "kind": data["kind"], "description": description}
        self.lines: dict[str, ReceiptLine] = {}
        for dataset, path in (("pilot", "data/lines.csv"), ("holdout", "data/followup_holdout24_inputs.csv")):
            with (root / path).open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    key = f"{dataset}:{row['id']}"
                    self.lines[key] = ReceiptLine(key, row["id"], dataset, row["raw_text"],
                                                  int(Decimal(row["price"]) * 100), row["merchant_type"])

    def line(self, line_id: str) -> ReceiptLine:
        if line_id not in self.lines:
            raise KeyError("Receipt line not found")
        return self.lines[line_id]

    def parent_of(self, node_id: str) -> str:
        node = self.nodes[node_id]
        return node["parent_id"] or node_id


class CachedResponses:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog

    def path(self, line: ReceiptLine, stage: str) -> Path | None:
        if stage == "D" or stage.startswith("topdown_"):
            sample = "original30" if line.dataset == "pilot" else "holdout24"
            name = stage.removeprefix("topdown_")
            return self.catalog.root / f"results/taxonomy-v2/followup-D-vs-TOPDOWN/{sample}/calls/{line.source_id}_{name}.json"
        if line.dataset == "holdout" and stage == "flat":
            return None  # No 29-option FLAT experiment exists for the additional set.
        folder = "results/taxonomy-v2/pilot-30/calls" if line.dataset == "pilot" else "results/taxonomy-v2/followup-D-vs-TOPDOWN/holdout24/calls"
        return self.catalog.root / folder / f"{line.source_id}_{stage}.json"

    def load(self, line: ReceiptLine, stage: str) -> dict:
        path = self.path(line, stage)
        if path is None:
            return {"stage": stage, "available": False, "reason": "not_collected",
                    "error": "The forced FLAT baseline was not collected for the additional 24 examples."}
        try:
            raw = path.read_bytes()
            record = json.loads(raw)
            if record.get("status") != "complete" or record.get("http_status") != 200:
                raise ValueError("Cached request did not complete successfully")
            state = record["request"]["state"]
            if (state["raw_text"] != line.raw_text or state["merchant_type"] != line.merchant_type
                    or Decimal(str(state["price"])) * 100 != line.price_cents):
                raise ValueError("Cache input does not match this receipt line")
            response = record["response"]
            model = response["model"]
            if model != "typesafe/jev-1.14" and not model.startswith("typesafe/jev-1.14-"):
                raise ValueError("Unexpected cached model")
            answer = response["answers"]["classification"]
            criteria = record["request"]["questions"]["classification"]["criteria"]
            if stage == "D" or stage.startswith("topdown_"):
                frozen = self.catalog.root / "results/taxonomy-v2/followup-D-vs-TOPDOWN/frozen"
                question = record["request"]["questions"]["classification"]
                if stage == "D":
                    expected = json.loads((frozen / "D_question.json").read_text(encoding="utf-8"))
                    valid = question == expected and set(criteria) == set(self.catalog.nodes) | {"unidentifiable","out_of_scope"}
                else:
                    prompts = json.loads((frozen / "TOPDOWN_prompts.json").read_text(encoding="utf-8"))
                    valid = question == prompts["parent"] if stage == "topdown_parent" else question in prompts["children"].values()
                if not valid:
                    raise ValueError("Cached question does not match the frozen follow-up configuration")
            if answer["type"] != "choice" or answer["choice"] not in criteria or set(answer["probabilities"]) != set(criteria):
                raise ValueError("Invalid or incomplete cached Choice distribution")
            for value in answer["probabilities"].values():
                if not isinstance(value, (float, int)) or not 0 <= value <= 1:
                    raise ValueError("Invalid cached probability")
            return {"stage": stage.removeprefix("topdown_"), "available": True, "choice": answer["choice"],
                    "probabilities": answer["probabilities"], "confidence": answer.get("confidence"),
                    "model": model, "provider": response.get("provider"), "usage": response.get("usage"),
                    "latency_seconds": record.get("latency_seconds"), "response": response,
                    "cache_file": path.relative_to(self.catalog.root).as_posix(),
                    "cache_sha256": hashlib.sha256(raw).hexdigest()}
        except (OSError, ValueError, KeyError, TypeError):
            return {"stage": stage, "available": False, "reason": "cache_unavailable",
                    "error": "The required cached response is missing, invalid, or does not match the input."}
