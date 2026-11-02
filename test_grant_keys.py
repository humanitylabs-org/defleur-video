"""DeFleur Video sends its App Manager grant keys to the Transcriber and the Browser (wizard-os issue 386, card 5).

With the browser boundary on, the Transcriber engine API and the Browser DevTools answer only granted callers. The
keys come from this app's own grants file (`uses: [transcriber, browser, files]`) and go only to that provider's own
endpoint. Keys are generated at runtime. Stdlib only (runs on the host and in the image).
"""
import json
import os
import secrets
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import app_grants
import transcriber
import workflow


class Provider(BaseHTTPRequestHandler):
    """A box provider behind its front with `enforce` on: no granted key, 403."""
    want = ""
    seen = []

    def _go(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)
        grant = self.headers.get("X-Wizard-Grant")
        Provider.seen.append((self.path, grant))
        ok = grant == Provider.want
        body = json.dumps({"data": [{"id": "Systran/faster-whisper-small"}]} if self.path == "/v1/models" else
                          {"Browser": "HeadlessChrome/155", "Protocol-Version": "1.3"} if ok else {"error": "needs X-Wizard-Grant"}).encode()
        self.send_response(200 if ok else 403)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = _go

    def log_message(self, *a):
        pass


class GrantKeys(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="grant-keys-"))
        self.http = HTTPServer(("127.0.0.1", 0), Provider)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        Provider.want, Provider.seen = secrets.token_hex(32), []
        self.env = {k: os.environ.get(k) for k in ("WIZARD_GRANTS_FILE", "TRANSCRIBER_URL", "BROWSER_URL")}

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def grants(self, outgoing, endpoints=None):
        p = self.dir / "grants.json"
        p.write_text(json.dumps({"outgoing": outgoing, "incoming": [], "provider_endpoints": endpoints or {}, "enforce": True}))
        os.environ["WIZARD_GRANTS_FILE"] = str(p)
        return p

    def test_key_only_for_the_providers_own_endpoint(self):
        key = Provider.want
        self.grants({"transcriber": key}, {"transcriber": self.url})
        t = ("transcriber",)
        self.assertEqual(app_grants.key_for("http://transcriber:8000", t, "http://transcriber:8000"), key)
        self.assertEqual(app_grants.key_for(self.url, t, "http://transcriber:8000"), key)
        self.assertEqual(app_grants.key_for("https://stt.example", t, "http://transcriber:8000"), "")
        self.assertEqual(app_grants.key_for("http://transcriber:8001", t, "http://transcriber:8000"), "")
        self.assertEqual(app_grants.key_for(self.url, ("browser",), "http://browser:9222"), "")
        self.grants({"transcriber": "short"})
        self.assertEqual(app_grants.key_for("http://transcriber:8000", t, "http://transcriber:8000"), "")
        (self.dir / "grants.json").write_text("{not json")
        self.assertEqual(app_grants.key_for("http://transcriber:8000", t, "http://transcriber:8000"), "")
        os.environ.pop("WIZARD_GRANTS_FILE")
        self.assertEqual(app_grants.key_for("http://transcriber:8000", t, "http://transcriber:8000"), "")

    def test_transcriber_requests_carry_the_key(self):
        self.grants({"transcriber": Provider.want}, {"transcriber": self.url})
        os.environ["TRANSCRIBER_URL"] = self.url
        s = transcriber.status()
        self.assertTrue(s["reachable"], s)
        self.assertEqual(Provider.seen, [("/v1/models", Provider.want)])
        # An owner-set third-party Transcriber never gets the box key.
        self.grants({"transcriber": Provider.want}, {"transcriber": "http://transcriber:8000"})
        self.assertFalse(transcriber.status()["reachable"])
        self.assertEqual(Provider.seen[-1], ("/v1/models", None))

    def test_browser_devtools_probe_carries_the_key(self):
        os.environ["BROWSER_URL"] = self.url
        self.grants({}, {})
        self.assertFalse(workflow.browser_status()["reachable"])          # ungranted: refused like the real front
        self.grants({"browser": Provider.want}, {"browser": self.url})
        s = workflow.browser_status()
        self.assertTrue(s["reachable"], s)
        self.assertEqual(Provider.seen[-1], ("/json/version", Provider.want))
        self.assertEqual(workflow.browser_grant(self.url), Provider.want)
        self.assertEqual(workflow.browser_grant("http://other:9222"), "")

    def test_capture_script_hash_matches_the_notice(self):
        notice = (Path(__file__).parent / "NOTICE").read_text()
        self.assertIn(workflow.CAPTURE_ADAPTED_SHA256, notice)
        self.assertEqual(workflow.sha(workflow.CAPTURE_SCRIPT), workflow.CAPTURE_ADAPTED_SHA256)
        self.assertIn("BROWSER_GRANT", workflow.CAPTURE_SCRIPT.read_text())


if __name__ == "__main__":
    unittest.main()
