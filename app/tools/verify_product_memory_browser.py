"""Real UI verification. Start a backend with an isolated DB before running."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser()
parser.add_argument("--url",default="http://127.0.0.1:8001")
args=parser.parse_args()
screenshots=ROOT / "app/.artifacts/screenshots"
screenshots.mkdir(parents=True,exist_ok=True)

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel="msedge",headless=True)
    context=browser.new_context(viewport={"width":1440,"height":1000},reduced_motion="reduce")
    context.route("**/*",lambda route:route.continue_() if urlparse(route.request.url).hostname in ("127.0.0.1","localhost") else route.abort())
    page=context.new_page()
    errors=[]
    page.on("pageerror",lambda error:errors.append(str(error)))
    page.goto(args.url,wait_until="networkidle")
    page.get_by_test_id("leaf_value_cents").wait_for()
    base=args.url+"/api/merchants/nordmarkt-demo"
    before=page.request.get(base+"/report?policy=SAFE&dataset=all").json()
    page.locator(".memory-entry > summary").click()
    page.get_by_role("button",name="Process description",exact=True).click()
    dialog=page.get_by_role("dialog",name="ERDBEER JOGHURT NM 150 G")
    dialog.get_by_test_id("candidate-SYN-104").wait_for()
    candidate=dialog.get_by_test_id("candidate-SYN-104")
    assert candidate.get_by_role("button",name="Confirm product").is_disabled()
    assert "Semantic cosine" in candidate.inner_text()
    assert dialog.get_by_text("No trusted mapping",exact=True).is_visible()
    candidate.get_by_role("checkbox").check()
    candidate.get_by_role("button",name="Confirm product").click()
    dialog.get_by_test_id("known-product").wait_for()
    assert "Jev classification bypassed" in dialog.get_by_test_id("known-product").inner_text()
    dialog.get_by_text("Alias confirmed. Future exact matches reuse Product Memory.",exact=True).wait_for()
    first_id=dialog.locator(".receipt-input + p").inner_text().split(" · ")[0]
    page.screenshot(path=str(screenshots/"product-memory-confirmed.png"),full_page=True)
    dialog.get_by_role("button",name="Close decision inspector").click()
    page.reload(wait_until="networkidle")
    page.locator(".memory-entry > summary").click()
    page.get_by_role("button",name="Process description",exact=True).click()
    dialog=page.get_by_role("dialog",name="ERDBEER JOGHURT NM 150 G")
    dialog.get_by_test_id("known-product").wait_for()
    repeated_id=dialog.locator(".receipt-input + p").inner_text().split(" · ")[0]
    assert first_id!=repeated_id
    for policy in ("SAFE","FORCED"):
        decision=page.request.get(base+f"/lines/{repeated_id}?policy={policy}").json()["decision"]
        assert decision["node_id"]=="dairy_eggs.yogurt_quark"
        assert decision["product_memory"]["match"]["method"]=="confirmed_alias"
        assert decision["product_memory"]["model_stage_bypassed"]
        assert not decision["assessments"] and decision["provenance"]["actual_model_calls"]==0
    dialog.get_by_role("button",name="Reverse confirmation",exact=True).click()
    dialog.get_by_test_id("candidate-SYN-104").wait_for()
    assert dialog.get_by_test_id("known-product").count()==0
    candidate=dialog.get_by_test_id("candidate-SYN-104")
    candidate.get_by_role("button",name="Not this product",exact=True).click()
    candidate=dialog.get_by_test_id("candidate-SYN-104")
    candidate.get_by_role("button",name="Rejected",exact=True).wait_for()
    assert candidate.get_by_role("button",name="Confirm product",exact=True).is_disabled()
    dialog.locator(".memory-step .audit > summary").click()
    dialog.get_by_role("button",name="Undo rejection",exact=True).click()
    candidate=dialog.get_by_test_id("candidate-SYN-104")
    candidate.get_by_role("checkbox").wait_for()
    dialog.get_by_role("button",name="Close decision inspector").click()
    page.get_by_label("Synthetic product memory scenario").select_option("3")
    page.get_by_role("button",name="Process description",exact=True).click()
    dialog=page.get_by_role("dialog",name="CC ZERO 1L")
    dialog.get_by_text("Confirmed identifier and confirmed alias disagree; review is required.",exact=True).first.wait_for()
    assert dialog.get_by_test_id("known-product").count()==0
    for button in dialog.get_by_role("button",name="Confirm product",exact=True).all():
        assert button.is_disabled()
    page.screenshot(path=str(screenshots/"product-memory-conflict.png"),full_page=True)
    dialog.get_by_role("button",name="Close decision inspector").click()
    page.get_by_label("Synthetic product memory scenario").select_option("1")
    page.get_by_role("button",name="Process description",exact=True).click()
    dialog=page.get_by_role("dialog",name="ART 123456")
    dialog.get_by_test_id("known-product").wait_for()
    assert "Confirmed product identifier" in dialog.get_by_test_id("known-product").inner_text()
    dialog.get_by_role("button",name="Close decision inspector").click()
    after=page.request.get(base+"/report?policy=SAFE&dataset=all").json()
    assert before["totals"]==after["totals"] and before["line_count"]==after["line_count"]==54
    page.get_by_role("button",name="Evaluation evidence",exact=True).click()
    page.get_by_role("heading",name="Merchant Product Memory",exact=True).wait_for()
    page.get_by_role("cell",name="Repeat after scripted review",exact=True).wait_for()
    page.set_viewport_size({"width":390,"height":844})
    page.get_by_role("button",name="Category Analytics",exact=True).click()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert not errors,errors
    print(json.dumps({"product_memory_browser":"PASS","confirmation_persists":True,
        "new_receipt_reuses_alias":True,"both_policies_bypass_cache_classification":True,
        "reverse_and_reject_and_undo":True,"contradictory_identifier_blocked":True,
        "known_sku":True,"weekly_totals_unchanged":True,"evaluation_visible":True,
        "mobile_no_overflow":True,"public_internet_blocked":True,"browser_errors":errors},indent=2))
    context.close()
    browser.close()
