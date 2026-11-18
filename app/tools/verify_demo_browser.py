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
    frames = []
    def socket_opened(socket):
        if '/api/ws' in socket.url:
            socket.on('framereceived',lambda payload: frames.append(json.loads(payload)))
    page.on('websocket',socket_opened)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(args.url, wait_until="networkidle")
    page.get_by_test_id("leaf_value_cents").wait_for()
    page.wait_for_function("document.querySelector('[data-testid=leaf_value_cents]').textContent.includes('€')")
    merchant = "nordmarkt-demo"
    endpoint = f"{args.url}/api/merchants/{merchant}"
    get_report = lambda: page.request.get(endpoint+"/report?policy=TWO_STAGE&dataset=pilot").json()
    one_shot = page.request.get(endpoint+"/report?policy=ONE_SHOT&dataset=pilot").json()
    assert one_shot["comparison"]["cohort"]["matched_count"] == 30
    assert page.get_by_test_id("policy-one-shot").get_attribute("aria-pressed") == "true"
    page.screenshot(path=str(artifacts/"dashboard-one_shot.png"),full_page=True)
    page.get_by_test_id("policy-two-stage").click()
    page.wait_for_function("document.querySelector('[data-testid=policy-two-stage]').getAttribute('aria-pressed') === 'true'")
    two_stage = get_report()
    page.wait_for_function("expected => document.querySelector('[data-testid=parent_value_cents]').textContent === expected", arg=f"€{two_stage['totals']['parent_value_cents']/100:,.2f}")
    assert two_stage["totals"]["parent_value_cents"] > 0 and two_stage["totals"]["unresolved_value_cents"] > 0
    assert one_shot["totals"]["leaf_value_cents"] > two_stage["totals"]["leaf_value_cents"]
    page.screenshot(path=str(artifacts/"dashboard-two_stage.png"),full_page=True)
    milk = next(line for line in two_stage["lines"] if line["line_id"]=="pilot:24")
    page.get_by_role("textbox",name="Find a receipt line").fill("MOLKEREI")
    page.get_by_test_id("review-row-pilot:24").click()
    dialog=page.get_by_role("dialog",name="MOLKEREI ART")
    dialog.locator(".assessment > strong").filter(has_text="No specific child").wait_for()
    dialog.locator('.distribution').first.locator('summary').click()
    assert dialog.locator('.distribution-table').first.get_by_text('94%',exact=True).is_visible()
    page.screenshot(path=str(artifacts/"decision-parent.png"),full_page=True)
    dialog.get_by_label("Corrected category").select_option("dairy_eggs.yogurt_quark")
    dialog.get_by_role("button",name="Apply correction").click()
    dialog.get_by_text("Correction saved. Report updated.",exact=True).wait_for()
    after=get_report()
    assert after["totals"]["leaf_value_cents"]-two_stage["totals"]["leaf_value_cents"]==milk["value_cents"]
    assert "pilot:24" not in [line["line_id"] for line in after["review_queue"]]
    assert page.get_by_test_id("review-row-pilot:24").count()==0
    page.reload(wait_until="networkidle")
    page.wait_for_function("expected => document.querySelector('[data-testid=leaf_value_cents]').textContent === expected",arg=f"€{after['totals']['leaf_value_cents']/100:,.2f}")
    persisted=page.request.get(endpoint+"/lines/pilot:24?policy=TWO_STAGE").json()
    assert persisted["decision"]["outcome"]=="override"
    assert persisted["decision"]["underlying_model"]["outcome"]=="parent_only"
    assert len(persisted["audit"])>=1
    page.locator(".all-lines > summary").click()
    page.get_by_role("button",name="MOLKEREI ART",exact=True).click()
    dialog=page.get_by_role("dialog",name="MOLKEREI ART")
    dialog.get_by_role("button",name="Undo correction").click()
    dialog.get_by_text("Correction undone. Report updated.",exact=True).wait_for()
    undone=get_report()
    assert undone["totals"]==two_stage["totals"]
    assert any(line["line_id"]=="pilot:24" for line in undone["review_queue"])
    dialog.get_by_role("button",name="Close decision inspector").click()
    page.locator(".all-lines > summary").click()
    page.wait_for_function("document.querySelector('[data-testid=socket-state]').textContent === 'WebSocket connected'")
    page.get_by_role('button',name='Demo Replay',exact=True).click()
    page.wait_for_function("document.querySelector('[data-testid=replay-count]')?.textContent === '6 / 6'",timeout=20000)
    page.get_by_text('replay complete',exact=True).wait_for()
    session_id=page.evaluate("localStorage.getItem('receipt-replay')")
    real_events=[f for f in frames if f.get('type')=='receipt.processed' and f.get('session_id')==session_id and f.get('generation')==1]
    assert len(real_events)==6 and len({f['line_id'] for f in real_events})==6
    replay_url=endpoint+f'/report?policy=TWO_STAGE&dataset=pilot&session_id={session_id}'
    replay_before=page.request.get(replay_url).json()
    assert replay_before['line_count']==6 and replay_before['totals']['sales_value_cents']==4044
    page.evaluate('window.scrollTo(0,0)')
    page.screenshot(path=str(artifacts/'replay-complete.png'),full_page=True)
    page.get_by_role('button',name='Reset replay',exact=True).click()
    page.wait_for_function("document.querySelector('[data-testid=replay-count]')?.textContent === '0 / 6'")
    page.wait_for_function("document.querySelector('[data-testid=replay-count]')?.textContent === '6 / 6'",timeout=20000)
    page.get_by_text('replay complete',exact=True).wait_for()
    replay_after=page.request.get(replay_url).json()
    assert replay_after['replay']['generation']==2 and replay_after['line_count']==6
    assert replay_after['totals']==replay_before['totals']
    page.get_by_role('button',name='Weekly snapshot',exact=True).click()
    page.wait_for_function("!localStorage.getItem('receipt-replay')")
    page.wait_for_function("expected => document.querySelector('[data-testid=leaf_value_cents]').textContent === expected",arg=f"€{two_stage['totals']['leaf_value_cents']/100:,.2f}")
    page.locator('.all-lines > summary').click()
    page.get_by_role('button',name='USB-C KABEL 1M',exact=True).click()
    scope_dialog=page.get_by_role('dialog',name='USB-C KABEL 1M')
    scope_dialog.get_by_text('Outside scope',exact=True).first.wait_for()
    scope_dialog.get_by_role('button',name='Close decision inspector').click()
    page.locator('.all-lines > summary').click()
    page.get_by_label('Source examples').select_option('holdout')
    page.get_by_test_id('policy-one-shot').click()
    page.wait_for_function("document.querySelector('[data-testid=policy-one-shot]').getAttribute('aria-pressed') === 'true'")
    additional=page.request.get(endpoint+'/report?policy=ONE_SHOT&dataset=holdout').json()
    assert additional['comparison']['cohort']['matched_count']==24
    assert all(r['availability']=='complete' for r in additional['lines'])
    page.get_by_test_id('policy-two-stage').click()
    page.get_by_role("button",name="Evaluation evidence",exact=True).click()
    page.get_by_role("heading",name="What the experiments tell us").wait_for()
    page.get_by_test_id('matched-evaluation').get_by_text('Original examples: 30 / 30 paired inputs',exact=True).wait_for()
    page.get_by_test_id('matched-evaluation').get_by_text('Additional examples: 24 / 24 paired inputs',exact=True).wait_for()
    page.get_by_text('Naive Forced Baseline and the former 0.85 policy',exact=True).click()
    page.locator('.evidence-examples button').first.click()
    baseline_dialog=page.get_by_role('dialog')
    baseline_dialog.get_by_text('Naive Forced Baseline',exact=True).wait_for()
    baseline_dialog.get_by_role('button',name='Close decision inspector').click()
    assert page.evaluate("localStorage.getItem('receipt-policy')")=='TWO_STAGE'

    fallback=browser.new_context(viewport={"width":1440,"height":1000},reduced_motion='reduce')
    fallback.route('**/*',lambda route: route.continue_() if urlparse(route.request.url).hostname in ('127.0.0.1','localhost') else route.abort())
    fallback.route_web_socket('**/api/ws**',lambda socket: socket.close())
    fallback.add_init_script("localStorage.setItem('receipt-policy','SAFE')")
    fp=fallback.new_page()
    fp.on('pageerror',lambda error: errors.append(str(error)))
    fp.goto(args.url,wait_until='networkidle')
    fp.get_by_role('button',name='Demo Replay',exact=True).click()
    fp.wait_for_function("document.querySelector('[data-testid=replay-count]')?.textContent === '6 / 6'",timeout=20000)
    fp.get_by_text('replay complete',exact=True).wait_for()
    assert fp.get_by_test_id('socket-state').inner_text()!='WebSocket connected'
    fp.get_by_role('button',name='Weekly snapshot',exact=True).click()
    fallback.close()

    mobile=browser.new_context(viewport={'width':390,'height':844},reduced_motion='reduce')
    mobile.route('**/*',lambda route: route.continue_() if urlparse(route.request.url).hostname in ('127.0.0.1','localhost') else route.abort())
    mp=mobile.new_page()
    mp.on('pageerror',lambda error: errors.append(str(error)))
    mp.goto(args.url,wait_until='networkidle')
    mp.get_by_test_id('category-chart').wait_for()
    assert mp.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile page overflows horizontally'
    mp.screenshot(path=str(artifacts/'dashboard-mobile.png'),full_page=True)
    mobile.close()
    assert not errors, errors
    browser.close()
    print(json.dumps({"browser_flow":"PASS","one_shot_to_two_stage":True,"actual_sqlite_correction":True,"queue_removed":True,"reload_persistence":True,"underlying_model_preserved":True,"undo_reconciles":True,"distribution_inspection":True,"scope_status_component":True,"matched_additional_set":True,"evaluation_view":True,"real_websocket_events":len(real_events),"replay_reset_no_duplicates":True,"rest_only_replay_fallback":True,"responsive_no_overflow":True,"public_internet_blocked":True,"browser_errors":errors,"screenshots":str(artifacts)},indent=2))
