import argparse
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
root=a.output.resolve()
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kw):super().__init__(*args,directory=str(root),**kw)
    def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever);thread.start()
inputs=json.loads((root/'browser-input.json').read_text());results=[];shots=[]
try:
    with sync_playwright() as pw:
        browser=pw.chromium.launch(args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            page=browser.new_page(viewport={'width':1080,'height':1920},device_scale_factor=1)
            for case in inputs['cases']:
                errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{server.server_port}/{case["path"]}',wait_until='networkidle')
                page.evaluate('async()=>{await window.houseFontsReady;await document.fonts.ready}')
                page.wait_for_function('Array.from(document.images).every(i => i.complete && i.naturalWidth > 0)')
                for t in case['times']:
                    page.evaluate('(t)=>window.renderFrame(t)',t)
                    state=page.evaluate('''() => ({mode:window.visualMode(window.__t),captions:window.captionSuppressed(window.__t), fonts:document.fonts.check('52px Anton') && document.fonts.check('52px Inter'), visible:[...document.querySelectorAll('.house-scene')].filter(e=>getComputedStyle(e).visibility==='visible').length,live:{width:document.querySelector('#live').getBoundingClientRect().width,height:document.querySelector('#live').getBoundingClientRect().height}})'''.replace('window.__t',str(t)))
                    assert state['fonts'] and not state['captions'],state
                    assert state['live']=={'width':1080,'height':1920},state
                    assert state['visible']==(1 if 3.5<=t<6.5 else 0),state
                    name=f'{case["component"]}-{t}.png'
                    page.screenshot(path=str(root/name))
                    shots.append(name)
                page.evaluate('window.renderFrame(4.5)');first=hashlib.sha256(page.screenshot()).hexdigest()
                page.evaluate('window.renderFrame(0)');page.evaluate('window.renderFrame(4.5)');second=hashlib.sha256(page.screenshot()).hexdigest()
                assert first==second,'Reverse seek is not state-pure'
                assert not errors,errors
                results.append({'component':case['component'],'pass':True,'frames':len(case['times']),'reverse_seek_sha256':first,'page_errors':errors})
            page.close()
        finally:browser.close()
finally:
    server.shutdown();server.server_close();thread.join()
# Contact sheets: component after-pivot beside clean return, phone-scale.
for group,names in [('components',[s for s in shots if s.endswith('-4.5.png')]),('clean-returns',[s for s in shots if s.endswith('-6.6.png')]),('approved-references',[r['frame'] for r in inputs['references']])]:
    width,height=270,480;cols=4;rows=(len(names)+cols-1)//cols
    sheet=Image.new('RGB',(cols*width,rows*(height+30)),(16,16,18));draw=ImageDraw.Draw(sheet)
    for i,name in enumerate(names):
        im=Image.open(root/name).convert('RGB');im.thumbnail((width,height))
        x=(i%cols)*width;y=(i//cols)*(height+30)
        sheet.paste(im,(x+(width-im.width)//2,y));draw.text((x+6,y+height+4),Path(name).stem,fill='white')
    sheet.save(root/f'{group}-contact.jpg',quality=92)
report={'pass':all(r['pass'] for r in results),'cases':results,'counts':{'cases':len(results),'pass':sum(r['pass'] for r in results),'fail':sum(not r['pass'] for r in results)},'limitations':inputs['limitations']}
(root/'browser-result.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
