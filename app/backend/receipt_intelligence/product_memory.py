from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from decimal import Decimal

from .catalog import Catalog, PROJECT, ReceiptLine
from .embeddings import embeddings
from .memory_store import MemoryStore


def normalize(text: str) -> str:
    """Identity key deliberately retains punctuation, digits, units and word order."""
    return " ".join(unicodedata.normalize("NFKC",text).casefold().split())


def lexical(a: str, b: str) -> float:
    def grams(text):
        text = " " + normalize(text) + " "
        return Counter(text[i:i+3] for i in range(len(text)-2))
    x,y = grams(a),grams(b)
    cosine = sum(v*y.get(k,0) for k,v in x.items()) / max(math.sqrt(sum(v*v for v in x.values())*sum(v*v for v in y.values())),1)
    words_a,words_b = set(re.findall(r"\w+",normalize(a))),set(re.findall(r"\w+",normalize(b)))
    overlap = len(words_a & words_b) / max(len(words_a | words_b),1)
    return .7*cosine + .3*overlap


def pack_sizes(text: str) -> set[str]:
    result = set()
    for number,unit in re.findall(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(kg|ml|cl|g|l)\b",normalize(text)):
        value = Decimal(number.replace(",","."))
        if unit == "kg": value,unit = value*1000,"g"
        if unit == "ml": value,unit = value/1000,"l"
        if unit == "cl": value,unit = value/100,"l"
        result.add(f"{value.normalize():f}{unit}")
    return result


def conflicts(text: str, attributes: dict, identifier_verified: bool = False) -> list[str]:
    """Conservative demonstrator guards, not a universal retail parser."""
    text = normalize(text)
    blocked = []
    sizes = pack_sizes(text)
    if sizes and attributes.get("pack") and sizes != {attributes["pack"]}:
        blocked.append("Explicit pack size differs from the catalog product.")
    diameter = re.search(r"\b(\d+)\s*cm\b",text)
    if diameter and attributes.get("diameter_cm") and diameter[1] != attributes["diameter_cm"]:
        blocked.append("Cookware diameter differs.")
    brand = attributes.get("brand")
    if brand and any(other in text for other in ("haribo","wmf") if other != brand):
        blocked.append("Explicit brand differs.")
    variant = attributes.get("variant")
    if variant == "original" and re.search(r"\b(zero|light|zuckerfrei)\b",text):
        blocked.append("Sugar-free/zero variant is not the original product.")
    if variant == "zero" and re.search(r"\b(original|classic|klassik)\b",text):
        blocked.append("Original variant is not the zero product.")
    if variant == "strawberry" and re.search(r"\b(vanille|natur|pfirsich|kirsch\w*)\b",text):
        blocked.append("Yogurt flavor differs.")
    if variant == "full_fat" and re.search(r"1[.,]5\s*%|fettarm|entrahmt|laktosefrei",text):
        blocked.append("Milk variant differs from the confirmed catalog item.")
    family = attributes.get("family")
    family_markers = {
        "candy":r"\b(haribo|fruchtgummi)\b", "frozen_fries":r"\b(frites|tiefgek\w*|tiefkuehl\w*)\b",
        "pan":r"\b(bratpf\w*|pfanne|pf)\b", "yogurt":r"\b(jog\w*|yog\w*)\b",
        "milk":r"\b(milch|vollmilch)\b", "cola":r"\b(cola|cc)\b", "lemons":r"\b(zitronen)\b",
    }
    explicit_families = {key for key,pattern in family_markers.items() if re.search(pattern,text)}
    if explicit_families and family not in explicit_families:
        blocked.append("Explicit description conflicts with this catalog product family.")
    incompatible = {
        "candy":r"\b(tk|tiefgek\w*|frites|backofen)\b",
        "frozen_fries":r"\b(haribo|fruchtgummi|sauer\w*|suess\w*)\b",
        "milk":r"\b(hafer\w*|soja\w*|mandel\w*|kokos\w*)\b",
        "lemons":r"\b(reiniger|putz\w*|spuel\w*|spül\w*|saft|shot)\b",
        "pan":r"\b(deckel|topf|reiniger)\b",
    }
    if family in incompatible and re.search(incompatible[family],text):
        blocked.append("Description names a conflicting product family or form.")
    if re.search(r"\b(pfand|leergut|rabatt|retoure|storno|coupon)\b",text):
        blocked.append("Receipt adjustment/return cannot reuse a merchandise identity.")
    if not identifier_verified and (not re.search(r"[a-zäöüß]{3}",text) or re.fullmatch(r"(?:art(?:ikel)?\s*\d+|aktion\s*\d+|molkerei\s*art)",text)):
        blocked.append("Description does not justify a reusable product identity.")
    return blocked


def alias_constraints(text: str, attributes: dict) -> list[str]:
    """A review must not create a broad alias that loses distinguishing attributes."""
    text = normalize(text)
    reasons = []
    if attributes.get("pack") and not pack_sizes(text):
        reasons.append("Pack size is absent; this alias could refer to multiple catalog sizes.")
    if attributes.get("diameter_cm") and not re.search(r"\b\d+\s*cm\b",text):
        reasons.append("Cookware diameter is absent.")
    if attributes.get("brand") and attributes["brand"] not in text:
        reasons.append("Brand is absent from the reusable alias.")
    variant_markers = {"original":r"\b(original|classic|klassik)\b", "zero":r"\b(zero|zuckerfrei)\b",
                       "strawberry":r"\b(erd\w*|strawberry)\b", "full_fat":r"3[.,]5\s*(%|prozent)"}
    variant = attributes.get("variant")
    if variant in variant_markers and not re.search(variant_markers[variant],text):
        reasons.append("Distinguishing product variant is absent from the reusable alias.")
    return reasons


class ProductMemory:
    def __init__(self, store, catalog: Catalog, encoder=None):
        self.db = MemoryStore(store)
        self.catalog = catalog
        self.encoder = encoder or embeddings
        data = json.loads((PROJECT / "app/data/product_memory_catalog.json").read_text(encoding="utf-8"))
        for product in data["products"]:
            if product["node_id"] not in catalog.nodes or catalog.nodes[product["node_id"]]["kind"] != "merchandise":
                raise ValueError("Invalid synthetic catalog classification")
        self.db.seed(data,normalize)

    def assess(self, line: ReceiptLine, merchant_id: str, namespace: str = "demo-pos",
               identifier: str | None = None, retrieve: bool = True) -> dict:
        snapshot = self.db.snapshot(merchant_id,namespace,line.merchant_type)
        products = snapshot["products"]
        alias = normalize(line.raw_text)
        mapped = snapshot["aliases"].get(alias)
        product_id = snapshot["identifiers"].get(identifier) if identifier else None
        selected = products.get(product_id) if product_id else products.get(mapped["product_id"]) if mapped and not identifier else None
        reason = "confirmed_identifier" if product_id else "confirmed_alias"
        blocks = []
        if identifier and not product_id:
            blocks.append("Identifier is not confirmed in this merchant/POS namespace; alias reuse is disabled.")
        if product_id and mapped and mapped["product_id"] != product_id:
            blocks.append("Confirmed identifier and confirmed alias disagree; review is required.")
        if selected:
            blocks.extend(conflicts(line.raw_text,selected["attributes"],identifier_verified=bool(product_id)))
            if not product_id:
                blocks.extend(alias_constraints(line.raw_text,selected["attributes"]))
        result = {"status":"no_mapping", "namespace":namespace, "normalized_alias":alias,
                  "identifier":identifier,"match":None,"candidates":[],"blocked_reasons":blocks,
                  "suggestions_are_identities":False, "model_stage_bypassed":False,
                  "embedding":self.encoder.status(),"retrieval_mode":"not_needed",
                  "audit":[], "active_reviews":[]}
        if selected and not blocks:
            result.update(status="known_mapping",model_stage_bypassed=True,
                match={"product":selected,"method":reason,"alias_provenance":mapped if reason=="confirmed_alias" else None})
        elif retrieve and products:
            query = self.encoder.vector(line.raw_text,"query")
            candidates = []
            for product in products.values():
                texts = [product["name"]]+[a["alias"] for a in snapshot["aliases"].values() if a["product_id"]==product["product_id"]]
                lex = max(lexical(line.raw_text,t) for t in texts)
                vector = self.encoder.vector(product["name"],"passage") if query else None
                semantic = sum(a*b for a,b in zip(query,vector)) if vector is not None and query is not None else None
                # Fixed ranking weights, never an identity threshold or calibrated probability.
                score = .6*lex + .4*semantic if semantic is not None else lex
                safety = conflicts(line.raw_text,product["attributes"])+alias_constraints(line.raw_text,product["attributes"])
                rejected = next((r for r in snapshot["reviews"] if r["alias"]==alias and r["product_id"]==product["product_id"] and r["action"]=="reject"),None)
                if rejected:
                    safety.append("Merchant rejected this exact alias/product suggestion.")
                if lex >= .06 or (semantic is not None and semantic >= .78):
                    candidates.append({"product":product,"lexical_score":round(lex,6),
                        "semantic_cosine":round(semantic,6) if semantic is not None else None,
                        "ranking_score":round(score,6),"eligible_for_confirmation":not safety and not blocks,
                        "blocked_reasons":safety+blocks,"rejected":bool(rejected)})
            candidates.sort(key=lambda c:(-c["ranking_score"],c["product"]["product_id"]))
            result.update(candidates=candidates[:3],status="suggested" if candidates else "no_mapping",
                          embedding=self.encoder.status(),retrieval_mode="hybrid" if query is not None else "lexical_only")
        return result

    def review(self, line: ReceiptLine, merchant_id: str, context: dict, product_id: str,
               action: str, identity_checked: bool, note: str, original_decision: dict) -> int:
        assessment = self.assess(line,merchant_id,context["pos_namespace"],context.get("identifier"))
        candidate = next((c for c in assessment["candidates"] if c["product"]["product_id"]==product_id),None)
        if not candidate:
            raise ValueError("Select a current catalog suggestion for this receipt.")
        if action == "confirm" and (not identity_checked or not candidate["eligible_for_confirmation"]):
            raise ValueError("Confirmation requires an independent identity check and no blocking conflicts.")
        evidence = {"candidate":candidate,"retrieval":assessment["embedding"],
                    "identity_checked_by_merchant":identity_checked,"original_decision":original_decision,
                    "independent_evaluation_ground_truth":False}
        return self.db.review(merchant_id,context["pos_namespace"],line.merchant_type,normalize(line.raw_text),
                              product_id,action,{**line.__dict__,"identifier":context.get("identifier")},evidence,note)
