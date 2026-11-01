"""Prepare deterministic house proof pages; no creative authorship or generation.

Run inside the candidate image. --fixtures contains privately copied approved
finished videos and archive-image.png, never production project/state folders.
"""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import house
from test_house import beat

p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--fixtures',type=Path,required=True);a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=True)
(a.output/'raw-reference').mkdir(exist_ok=True)
refs={'ai-authority-approved.mp4':[0,15,27.5,32,36], 'longevity-approved.mp4':[0,3.5,10,22,42,69,75], 'information-diet-approved.mp4':[0,15,30,45]}
reference_rows=[]
for name,times in refs.items():
    src=a.fixtures/name
    if not src.is_file():raise RuntimeError(f'Missing approved source {name}; do not synthesize a replacement')
    for t in times:
        dest=a.output/'raw-reference'/f'{src.stem}-{t}.jpg'
        subprocess.run(['/usr/bin/ffmpeg','-v','error','-ss',str(t),'-i',str(src),'-frames:v','1','-q:v','2',str(dest)],check=True,timeout=30)
        reference_rows.append({'source':name,'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'seconds':t,'frame':str(dest.relative_to(a.output))})
rows=[]
for component in house.COMPONENTS:
    b=beat(component)
    b['labels']=['HEALTHY','TRUST ALL','DOUBT ALL','BALANCE']
    if component=='image-beat':b.update(labels=[],visual_id='archive')
    if component=='source-frame':b.update(source_asset='assets/source.png',source_url='https://github.com/humanitylabs-org/defleur-video',attribution='Approved reference frame')
    data={'duration':20,'beats':[b]}
    # Browser fixture only: archive art is deliberately not claimed as a new
    # generated/attached image, nor is it fed to the staged production API.
    dest=a.output/'gallery'/component
    dest.mkdir(parents=True,exist_ok=True)
    for rel,value in house.compile_files(data).items():
        file=dest/rel;file.parent.mkdir(parents=True,exist_ok=True)
        file.write_bytes(base64.b64decode(value['base64']) if isinstance(value,dict) else value.encode())
    page=dest/'index.html'
    page.write_text(page.read_text().replace('"visual_id": "archive"','"visual_id": "archive", "asset": "assets/archive.png"'))
    (dest/'assets').mkdir(exist_ok=True)
    shutil.copyfile(a.fixtures/'archive-image.png',dest/'assets/archive.png')
    subprocess.run(['/opt/venv/bin/python','-c','from PIL import Image; import sys; Image.open(sys.argv[1]).save(sys.argv[2])',str(a.output/'raw-reference/longevity-approved-0.jpg'),str(dest/'assets/source.png')],check=True,timeout=30)
    (dest/'defleur').mkdir(exist_ok=True)
    (dest/'defleur/ledger.js').write_text('window.sourceFrameForOutputFrame=f=>f; document.querySelector("#live").src="assets/speaker.jpg";')
    (dest/'defleur/gsap.min.js').write_text('/* No GSAP call is used by the pure data house components. Native capture loads pinned GSAP. */')
    shutil.copyfile(a.output/'raw-reference/longevity-approved-0.jpg',dest/'assets/speaker.jpg')
    rows.append({'component':component,'path':f'gallery/{component}/index.html','times':[0,3.6,4.5,6.6]})
for version in ('v3','v31'):
    fixture=house.read(house.KIT/'fixtures'/f'{version}.json')
    house.validate(fixture['plan'],configuration={**house.policy(),**fixture['historical_project_policy']})
(a.output/'browser-input.json').write_text(json.dumps({'cases':rows,'references':reference_rows,'limitations':['Gallery images are archival fixtures, not new generation evidence.','Gallery checks deterministic mechanisms. Native captions/full decode are separately covered by the real FFmpeg HTTP suite.','Video render colors are the approved production palette, not Wizard UI skins. No app/shell view was changed.']},indent=2))
print(json.dumps({'output':str(a.output),'components':len(rows),'reference_frames':len(reference_rows)}))
