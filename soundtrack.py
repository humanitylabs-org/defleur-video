"""Native bounded sound assets, immutable plans and deterministic dialogue-relative mix.
No caller-provided filesystem paths, filters, commands or network reads.
"""
from __future__ import annotations
import base64
import hashlib
import io
import json
import math
import re
import wave
from pathlib import Path
from urllib.parse import urlsplit
import sys
import os
import tempfile
# Native helper runs with -I; only this immutable application source directory
# may be imported, never a project or caller-supplied directory.
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from editing import Rejected

MAX_BYTES = 32 * 1024 * 1024
HEX = re.compile(r"^[a-f0-9]{64}$")
KINDS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
GAIN_LIMITS = {"sfx": (-28, -16), "music": (-28, -20)}


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def number(value, name):
    if type(value) not in (float, int) or not math.isfinite(value):
        raise Rejected(f"{name} must be finite numeric")
    return float(value)


def store_asset(project, value):
    if not isinstance(value, dict) or set(value) != {"base64", "extension", "sha256", "license_receipt"}:
        raise Rejected("sound asset needs base64, extension, sha256 and license_receipt")
    ext = value["extension"]
    if ext not in KINDS or not isinstance(value["sha256"], str) or not HEX.fullmatch(value["sha256"]):
        raise Rejected("unsupported audio extension or SHA-256")
    receipt = value["license_receipt"]
    if not isinstance(receipt, dict) or set(receipt) != {"source_url", "license", "attribution", "evidence"}:
        raise Rejected("license receipt requires source_url, license, attribution, evidence")
    if any(not isinstance(v, str) or not v.strip() or len(v) > 8000 for v in receipt.values()):
        raise Rejected("license receipt fields must be nonempty bounded text")
    if receipt["license"] not in {"CC0-1.0", "CC-BY-4.0", "owned"} or urlsplit(receipt["source_url"]).scheme not in {"https", "http", "urn"}:
        raise Rejected("unsupported license or source URI")
    try:
        data = base64.b64decode(value["base64"], validate=True)
    except (ValueError, TypeError):
        raise Rejected("invalid base64 audio") from None
    if not 1 <= len(data) <= MAX_BYTES or hashlib.sha256(data).hexdigest() != value["sha256"]:
        raise Rejected("audio size or hash mismatch")
    asset_id = hashlib.sha256(canonical({"sha256": value["sha256"], "extension": ext, "license_receipt": receipt})).hexdigest()
    folder = project / "sound-assets"
    folder.mkdir(exist_ok=True)
    path = folder / (asset_id + ext)
    if not path.exists():
        blobs = [p for p in folder.iterdir() if p.suffix in KINDS]
        if len(blobs) >= 64 or sum(p.stat().st_size for p in blobs) + len(data) > 256 * 1024**2:
            raise Rejected("sound asset project quota exceeded (64 assets / 256MiB)")
        if __import__("shutil").disk_usage(folder).free < len(data) + 512 * 1024**2:
            raise Rejected("insufficient disk reserve for sound upload")
    record = {"asset_id": asset_id, "sha256": value["sha256"], "extension": ext, "bytes": len(data), "license_receipt": receipt,
              "license_verified": False, "receipt_basis": "operator-supplied; retained for review"}
    # Immutable content-addressed blobs; existing uploads cannot be overwritten.
    try:
        with path.open("xb") as f:
            f.write(data)
    except FileExistsError:
        if path.is_symlink() or sha(path) != value["sha256"]:
            raise Rejected("existing audio asset changed")
    meta = folder / (asset_id + ".json")
    if not meta.exists():
        fd, temporary = tempfile.mkstemp(prefix='.receipt-', dir=folder)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(canonical(record)); f.flush(); os.fsync(f.fileno())
            os.replace(temporary, meta)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return record


def asset(project, asset_id):
    if not isinstance(asset_id, str) or not HEX.fullmatch(asset_id):
        raise Rejected("invalid sound asset ID")
    folder = project / "sound-assets"
    try:
        record = json.loads((folder / (asset_id + ".json")).read_text())
        path = folder / (asset_id + record["extension"])
        if path.is_symlink() or sha(path) != record["sha256"]:
            raise Rejected("sound asset hash changed")
        return path, record
    except (OSError, ValueError, KeyError):
        raise Rejected("sound asset missing or invalid") from None


