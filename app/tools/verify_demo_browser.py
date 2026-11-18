"""Actual browser/REST flow against running local servers. Uses an isolated DB server."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:5173")
args = parser.parse_args()
artifacts = ROOT / "app/.artifacts/screenshots"
artifacts.mkdir(parents=True, exist_ok=True)

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="msedge", headless=True)
    context = browser.new_context(viewport={"width":1440,"height":1000}, reduced_motion="reduce")
    # Browser requests to the public internet are blocked for the entire demo.
    context.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname in ("127.0.0.1","localhost") else route.abort())
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(args.url, wait_until="networkidle")
    page.get_by_test_id("leaf_value_cents").wait_for()
    page.wait_for_function("document.querySelector('[data-testid=leaf_value_cents]').textContent.includes('€')")
    merchant = "nordmarkt-demo"
    endpoint = f"{args.url}/api/merchants/{merchant}"
    get_report = lambda: page.request.get(endpoint+"/report?policy=SAFE&dataset=pilot").json()
    forced = page.request.get(endpoint+"/report?policy=FORCED&dataset=pilot").json()
    assert forced["totals"]["leaf_value_cents"] == forced["totals"]["sales_value_cents"]
    assert page.get_by_test_id("policy-forced").get_attribute("aria-pressed") == "true"
    page.screenshot(path=str(artifacts/"dashboard-forced.png"),full_page=True)
    page.get_by_test_id("policy-safe").click()
    page.wait_for_function("document.querySelector('[data-testid=policy-safe]').getAttribute('aria-pressed') === 'true'")
    safe = get_report()
    page.wait_for_function("expected => document.querySelector('[data-testid=parent_value_cents]').textContent === expected", arg=f"€{safe['totals']['parent_value_cents']/100:,.2f}")
    assert safe["totals"]["parent_value_cents"] > 0 and safe["totals"]["unresolved_value_cents"] > 0
    assert forced["totals"]["leaf_value_cents"] > safe["totals"]["leaf_value_cents"]
    page.screenshot(path=str(artifacts/"dashboard-safe.png"),full_page=True)
    milk = next(line for line in safe["lines"] if line["line_id"]=="pilot:24")
    page.get_by_role("textbox",name="Find a receipt line").fill("MOLKEREI")
    page.get_by_test_id("review-row-pilot:24").click()
    dialog=page.get_by_role("dialog",name="MOLKEREI ART")
    dialog.locator(".assessment > strong").filter(has_text="No specific child").wait_for()
    page.screenshot(path=str(artifacts/"decision-parent.png"),full_page=True)
    dialog.get_by_label("Corrected category").select_option("dairy_eggs.yogurt_quark")
    dialog.get_by_role("button",name="Apply correction").click()
    dialog.get_by_text("Correction saved. Report updated.",exact=True).wait_for()
    after=get_report()
    assert after["totals"]["leaf_value_cents"]-safe["totals"]["leaf_value_cents"]==milk["value_cents"]
    assert "pilot:24" not in [line["line_id"] for line in after["review_queue"]]
    assert page.get_by_test_id("review-row-pilot:24").count()==0
    page.reload(wait_until="networkidle")
    page.wait_for_function("expected => document.querySelector('[data-testid=leaf_value_cents]').textContent === expected",arg=f"€{after['totals']['leaf_value_cents']/100:,.2f}")
    persisted=page.request.get(endpoint+"/lines/pilot:24?policy=SAFE").json()
    assert persisted["decision"]["outcome"]=="override"
    assert persisted["decision"]["underlying_model"]["outcome"]=="parent_only"
    assert len(persisted["audit"])>=1
    page.locator(".all-lines > summary").click()
    page.get_by_role("button",name="MOLKEREI ART",exact=True).click()
    dialog=page.get_by_role("dialog",name="MOLKEREI ART")
    dialog.get_by_role("button",name="Undo correction").click()
    dialog.get_by_text("Correction undone. Report updated.",exact=True).wait_for()
    undone=get_report()
    assert undone["totals"]==safe["totals"]
    assert any(line["line_id"]=="pilot:24" for line in undone["review_queue"])
    dialog.get_by_role("button",name="Close decision inspector").click()
    page.locator(".all-lines > summary").click()
    page.get_by_role("button",name="Evaluation evidence",exact=True).click()
    page.get_by_role("heading",name="What the experiments tell us").wait_for()
    assert page.get_by_role("heading",name="Original 30-line pilot").is_visible()
    assert not errors, errors
    browser.close()
    print(json.dumps({"browser_flow":"PASS","forced_to_safe":True,"actual_sqlite_correction":True,"queue_removed":True,"reload_persistence":True,"underlying_model_preserved":True,"undo_reconciles":True,"evaluation_view":True,"public_internet_blocked":True,"browser_errors":errors,"screenshots":str(artifacts)},indent=2))
