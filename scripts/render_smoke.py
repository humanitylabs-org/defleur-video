#!/usr/bin/env python3
"""Render one motion Short end to end against a running DeFleur, for the per-architecture look check in CI.

Usage: render_smoke.py serve-transcriber            (fake Transcriber on :8000, fixed words; run inside the image)
       render_smoke.py render <api-url> <source.mp4> <out-dir>
Stages: source-audio, asr, pcm-assemble, asr, face-crop, submit motion, motion-capture proof, final-render with the
proof. Writes <out-dir>/final.mp4 and summary.json. The image jobs run it on amd64 and arm64 and the parity job
compares the two finals (wizard-os#997: the Mac's arm64 Shorts must look like the Company's amd64 ones).
"""
import json
import sys
import time
import urllib.error
import urllib.request

WORDS = "so the thing about watching your feet is that it keeps you humble every single step reminds you where you are".split()
INDEX = '''<!doctype html><html><head><link rel="stylesheet" href="main.css"></head><body>
<img id="live"><div id="card"><div class="k">KEEP YOU</div><div class="v">HUMBLE</div><div id="bar"></div></div>
<script src="defleur/ledger.js"></script><script src="defleur/gsap.min.js"></script>
<script>
const card = document.getElementById('card'), bar = document.getElementById('bar');
window.renderFrame = (t) => {
  const on = t >= 3 && t < 7;
  card.style.opacity = on ? 1 : 0;
  bar.style.width = on ? Math.round(((t - 3) / 4) * 760) + 'px' : '0px';
};
</script></body></html>'''
CSS = ('body{margin:0;width:1080px;height:1920px;overflow:hidden;background:#000}#live{position:absolute;inset:0;width:1080px;height:1920px}'
       '#card{position:absolute;left:140px;top:360px;width:800px;padding:40px;background:#1d4ed8;border-radius:28px;color:#fff;'
       'font:900 96px Montserrat,sans-serif;opacity:0}.k{font-size:64px}#bar{height:24px;background:#facc15;margin-top:24px;width:0}')
BEAT = {'start': 3.0, 'end': 7.0, 'spoken_anchor': 'keeps you humble', 'viewer_inference': 'humility is the point',
        'visual_family': 'title card', 'state_before': 'speaker only', 'state_after': 'card names the idea',
        'causal_action': 'card slides in as the words land', 'caption_treatment': 'show', 'speaker_return': 'card fades at 7 s'}


def serve_transcriber():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def reply(self, v):
            d = json.dumps(v).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(d)))
            self.end_headers()
            self.wfile.write(d)

        def do_GET(self):
            self.reply({"data": [{"id": "Systran/faster-whisper-small"}]})

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            step = 11.0 / len(WORDS)
            words = [{"word": " " + w, "start": round(i * step + .05, 3), "end": round(i * step + step * .8, 3), "probability": .95}
                     for i, w in enumerate(WORDS)]
            self.reply({"language": "en", "duration": 11.0, "text": " ".join(WORDS),
                        "segments": [{"id": 0, "start": 0.0, "end": 11.0, "text": " ".join(WORDS)}], "words": words})
    ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()


def render(base, source, out):
    from pathlib import Path

    def req(m, p, body=None, raw=None, ct='application/json'):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        r = urllib.request.Request(base + p, data=data, method=m, headers={'Content-Type': ct})
        try:
            with urllib.request.urlopen(r, timeout=600) as x:
                return x.status, (json.load(x) if 'json' in x.headers.get('Content-Type', '') else x.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')

    def stage(pid, name, value):
        s, job = req('POST', f'/v1/projects/{pid}/stages/{name}', value)
        assert s == 202, (name, s, job)
        while job['state'] in ('queued', 'running'):
            time.sleep(1)
            job = req('GET', f"/v1/jobs/{job['id']}")[1]
        assert job['state'] == 'needs_review', (name, job.get('error'))
        return job

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    s, p = req('POST', '/v1/projects', raw=Path(source).read_bytes(), ct='video/mp4')
    assert s == 201, p
    pid = p['id']
    src = stage(pid, 'source-audio', {})
    stage(pid, 'asr', {'audio_job': src['id'], 'language': 'en'})
    asm = stage(pid, 'pcm-assemble', {'audio_job': src['id'], 'segments': [{'start_s': 0, 'end_s': 12, 'reason': 'whole take'}]})
    easr = stage(pid, 'asr', {'audio_job': asm['id'], 'language': 'en'})
    crop = stage(pid, 'face-crop', {'assemble_job': asm['id']})
    s, m = req('POST', f'/v1/projects/{pid}/motion', {'files': {'index.html': INDEX, 'main.css': CSS}, 'plan': {'beats': [BEAT]}})
    assert s == 201, m
    base_in = {'assemble_job': asm['id'], 'crop_job': crop['id'], 'edited_asr_job': easr['id']}
    proof = stage(pid, 'motion-capture', {**base_in, 'mode': 'proof', 'composition_sha256': m['composition_sha256']})
    assert proof['result']['summary']['pass'], proof['result']['summary']
    final = stage(pid, 'final-render', {**base_in, 'proof_job': proof['id']})
    rs = final['result']['summary']
    s, data = req('GET', f"/v1/jobs/{final['id']}/stage-artifacts/final.mp4")
    assert s == 200
    (out / 'final.mp4').write_bytes(data)
    summary = {'final_sha256': rs['final_sha256'], 'width': rs['width'], 'height': rs['height'], 'frames': rs['frames'],
               'beats_show_motion': (rs.get('motion_layer') or {}).get('beats_show_motion'), 'elapsed_s': final['result']['elapsed_s']}
    assert (rs['width'], rs['height']) == (1080, 1920) and all((summary['beats_show_motion'] or {'x': False}).values()), summary
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    if sys.argv[1:2] == ['serve-transcriber']:
        serve_transcriber()
    else:
        render(*sys.argv[2:5])