def validate_plan(project, plan, duration=None):
    if not isinstance(plan, dict) or set(plan) != {"version", "cues"} or plan["version"] != 1:
        raise Rejected("soundtrack plan needs version=1 and cues")
    cues = plan["cues"]
    if not isinstance(cues, list) or not 1 <= len(cues) <= 64:
        raise Rejected("soundtrack requires 1..64 cues")
    if not any(c.get("role") == "sfx" for c in cues if isinstance(c, dict)):
        raise Rejected("enhanced music-off must include SFX")
    for cue in cues:
        if not isinstance(cue, dict) or set(cue) != {"asset_id", "role", "start", "end", "source_start", "gain_db", "fade_s"}:
            raise Rejected("cue needs asset_id, role, start, end, source_start, gain_db, fade_s")
        asset(project, cue["asset_id"])
        if cue["role"] not in {"sfx", "music"}:
            raise Rejected("cue role must be sfx or music")
        start, end, source_start, gain, fade = [number(cue[k], k) for k in ("start", "end", "source_start", "gain_db", "fade_s")]
        if not 0 <= start < end <= (duration if duration is not None else 600) or source_start < 0:
            raise Rejected("cue timing outside edited timeline")
        lo, hi = GAIN_LIMITS[cue["role"]]
        if not lo <= gain <= hi:
            raise Rejected(f"cue gain outside trial dialogue-relative range {lo}..{hi} dB; audibility still needs audition")
        if not 0.005 <= fade <= min(2, (end - start) / 2):
            raise Rejected("cue fade must be 5ms..2s and fit cue")
    return plan


def submit(project, plan):
    validate_plan(project, plan)
    data = canonical(plan)
    digest = hashlib.sha256(data).hexdigest()
    folder = project / "sound-plans"
    folder.mkdir(exist_ok=True)
    path = folder / (digest + ".json")
    if not path.exists():
        if len(list(folder.glob("*.json"))) >= 64:
            raise Rejected("soundtrack plan quota exceeded")
        path.write_bytes(data)
    return {"plan_sha256": digest, "plan": plan}


def load(project, digest):
    if not isinstance(digest, str) or not HEX.fullmatch(digest):
        raise Rejected("invalid soundtrack plan hash")
    path = project / "sound-plans" / (digest + ".json")
    if not path.is_file() or path.is_symlink() or sha(path) != digest:
        raise Rejected("soundtrack plan missing or changed")
    return json.loads(path.read_text())


def delivery_check(root, variant):
    import numpy as np
    if variant not in ('music-off', 'music-on'):
        raise Rejected('an exact requested music variant is required')
    receipt = json.loads((root / "soundtrack-receipt.json").read_text())
    dialogue_ok = sha(root / "dialogue-premix.wav") == receipt["dialogue_sha256"]
    selected = sha(root / "mix-input.wav")
    mix_ok = selected == receipt["outputs"][variant]["sha256"]
    arrays = []
    for name in ("mix-input.wav", "final-audio.wav"):
        with wave.open(str(root / name)) as w:
            if w.getframerate() != 48000 or w.getsampwidth() != 2:
                raise Rejected("decoded mix format changed")
            arrays.append(np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768)
    a, b = arrays
    length_ok = abs(len(a) - len(b)) <= 2048
    n = min(len(a), len(b))
    correlation = float(np.corrcoef(a[:n], b[:n])[0, 1])
    peak = float(np.max(np.abs(b)))
    passed = dialogue_ok and mix_ok and length_ok and math.isfinite(correlation) and correlation >= .98 and peak < 1
    return {"pass": passed, "requested_variant": variant, "dialogue_custody": dialogue_ok, "selected_mix_custody": mix_ok, "decoded_length": length_ok,
            "decoded_mix_correlation": correlation if math.isfinite(correlation) else None, "decoded_sample_peak_dbfs": 20 * math.log10(peak) if peak else None,
            "human_listening_approval": False, "scope": "sample peak, decoded PCM correlation and source custody; not true-peak/loudness or perceptual approval"}


