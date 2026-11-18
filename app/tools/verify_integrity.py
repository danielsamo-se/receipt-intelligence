"""Read-only experiment provenance, response, ignore-rule and secret checks."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
folder=ROOT/'results/taxonomy-v2/followup-D-vs-TOPDOWN'
manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
verified=0
for field,base in [('source_sha256',ROOT),('frozen_sha256',folder),('protected_existing_sha256',ROOT)]:
    for name,expected in manifest[field].items():
        assert hashlib.sha256((base/name).read_bytes()).hexdigest()==expected,'Frozen artifact changed: '+name
        verified+=1
records=list(folder.glob('*/calls/*.json'))
assert len(records)==144
for path in records:
    r=json.loads(path.read_text(encoding='utf-8'))
    assert r['status']=='complete' and r['http_status']==200,path.name
    a=r['response']['answers']['classification']
    assert set(a['probabilities'])==set(r['request']['questions']['classification']['criteria']),path.name
for name in ('findings.md','comparison_report.md'):
    assert (folder/name).read_text(encoding='utf-8').strip()
git=['git','-c','safe.directory='+ROOT.as_posix()]
tracked=subprocess.check_output(git+['ls-files','-z'],cwd=ROOT).decode().split('\0')
assert '.env' not in tracked
env=(ROOT/'.env').read_text(encoding='utf-8-sig') if (ROOT/'.env').is_file() else ''
keys=re.findall(r'''(?m)^\s*OPENROUTER_API_KEY\s*=\s*['"]?([A-Za-z0-9_-]+)''',env)
secret_pattern=re.compile(r'sk-or-(?:v1-)?[A-Za-z0-9_-]{20,}')
for name in [p for p in tracked if p]+[p.relative_to(ROOT).as_posix() for p in (ROOT/'app/frontend/dist').rglob('*') if p.is_file()]:
    body=(ROOT/name).read_bytes().decode('utf-8',errors='ignore')
    assert not any(key in body for key in keys if key),'Secret detected in '+name
    assert not secret_pattern.search(body),'Credential-like value detected in '+name
for name in ('.env','.venv/pyvenv.cfg','app/frontend/node_modules/react/package.json','app/frontend/dist/index.html',
             'app/.local/demo.sqlite3','app/.tools/node-path.txt','app/.artifacts/test.tmp','app/demo-credentials.json'):
    assert subprocess.run(git+['check-ignore','-q','--',name],cwd=ROOT).returncode==0,'Ignore rule missing: '+name
print(json.dumps({'result':'PASS','frozen_hash_checks':verified,'cached_responses':len(records),
                  'tracked_secret_scan':'PASS','built_frontend_secret_scan':'PASS','ignore_rules':'PASS',
                  'api_calls':0,'files_modified':0},indent=2))
