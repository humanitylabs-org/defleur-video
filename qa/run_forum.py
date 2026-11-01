"""Bounded worker entry. Admission belongs to the originating agent.

Build exact pushed source, run the complete existing/native suite plus house
regressions, extract approved frames, capture deterministic house components.
No live containers, networks, secrets, project data or persistent services touched.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

p=argparse.ArgumentParser();p.add_argument('--sha',required=True);p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
root=Path(__file__).resolve().parents[1]
sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
if sha!=a.sha:raise SystemExit(f'Expected {a.sha}, found {sha}')
if subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip():raise SystemExit('Worker checkout must be clean')
a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True);os.chmod(a.output,0o777)
image=f'defleur-house-preview:{sha[:12]}'
rows=[]
receipt={'source_revision':sha,'image':image,'commands':rows,'pass':False}

def save():
    (a.output/'worker-result.json').write_text(json.dumps(receipt,indent=2))

def run(name,argv,env=None):
    with (a.output/f'{name}.log').open('w') as log:
        result=subprocess.run(argv,cwd=root,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,**(env or {})})
    rows.append({'name':name,'argv':argv,'returncode':result.returncode,'log':f'{name}.log'})
    save()
    if result.returncode:raise SystemExit(f'{name} failed; see {a.output/name}.log')

save()
run('build',['docker','build','--label','org.opencontainers.image.source=https://github.com/humanitylabs-org/defleur-video','--label',f'org.opencontainers.image.revision={sha}','-t',image,'.'])
receipt['image_inspect']=json.loads(subprocess.check_output(['docker','image','inspect',image],text=True))[0]
save()
run('native-suite',['sh','test-container.sh'],{'VIDEO_SKIP_BUILD':'1','VIDEO_IMAGE':image})
run('image-provenance-suite',[sys.executable,'-m','unittest','-v','test_image_provenance'])
run('scale-suite-declaration',['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
    '--tmpfs','/scratch:rw,noexec,nosuid,size=512m,mode=1777','-e','TMPDIR=/scratch','-v',f'{root}/test_workflow_scale.py:/app/test_workflow_scale.py:ro','--entrypoint','/usr/bin/python3',image,'-m','unittest','-v','test_workflow_scale'])
run('prepare-gallery',['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
    '--tmpfs','/scratch:rw,noexec,nosuid,size=512m,mode=1777','-e','TMPDIR=/scratch',
    '-v',f'{root}:/checkout:ro','-v',f'{a.fixtures.resolve()}:/fixtures:ro','-v',f'{a.output}:/evidence',
    '--entrypoint','/usr/bin/python3',image,'/checkout/qa/prepare_house_gallery.py','--output','/evidence','--fixtures','/fixtures'])
run('browser-image',['docker','build','-f','qa/Dockerfile.browser','-t',f'defleur-house-browser-qa:{sha[:12]}','.'])
run('browser-suite',['docker','run','--rm','--network','none','--cap-drop','ALL','--security-opt','no-new-privileges','--memory','3g','--pids-limit','512',
    '-v',f'{root}/qa:/qa:ro','-v',f'{a.output}:/evidence',f'defleur-house-browser-qa:{sha[:12]}','/qa/house_browser.py','--output','/evidence'])
receipt['pass']=True
receipt['limitations']=['Image generation is not demonstrated by archival/fixture gallery assets. Probe the staged app connection separately.', 'The native suite uses an explicitly controlled loopback Transcriber fixture; not a claim of live ASR or subjective creative approval.', 'Scale test remains opt-in; its skip is reported, not claimed as passed capacity evidence.']
save()
print(json.dumps({'pass':True,'source_revision':sha,'image':image,'image_id':receipt['image_inspect']['Id'],'result':str(a.output/'worker-result.json')}))