def mix(ctx, value, source, metadata):
    import numpy as np
    project = source.parent
    plan = load(project, value["plan_sha256"])
    dialogue, _ = ctx.ref(value["assemble_job"], {"pcm-assemble"}, "edited.wav", "dialogue-premix.wav")
    with wave.open(str(dialogue)) as w:
        channels, rate, width, count = w.getnchannels(), w.getframerate(), w.getsampwidth(), w.getnframes()
        if rate != 48000 or width != 2 or channels not in (1, 2):
            raise Rejected("sound mix needs 48kHz s16 mono/stereo dialogue")
        speech = np.frombuffer(w.readframes(count), dtype="<i2").astype(np.float64).reshape(-1, channels) / 32768
    validate_plan(project, plan, count / rate)
    stems = {role: np.zeros_like(speech) for role in ("sfx", "music")}
    evidence, credits = [], {}
    for index, cue in enumerate(plan["cues"]):
        path, receipt = asset(project, cue["asset_id"])
        credits[cue["asset_id"]] = receipt
        start, end = round(cue["start"] * rate), round(cue["end"] * rate)
        duration = (end - start) / rate
        # Protocol whitelist prevents container formats referring to external/network resources.
        raw = ctx.native(["/usr/bin/ffmpeg", "-v", "error", "-xerror", "-protocol_whitelist", "file,pipe", "-threads", "1",
                          "-ss", f'{cue["source_start"]:.6f}', "-i", path, "-t", f'{duration:.6f}', "-map", "0:a:0",
                          "-f", "s16le", "-ar", str(rate), "-ac", str(channels), "pipe:1"],
                         timeout=120, cpu=120, max_log=MAX_BYTES * 4, as_limit=2 * 1024**3, cwd=ctx.root)
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float64).reshape(-1, channels) / 32768
        if len(samples) < end - start:
            raise Rejected("sound asset too short: no silent padding or automatic looping")
        samples = samples[:end-start].copy()
        fade = round(cue["fade_s"] * rate)
        samples[:fade] *= np.linspace(0, 1, fade)[:, None]
        samples[-fade:] *= np.linspace(1, 0, fade)[:, None]
        local = float(np.sqrt(np.mean(speech[start:end] ** 2)))
        rms = float(np.sqrt(np.mean(samples ** 2)))
        if local < 0.001 or rms < 0.00001:
            raise Rejected("silent asset or insufficient local dialogue for quantitative contrast")
        samples *= local * 10 ** (cue["gain_db"] / 20) / rms
        stems[cue["role"]][start:end] += samples
        evidence.append({"cue": index, "role": cue["role"], "asset_id": cue["asset_id"],
                         "local_dialogue_rms_dbfs": 20 * math.log10(local), "stem_relative_db": cue["gain_db"],
                         "stem_rms_dbfs": 20 * math.log10(local) + cue["gain_db"]})
    # Aggregate overlaps must not defeat the per-cue contrast limits.
    for cue in plan["cues"]:
        a, b = round(cue["start"] * rate), round(cue["end"] * rate)
        speech_rms = float(np.sqrt(np.mean(speech[a:b] ** 2)))
        for role, (_, limit) in GAIN_LIMITS.items():
            stem_rms = float(np.sqrt(np.mean(stems[role][a:b] ** 2)))
            if stem_rms > speech_rms * 10 ** (limit / 20) * 1.001:
                raise Rejected("overlapping cues exceed aggregate dialogue-relative limit")
    outputs = {}
    for name, samples in {"sfx-stem": stems["sfx"], "music-stem": stems["music"],
                          "music-off": speech + stems["sfx"], "music-on": speech + stems["sfx"] + stems["music"]}.items():
        peak = float(np.max(np.abs(samples)))
        if peak >= 0.98:
            raise Rejected("mix lacks peak headroom; reduce sound gain (dialogue is never silently normalized)")
        target = ctx.root / (name + ".wav")
        with wave.open(str(target), "wb") as w:
            w.setparams((channels, 2, rate, 0, "NONE", "not compressed"))
            w.writeframes(np.rint(samples * 32768).astype("<i2").tobytes())
        outputs[name] = {"sha256": sha(target), "peak_dbfs": 20 * math.log10(peak) if peak else None, "samples": count}
    receipt = {"assemble_job": value["assemble_job"], "plan_sha256": value["plan_sha256"], "dialogue_sha256": sha(dialogue),
               "sample_rate": rate, "samples": count, "outputs": outputs, "cues": evidence, "pass": True,
               "human_listening_approval": False, "music_default": False, "has_music": any(c["role"] == "music" for c in plan["cues"])}
    ctx.write("soundtrack-plan.json", plan)
    ctx.write("soundtrack-receipt.json", receipt)
    ctx.write("credits.json", {"assets": list(credits.values()), "embedded_in_video": False, "plan_sha256": value["plan_sha256"]})
    return receipt


if __name__ == "__main__":
    if sys.argv[1] == "check":
        print(json.dumps(delivery_check(Path(sys.argv[2]), sys.argv[3])))
    elif sys.argv[1] == "mix":
        import shutil
        from service import native
        project, dialogue, output, request = map(Path, sys.argv[2:])
        class NativeMixContext:
            root = output
            def ref(self, jid, stages, name, dest=None):
                if name != "edited.wav" or stages != {"pcm-assemble"}:
                    raise Rejected("unexpected sound helper input")
                target = output / (dest or name)
                shutil.copyfile(dialogue, target)
                return target, {}
            def write(self, name, value):
                (output / name).write_bytes(canonical(value))
            native = staticmethod(native)
        print(json.dumps(mix(NativeMixContext(), json.loads(request.read_text()), project / "source.mp4", {})))
    else:
        raise SystemExit("unknown native sound helper operation")
