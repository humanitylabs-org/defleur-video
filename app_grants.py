"""This app's grant keys for the box services it uses (wizard-os spec PERMISSIONS.md layer 2; issue 386, card 5).

The App Manager mounts the app's grants file read-only at /wizard (WIZARD_GRANTS_FILE): `outgoing` maps each grant
target (`transcriber`, `browser`, or a `slot:<name>`) to this app's key, and `provider_endpoints` says where the
granted provider answers. With the browser boundary on, the Transcriber engine API and the Browser DevTools answer
only callers that send a granted key as X-Wizard-Grant. A key is only ever sent to that provider's own endpoint (the
recipe default or the App Manager's provider endpoint), never to an owner-set third-party URL.
"""
from __future__ import annotations

import json
import os
import re
from urllib.parse import urlsplit

_KEY = re.compile(r"[A-Za-z0-9_-]{32,256}")


def _doc(path: str | None = None) -> dict:
    path = os.environ.get("WIZARD_GRANTS_FILE", "") if path is None else path
    if not path:
        return {}
    try:
        with open(path, "rb") as f:
            doc = json.loads(f.read(65537)[:65536])
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _origin(url: str) -> str:
    try:
        p = urlsplit(url)
        return f"{p.scheme}://{(p.hostname or '').lower()}:{p.port or (443 if p.scheme == 'https' else 80)}"
    except ValueError:
        return ""


def key_for(url: str, targets: tuple[str, ...], default_url: str, path: str | None = None) -> str:
    """The key to send to `url`, or '' (no grants file, no grant for these targets, or `url` is not that provider)."""
    doc = _doc(path)
    out = doc.get("outgoing")
    ends = doc.get("provider_endpoints") if isinstance(doc.get("provider_endpoints"), dict) else {}
    if not isinstance(out, dict):
        return ""
    for target in targets:
        key = out.get(target)
        if not (isinstance(key, str) and _KEY.fullmatch(key)):
            continue
        allowed = {_origin(default_url)} | ({_origin(ends[target])} if isinstance(ends.get(target), str) else set())
        return key if _origin(url) in allowed else ""
    return ""
