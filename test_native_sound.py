"""Real HTTP/FFmpeg fixture. Synthetic owned tones, never user media or editorial approval."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
import profiles
import service
import soundtrack


class NativeSoundTests(unittest.TestCase):
    def test_profiles_licensed_mix_and_rejections(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temp:
            root = Path(temp)
            source, tone = root / "fixture.mp4", root / "tone.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=navy:s=160x90:r=10", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "3", "-c:v", "libx264", "-threads", "1", "-c:a", "aac", "-ac", "2", "-movflags", "+faststart", str(source)], check=True)
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=900:sample_rate=48000", "-t", "3", str(tone)], check=True)
            server = service.make_server(root / "data", "fixture-token-012345678901234567890123456789", port=0)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            def request(method, path, body=None, raw=False):
                data = body if raw else json.dumps(body).encode() if body is not None else None
                req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}" + path, data=data, method=method,
                    headers={"Authorization": "Bearer fixture-token-012345678901234567890123456789", "Content-Type": "video/mp4" if raw else "application/json"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    return json.load(r)
            def wait(job):
                deadline = time.monotonic() + 120
                while job["state"] in {"queued", "running"} and time.monotonic() < deadline:
                    time.sleep(.1)
                    job = request("GET", "/v1/jobs/" + job["id"])
                self.assertEqual(job["state"], "needs_review", job)
                return job
            try:
                listing = request("GET", "/v1/workflows")
                self.assertEqual(listing["default"], "original-v1")
                original = request("GET", "/v1/workflows/original-v1")
                self.assertEqual(original["instructions"].encode(), profiles.ROOT.joinpath("SKILL.md").read_bytes())
                project = request("POST", "/v1/projects", source.read_bytes(), True)
                pid = project["id"]
                route = f"/v1/projects/{pid}"
                self.assertEqual(project["workflow_profile"]["id"], "original-v1")
                request("POST", route + "/workflow", {"profile_id": "sound-and-research-v1", "provenance": {"arm": "non-private synthetic fixture"}})
                src = wait(request("POST", route + "/stages/source-audio", {}))
                with self.assertRaises(urllib.error.HTTPError) as exc:
                    request("POST", route + "/workflow", {"profile_id": "original-v1"})
                self.assertEqual(exc.exception.code, 422)
                asm = wait(request("POST", route + "/stages/pcm-assemble", {"audio_job": src["id"], "segments": [{"start_s": 0, "end_s": 3, "reason": "synthetic fixture"}]}))
                blob = tone.read_bytes()
                asset = {"base64": base64.b64encode(blob).decode(), "extension": ".wav", "sha256": hashlib.sha256(blob).hexdigest(),
                         "license_receipt": {"source_url": "urn:defleur:synthetic-fixture", "license": "owned", "attribution": "DeFleur native test: generated sine wave", "evidence": "FFmpeg lavfi sine; no third-party recording"}}
                for bad in ({**asset, "sha256": "0" * 64}, {**asset, "license_receipt": {}}):
                    with self.assertRaises(urllib.error.HTTPError) as exc:
                        request("POST", route + "/sound-assets", bad)
                    self.assertEqual(exc.exception.code, 422)
                stored = request("POST", route + "/sound-assets", asset)
                cue = {"asset_id": stored["asset_id"], "role": "sfx", "start": .2, "end": 2.8, "source_start": 0, "gain_db": -22, "fade_s": .05}
                plan = {"version": 1, "cues": [cue, {**cue, "role": "music", "gain_db": -28}]}
                for bad in ({**cue, "end": -1}, {**cue, "gain_db": 0}, {**cue, "asset_id": "../bad"}):
                    with self.assertRaises(urllib.error.HTTPError):
                        request("POST", route + "/soundtrack", {"version": 1, "cues": [bad]})
                submitted = request("POST", route + "/soundtrack", plan)
                mixed = wait(request("POST", route + "/stages/sound-mix", {"assemble_job": asm["id"], "plan_sha256": submitted["plan_sha256"]}))
                summary = mixed["result"]["summary"]
                self.assertTrue(summary["pass"])
                self.assertFalse(summary["human_listening_approval"])
                self.assertNotEqual(summary["outputs"]["music-off"]["sha256"], summary["outputs"]["music-on"]["sha256"])
                folder = server.store.path(pid) / (mixed["id"] + ".stage")
                shutil.copyfile(folder / "music-off.wav", folder / "mix-input.wav")
                subprocess.run(["ffmpeg", "-v", "error", "-i", str(folder / "mix-input.wav"), "-c:a", "aac", "-b:a", "192k", str(root / "fixture.m4a")], check=True)
                subprocess.run(["ffmpeg", "-v", "error", "-i", str(root / "fixture.m4a"), "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(folder / "final-audio.wav")], check=True)
                delivery = soundtrack.delivery_check(folder)
                self.assertTrue(delivery["pass"], delivery)
                evidence = {"fixture": "owned generated tone, not speech or final creative acceptance", "mix_job": mixed["id"], "summary": summary, "decoded_mix_check": delivery,
                            "profiles": listing, "host": os.uname().nodename}
                if os.environ.get("NATIVE_SOUND_EVIDENCE"):
                    Path(os.environ["NATIVE_SOUND_EVIDENCE"]).write_text(json.dumps(evidence, indent=2))
                print(json.dumps(evidence), flush=True)
            finally:
                server.shutdown(); server.store.close(); server.server_close(); thread.join(5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
