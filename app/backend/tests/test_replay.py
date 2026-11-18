import time

from fastapi.testclient import TestClient

from receipt_intelligence.api import create_app
from receipt_intelligence.replay import REPLAY_LINES
from receipt_intelligence.service import MERCHANT_ID, ReceiptService
from receipt_intelligence.storage import Store


def test_store_duplicate_events_and_reset_do_not_double_count(tmp_path):
    store=Store(tmp_path/'replay.sqlite3')
    service=ReceiptService(store)
    session=store.create_replay(MERCHANT_ID,"SAFE",REPLAY_LINES)
    assert store.add_replay_member(session['id'],MERCHANT_ID,REPLAY_LINES[0],session['generation'])
    revision=store.snapshot(MERCHANT_ID)[0]
    assert not store.add_replay_member(session['id'],MERCHANT_ID,REPLAY_LINES[0],session['generation'])
    assert store.snapshot(MERCHANT_ID)[0]==revision
    report=service.report(MERCHANT_ID,"SAFE",replay_id=session['id'])
    assert report['line_count']==1 and report['lines'][0]['quantity']==1
    assert report['totals']['sales_value_cents']==119
    reset=store.reset_replay(session['id'],MERCHANT_ID,"SAFE")
    assert reset['processed_count']==0 and reset['generation']==2
    assert not store.add_replay_member(session['id'],MERCHANT_ID,REPLAY_LINES[1],1)
    assert store.add_replay_member(session['id'],MERCHANT_ID,REPLAY_LINES[0],2)
    assert service.report(MERCHANT_ID,"SAFE",replay_id=session['id'])['totals']['sales_value_cents']==119


def test_real_websocket_receipts_and_reset_reconcile(tmp_path):
    app=create_app(tmp_path/'websocket.sqlite3',replay_interval=.005)
    with TestClient(app) as client:
        with client.websocket_connect('/api/ws') as socket:
            assert socket.receive_json()['type']=='connected'
            session=client.post('/api/replay',json={'policy':'SAFE'}).json()
            received=[]
            while True:
                event=socket.receive_json()
                if event.get('session_id')!=session['id']:
                    continue
                if event['type']=='receipt.processed':
                    received.append(event['line_id'])
                    assert event['decision']['policy']=='SAFE'
                if event['type']=='replay.completed':
                    break
            assert received==REPLAY_LINES
            url=f"/api/merchants/{MERCHANT_ID}/report?policy=SAFE&session_id={session['id']}"
            first=client.get(url).json()
            assert first['line_count']==6 and first['totals']['sales_value_cents']==4044
            assert first['replay']['processed_count']==6
            reset=client.post(f"/api/replay/{session['id']}/reset",json={'policy':'SAFE'}).json()
            assert reset['generation']==2
            while True:
                event=socket.receive_json()
                if event.get('session_id')==session['id'] and event.get('generation')==2 and event['type']=='replay.completed':
                    break
            second=client.get(url).json()
            assert second['totals']==first['totals'] and second['line_count']==6
        assert client.get('/api/replay/not-a-session').status_code==404


def test_replay_rest_source_works_without_websocket(tmp_path):
    app=create_app(tmp_path/'rest-only.sqlite3',replay_interval=.001)
    with TestClient(app) as client:
        session=client.post('/api/replay',json={'policy':'SAFE'}).json()
        for _ in range(100):
            state=client.get('/api/replay/'+session['id']).json()
            if state['status']=='complete':
                break
            time.sleep(.01)
        assert state['status']=='complete' and state['processed_count']==6
        report=client.get(f"/api/merchants/{MERCHANT_ID}/report?session_id={session['id']}").json()
        assert report['mode']=='replay' and report['line_count']==6
        assert report['totals']['net_receipt_value_cents']==4044


def test_corrections_publish_after_persisting(tmp_path):
    with TestClient(create_app(tmp_path/'correction-events.sqlite3')) as client:
        with client.websocket_connect('/api/ws') as socket:
            socket.receive_json()
            url=f'/api/merchants/{MERCHANT_ID}/lines/pilot:24'
            assert client.post(url+'/corrections',json={'node_id':'dairy_eggs.yogurt_quark'}).status_code==200
            event=socket.receive_json()
            assert event['type']=='correction.saved'
            assert client.get(url).json()['decision']['outcome']=='override'
