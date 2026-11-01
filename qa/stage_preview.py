"""Install only this isolated preview after worker evidence passes. No WAM/live edits.

Run on the same Linux worker. Services/state live below ~/wizard-local; source,
fixtures and build evidence stay outside the installed app. API bearer is generated
locally and never printed or returned. Only explicit tailnet IPs may be bound.
"""
import argparse
from datetime import datetime,timedelta,timezone
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.error
import urllib.request

p=argparse.ArgumentParser();p.add_argument('--receipt',type=Path,required=True);p.add_argument('--tailnet-ip',required=True);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--port',type=int,default=28787);a=p.parse_args()
ip=ipaddress.ip_address(a.tailnet_ip)
if ip not in ipaddress.ip_network('100.64.0.0/10'):raise SystemExit('Only a tailnet IPv4 listener is permitted')
r=json.loads(a.receipt.read_text())
if r.get('pass') is not True:raise SystemExit('Worker acceptance has not passed')
sha=r['source_revision'];image=r['image'];identity=r['image_inspect']['Id']
actual=json.loads(subprocess.check_output(['docker','image','inspect',image],text=True))[0]
if actual['Id']!=identity or actual['Config']['Labels'].get('org.opencontainers.image.revision')!=sha:raise SystemExit('Candidate image identity changed')
name='defleur-house-preview';browser=name+'-browser';network=name+'-network';volume=name+'-data'
if subprocess.run(['docker','container','inspect',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:raise SystemExit('Preview already exists; do not replace it blindly')
root=Path.home()/'wizard-local'/name;root.mkdir(parents=True,exist_ok=True);root.chmod(0o700)
token=secrets.token_urlsafe(36)
env=root/'preview.env';env.write_text('VIDEO_API_TOKEN='+token+'\nVIDEO_DATA_DIR=/data\nVIDEO_BIND=0.0.0.0\nBROWSER_URL=http://'+browser+':9222\n');env.chmod(0o600)
labels=['--label','org.wizard.preview.owner=defleur-house-pipeline','--label','org.opencontainers.image.revision='+sha]
subprocess.run(['docker','network','create',*labels,network],check=True)
subprocess.run(['docker','volume','create',*labels,volume],check=True)
subprocess.run(['docker','run','-d','--name',browser,'--restart','unless-stopped','--pull','never',*labels,'--network',network,
    '--cap-drop','ALL','--security-opt','no-new-privileges','--memory','2g','--pids-limit','512','--shm-size','512m',
    'ghcr.io/humanitylabs-org/browser-engine@sha256:11ffb8c2c1d53c42ec178dbc1ca6f710863043311dc16f3b375cc67d857010f5'],check=True)
subprocess.run(['docker','run','-d','--name',name,'--restart','unless-stopped','--pull','never',*labels,'--network',network,
    '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--memory','8g','--memory-swap','8g','--pids-limit','2048',
    '--tmpfs','/scratch:rw,noexec,nosuid,size=1024m,mode=1777','-e','TMPDIR=/scratch',
    '--env-file',str(env),'-v',volume+':/data','-p',f'127.0.0.1:{a.port}:8787','-p',f'{a.tailnet_ip}:{a.port}:8787',identity],check=True)
base=f'http://127.0.0.1:{a.port}'
for attempt in range(120):
    try:
        with urllib.request.urlopen(base+'/healthz',timeout=2) as response:health=json.load(response)
        break
    except (OSError,ValueError):
        if attempt==119:raise
        time.sleep(.5)

def request(method,path,value=None,content_type='application/json'):
    data=json.dumps(value).encode() if content_type=='application/json' and value is not None else value
    req=urllib.request.Request(base+path,data=data,method=method,headers={'Authorization':'Bearer '+token,'Content-Type':content_type,'Accept':'application/json, text/event-stream'})
    with urllib.request.urlopen(req,timeout=180) as response:
        raw=response.read();kind=response.headers.get('Content-Type','')
        return json.loads(raw) if 'application/json' in kind else raw

skill=request('GET','/SKILL.md');expected=(Path(__file__).resolve().parents[1]/'SKILL.md').read_bytes()
if skill!=expected:raise SystemExit('Preview installed skill does not match release source')
guide=request('GET','/v1/house')
project=request('POST','/v1/projects',a.fixture.read_bytes(),'video/mp4');pid=project['id']
try:
    planned=request('POST',f'/v1/projects/{pid}/plan-visual',{'beat_id':'connection-probe','family':'cinematic-metaphor','subject':'A bounded connection verification probe, not owner creative content'})
    generation=request('POST',f'/v1/projects/{pid}/generate-visual',{'beat_id':'connection-probe'})
finally:
    request('DELETE',f'/v1/projects/{pid}')
try:
    request('GET',f'/v1/projects/{pid}')
    raise SystemExit('Temporary connection-probe project was not deleted')
except urllib.error.HTTPError as error:
    if error.code!=404:raise
mcp=request('POST','/mcp',{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'defleur-preview-verifier','version':'1'}}})
if isinstance(mcp,bytes):
    events=[json.loads(line[6:]) for line in mcp.decode().splitlines() if line.startswith('data: ')]
    mcp=events[-1] if events else None
if not isinstance(mcp,dict) or not mcp.get('result',{}).get('protocolVersion'):
    raise SystemExit('Preview MCP initialize did not return a valid protocol result')
safe_inspect=json.loads(subprocess.check_output(['docker','inspect',name],text=True))[0]
receipt={'stage':'isolated developer preview; not a managed/live installation','source_revision':sha,'image':image,'image_id':identity,
    'url':f'http://{a.tailnet_ip}:{a.port}','mcp':f'http://{a.tailnet_ip}:{a.port}/mcp','authentication':'Bearer from owner-only preview.env on worker; token intentionally omitted',
    'health':health,'container':name,'browser':browser,'installed_skill_sha256':hashlib.sha256(skill).hexdigest(),'installed_equals_release':True,
    'default_preset':guide['policy']['preset'],'generation_probe':generation,'temporary_probe_project_deleted':True,
    'mcp_initialize_received':bool(mcp),'actual_container_image':safe_inspect['Image'],'actual_ports':safe_inspect['NetworkSettings']['Ports'],
    'expires_at':(datetime.now(timezone.utc)+timedelta(days=7)).isoformat(),
    'cleanup_commands':[['docker','rm','-f',name,browser],['docker','network','rm',network]],
    'retained_preview_data_volume':volume,'limitations':['No live/company container, installed skill or routing registry was modified.','Preview image generation blocker is reported verbatim; no substitute provider/model was called.','Creator must independently review screenshots and native output before any acceptance/promotion.']}
(root/'STAGE.json').write_text(json.dumps(receipt,indent=2));(root/'STAGE.json').chmod(0o600)
print(json.dumps(receipt,indent=2))
