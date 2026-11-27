"""App-original Shorts editing styles (style packs) for DeFleur Video (humanitylabs-org/wizard-os#1012).

A style pack is plain data, versioned in a folder `<style-id>/<version>/`:

- `style.json`  id, name, author, version, a preset overlay (caption font/size/colours/stroke/placement, cut
                tightness), the layout (`crop`, today's fixed 9:16 face crop, or `window`: 16:9 footage in a window
                on a black canvas), persistent text layers (fixed text or per-Short slots such as title/tagline),
                inserts (image box, fades, pacing), caption animation, joined-range punch-in, output finish
                (fades, loudness) and which agent rules it overrides.
- `STYLE.md`    the editing guide the agent follows for this style.
- `references/` 1-3 small reference Shorts or stills (or `references` links in style.json).

`defleur-house` is built in: today's preset (defaults/james-preset.json) and today's rules, unchanged. With no
style chosen nothing in the pipeline reads this module's output, so house renders stay byte-identical.

Validation refuses unknown keys, fonts that aren't installed in this image, anything that isn't data (scripts or any
other file kind), and anything the renderer cannot draw yet, each with one plain reason.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

SCHEMA = "defleur-video-style/1"
HOUSE_ID = "defleur-house"
HOUSE_VERSION = "1"
ROOT = Path(os.environ.get("VIDEO_DATA_DIR", "/data")) / "styles"
FONT_DIR = "/usr/share/fonts/"
CANVAS = (1080, 1920)
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,47}$")
VERSION_RE = re.compile(r"^[1-9][0-9]{0,3}$")
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
REF_RE = re.compile(r"^references/[a-z0-9][a-z0-9_-]{0,47}\.(mp4|jpg|jpeg|png|webp)$")
REF_MAX = 5 << 20  # small references only: the pack travels in one MCP call (8 MiB, base64)
PACK_MAX = 5 << 20
TEXT_MAX = 64 << 10
MAGIC = {".png": lambda b: b[:8] == b"\x89PNG\r\n\x1a\n", ".jpg": lambda b: b[:3] == b"\xff\xd8\xff",
         ".jpeg": lambda b: b[:3] == b"\xff\xd8\xff", ".webp": lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP",
         ".mp4": lambda b: b[4:8] == b"ftyp"}
SCRIPT_KINDS = {".py", ".sh", ".bash", ".zsh", ".js", ".mjs", ".cjs", ".ts", ".rb", ".pl", ".php", ".lua", ".exe", ".bat",
                ".cmd", ".ps1", ".html", ".htm", ".svg", ".wasm", ".so", ".dylib", ".jar", ".command", ".applescript"}

# Agent-facing parts of the house contract a pack may replace (mcp_server.MOTION_CONTRACT / GUIDE).
AGENT_RULES = {
    "caption_band": "the page rule naming where captions live and that graphics stay out of that band",
    "beat_layout": "James' house layout part of motion_contract.beat_rules (full-frame beats)",
    "captions": "motion_contract.captions",
    "inserts": "motion_contract.inserts",
    "sequence": "motion_contract.sequence (the tool order for the motion/insert step)",
    "default_edit": "GUIDE.default_edit (what a DeFleur edit is in this style)",
    "approval": "what the ONE approval question must show (e.g. title and tagline with alternates, the image plan)",
}

CAPTION_KEYS = {
    "font": str, "font_size_px": int, "active_scale": float, "min_scale": float, "uppercase": bool, "max_words": int,
    "max_chars": int, "break_on_punctuation": bool, "text_color": "color", "active_color": "color",
    "emphasis_color": "color", "outline_color": "color", "outline_width_px": int, "shadow_px": int, "safe_rect": "rect4",
    "always_on": bool, "anchor": ("center", "top"), "pop_from_scale": float, "pop_ms": int,
}
# James' caption_layer.py (crop layout) draws these; the window renderer (style_render.py) draws all CAPTION_KEYS.
CAPTION_KEYS_HOUSE_RENDERER = set(CAPTION_KEYS) - {"anchor", "pop_from_scale", "pop_ms"}
EDITORIAL_KEYS = {"auto_propose_fillers": bool, "auto_propose_repeats_and_restarts": bool, "shorten_long_pauses_to_s": float,
                  "shorten_noisy_pauses": bool, "trim_leading_and_trailing_dead_air": bool,
                  "restore_clause_when_cut_is_fragile": bool}
TOP_KEYS = {"schema", "id", "name", "author", "version", "description", "preset", "layout", "text_layers", "inserts",
            "joins", "finish", "agent_rules", "references", "slots"}
CANT_DRAW = {
    "ken_burns": "Ken Burns moves on inserts", "zoom": "zooming inserts", "transition": "transitions between inserts",
    "animation": "caption animations other than the first-word pop", "caption_free": "caption-free stretches",
    "caption_suppress": "caption-free stretches", "video_inserts": "moving-video inserts in a window layout",
    "blur": "blurred backgrounds", "split": "split-screen layouts", "pan": "moving crops",
}


class StyleError(ValueError):
    """A pack was refused; str(e) is the plain reason."""


# ---------- fonts ----------

def _fc_match(pattern: str) -> tuple[str, str, str]:
    out = subprocess.run(["fc-match", "-f", "%{file}\n%{family}\n%{style}", pattern], capture_output=True, text=True,
                         timeout=20, check=True).stdout.split("\n")
    return (out + ["", "", ""])[:3]


FONT_MATCH = _fc_match  # tests swap this when fontconfig is missing


def resolve_font(pattern, label: str) -> str:
    """'Family' or 'Family:style=Style' -> installed font file. Refused unless fontconfig finds that family (and style)."""
    if not isinstance(pattern, str) or not pattern.strip() or len(pattern) > 120 or not re.fullmatch(r"[A-Za-z0-9 :=_-]+", pattern):
        raise StyleError(f"{label}: font must be a font name like 'Montserrat:style=Bold'")
    family = pattern.split(":", 1)[0].strip().lower()
    want_style = (re.search(r":style=([A-Za-z0-9 ]+)", pattern) or [None, ""])[1].strip().lower()
    try:
        path, families, styles = FONT_MATCH(pattern)
    except (OSError, subprocess.SubprocessError):
        raise StyleError(f"{label}: can't look up fonts on this server (fontconfig missing)") from None
    have = [f.strip().lower() for f in families.split(",")]
    have_styles = [s.strip().lower() for s in styles.split(",")]
    if family not in have or (want_style and want_style not in have_styles) or not path.startswith(FONT_DIR) \
            or ".." in path or not Path(path).is_file():
        raise StyleError(f"{label}: font {pattern!r} isn't installed on this DeFleur server (closest match: "
                         f"{families.split(',')[0] or 'none'} {styles.split(',')[0]}). Installed fonts are listed in capabilities.styles.fonts")
    return path


def installed_fonts() -> list[str]:
    try:
        out = subprocess.run(["fc-list", "--format", "%{family[0]}:style=%{style[0]}\n"], capture_output=True, text=True,
                             timeout=20, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted({line.strip() for line in out.splitlines() if line.strip() and "DejaVu" not in line})


# ---------- validation ----------

def _keys(obj, allowed: set, label: str):
    if not isinstance(obj, dict):
        raise StyleError(f"{label} must be an object")
    for k in obj:
        if k in CANT_DRAW:
            raise StyleError(f"{label}.{k}: the renderer can't draw {CANT_DRAW[k]} yet, so this pack can't be installed")
    extra = sorted(set(obj) - allowed)
    if extra:
        raise StyleError(f"{label}: unknown key {extra[0]!r} (allowed: {', '.join(sorted(allowed))})")


def _num(v, label, lo, hi, kind=float):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or (kind is int and int(v) != v) or not lo <= v <= hi:
        raise StyleError(f"{label} must be a number from {lo} to {hi}")
    return kind(v)


def _text(v, label, n=200):
    if not isinstance(v, str) or not v.strip() or len(v) > n:
        raise StyleError(f"{label} must be text of 1-{n} characters")
    return v


def _color(v, label):
    if not isinstance(v, str) or not COLOR_RE.fullmatch(v):
        raise StyleError(f"{label} must be a colour written as # and 6 hex digits (RRGGBB)")
    return v.upper()


def _rect(v, label, n=4, box=CANVAS):
    if not isinstance(v, list) or len(v) != n or not all(isinstance(x, int) and not isinstance(x, bool) for x in v):
        raise StyleError(f"{label} must be [x, y, w, h] in whole pixels")
    x, y, w, h = v
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > box[0] or y + h > box[1]:
        raise StyleError(f"{label} must sit inside the {box[0]}x{box[1]} canvas")
    return v


def _caption(obj, label, window: bool) -> dict:
    _keys(obj, set(CAPTION_KEYS), label)
    if not window:
        nope = sorted(set(obj) - CAPTION_KEYS_HOUSE_RENDERER)
        if nope:
            raise StyleError(f"{label}.{nope[0]}: the crop layout's caption renderer can't draw that yet (use layout window)")
    out = {}
    for k, v in obj.items():
        kind = CAPTION_KEYS[k]
        if kind is bool:
            if not isinstance(v, bool):
                raise StyleError(f"{label}.{k} must be true or false")
            out[k] = v
        elif kind is int:
            lim = {"font_size_px": (24, 160), "max_words": (1, 8), "max_chars": (4, 40), "outline_width_px": (0, 16),
                   "shadow_px": (0, 16), "pop_ms": (0, 500)}[k]
            out[k] = _num(v, f"{label}.{k}", *lim, kind=int)
        elif kind is float:
            lim = {"active_scale": (1.0, 1.3), "min_scale": (0.5, 1.0), "pop_from_scale": (0.5, 1.0)}[k]
            out[k] = _num(v, f"{label}.{k}", *lim)
        elif kind == "color":
            out[k] = _color(v, f"{label}.{k}")
        elif kind == "rect4":
            if not isinstance(v, list) or len(v) != 4 or not all(isinstance(x, int) and not isinstance(x, bool) for x in v) \
                    or not (0 <= v[0] < v[2] <= CANVAS[0] and 0 <= v[1] < v[3] <= CANVAS[1]):
                raise StyleError(f"{label}.safe_rect must be [left, top, right, bottom] inside the canvas")
            out[k] = v
        elif isinstance(kind, tuple):
            if v not in kind:
                raise StyleError(f"{label}.{k} must be one of {', '.join(kind)}")
            out[k] = v
        else:
            out[k] = v
    if "font" in out:
        out["font_path"] = resolve_font(out.pop("font"), f"{label}.font")
    return out


def _layer(obj, i, slots: set, names: set) -> dict:
    label = f"text_layers[{i}]"
    _keys(obj, {"id", "kind", "slot", "text", "runs", "font", "size_px", "color", "letter_spacing_px", "uppercase", "top_px",
                "bottom_margin_px", "top_by_lines", "max_lines", "max_width_px", "outline_width_px", "outline_color"}, label)
    lid = obj.get("id")
    if not isinstance(lid, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,23}", lid) or lid in names:
        raise StyleError(f"{label}.id must be a short unique lowercase name")
    kind = obj.get("kind")
    if kind not in ("slot", "fixed"):
        raise StyleError(f"{label}.kind must be 'slot' (text per Short, e.g. title) or 'fixed' (same text every Short)")
    out = {"id": lid, "kind": kind, "size_px": _num(obj.get("size_px"), f"{label}.size_px", 16, 200, int),
           "letter_spacing_px": _num(obj.get("letter_spacing_px", 0), f"{label}.letter_spacing_px", 0, 40, int),
           "uppercase": bool(obj.get("uppercase", False)), "max_lines": _num(obj.get("max_lines", 1), f"{label}.max_lines", 1, 3, int),
           "max_width_px": _num(obj.get("max_width_px", 960), f"{label}.max_width_px", 100, CANVAS[0], int),
           "outline_width_px": _num(obj.get("outline_width_px", 0), f"{label}.outline_width_px", 0, 16, int)}
    if "outline_color" in obj:
        out["outline_color"] = _color(obj["outline_color"], f"{label}.outline_color")
    if kind == "slot":
        slot = obj.get("slot", lid)
        if slot not in slots:
            raise StyleError(f"{label}.slot {slot!r} must be one of the pack's slots ({', '.join(sorted(slots)) or 'none'})")
        out["slot"] = slot
        out["font_path"] = resolve_font(obj.get("font"), f"{label}.font")
        out["color"] = _color(obj.get("color"), f"{label}.color")
    else:
        runs = obj.get("runs") or ([{"text": obj.get("text"), "font": obj.get("font"), "color": obj.get("color")}] if "text" in obj else None)
        if not isinstance(runs, list) or not 1 <= len(runs) <= 6:
            raise StyleError(f"{label}: a fixed layer needs text (or 1-6 runs of text/font/color)")
        out["runs"] = []
        for k, run in enumerate(runs):
            _keys(run, {"text", "font", "color"}, f"{label}.runs[{k}]")
            out["runs"].append({"text": _text(run.get("text"), f"{label}.runs[{k}].text", 80),
                                "font_path": resolve_font(run.get("font") or obj.get("font"), f"{label}.runs[{k}].font"),
                                "color": _color(run.get("color") or obj.get("color"), f"{label}.runs[{k}].color")})
    places = [k for k in ("top_px", "bottom_margin_px", "top_by_lines") if k in obj]
    if len(places) != 1:
        raise StyleError(f"{label}: give exactly one of top_px, bottom_margin_px or top_by_lines")
    if "top_px" in obj:
        out["top_px"] = _num(obj["top_px"], f"{label}.top_px", 0, CANVAS[1] - 1, int)
    elif "bottom_margin_px" in obj:
        out["bottom_margin_px"] = _num(obj["bottom_margin_px"], f"{label}.bottom_margin_px", 0, CANVAS[1] - 1, int)
    else:
        tb = obj["top_by_lines"]
        _keys(tb, {"of", "1", "2", "3"}, f"{label}.top_by_lines")
        if tb.get("of") not in names:
            raise StyleError(f"{label}.top_by_lines.of must name an earlier text layer")
        out["top_by_lines"] = {"of": tb["of"], **{k: _num(v, f"{label}.top_by_lines.{k}", 0, CANVAS[1] - 1, int)
                                                  for k, v in tb.items() if k != "of"}}
        if "1" not in out["top_by_lines"]:
            raise StyleError(f"{label}.top_by_lines needs at least the '1' line position")
    return out


def validate_spec(spec, files: dict | None = None) -> dict:
    """style.json -> resolved spec (font names -> installed files). files: {relpath: bytes} of the pack for references."""
    _keys(spec, TOP_KEYS, "style.json")
    if spec.get("schema") != SCHEMA:
        raise StyleError(f"style.json schema must be {SCHEMA!r}")
    sid = spec.get("id")
    if not isinstance(sid, str) or not ID_RE.fullmatch(sid):
        raise StyleError("style.json id must be 3-48 lowercase letters, digits and dashes, e.g. 'novairecito-window-noir'")
    if sid == HOUSE_ID:
        raise StyleError(f"{HOUSE_ID} is built in and can't be replaced by a pack")
    version = str(spec.get("version", ""))
    if not VERSION_RE.fullmatch(version):
        raise StyleError("style.json version must be a whole number 1-9999 (bump it for every change)")
    out = {"schema": SCHEMA, "id": sid, "version": version, "name": _text(spec.get("name"), "name", 60),
           "author": _text(spec.get("author"), "author", 80)}
    if "description" in spec:
        out["description"] = _text(spec["description"], "description", 600)
    layout = spec.get("layout", {"mode": "crop"})
    _keys(layout, {"mode", "rect", "background", "grade"}, "layout")
    mode = layout.get("mode", "crop")
    if mode not in ("crop", "window"):
        raise StyleError(f"layout.mode {mode!r}: the renderer can draw only 'crop' (the house 9:16 face crop) or 'window' yet")
    window = mode == "window"
    out["layout"] = {"mode": mode}
    if window:
        out["layout"]["rect"] = _rect(layout.get("rect"), "layout.rect")
        out["layout"]["background"] = _color(layout["background"], "layout.background") if "background" in layout else None
        if "grade" in layout:
            _keys(layout["grade"], {"contrast", "saturation"}, "layout.grade")
            out["layout"]["grade"] = {k: _num(v, f"layout.grade.{k}", 0.5, 1.5) for k, v in layout["grade"].items()}
    elif set(layout) - {"mode"}:
        raise StyleError("layout: rect, background and grade only apply to layout mode 'window'")
    preset = spec.get("preset", {})
    _keys(preset, {"caption", "editorial"}, "preset")
    out["preset"] = {}
    if "caption" in preset:
        out["preset"]["caption"] = _caption(preset["caption"], "preset.caption", window)
    if "editorial" in preset:
        _keys(preset["editorial"], set(EDITORIAL_KEYS), "preset.editorial")
        ed = {}
        for k, v in preset["editorial"].items():
            if EDITORIAL_KEYS[k] is bool:
                if not isinstance(v, bool):
                    raise StyleError(f"preset.editorial.{k} must be true or false")
                ed[k] = v
            else:
                ed[k] = _num(v, f"preset.editorial.{k}", 0.05, 2.0)
        out["preset"]["editorial"] = ed
    if window and "safe_rect" not in out["preset"].get("caption", {}):
        raise StyleError("preset.caption.safe_rect is required with layout window (where the caption band is)")
    slots = spec.get("slots", {})
    _keys(slots, {"title", "tagline", "subtitle", "kicker"}, "slots")
    out["slots"] = {}
    for name, rule in slots.items():
        _keys(rule, {"required", "max_chars", "alternates", "hint"}, f"slots.{name}")
        out["slots"][name] = {"required": bool(rule.get("required", True)),
                              "max_chars": _num(rule.get("max_chars", 60), f"slots.{name}.max_chars", 4, 120, int),
                              "alternates": _num(rule.get("alternates", 0), f"slots.{name}.alternates", 0, 5, int),
                              "hint": _text(rule.get("hint", name), f"slots.{name}.hint", 400)}
    layers = spec.get("text_layers", [])
    if not isinstance(layers, list) or len(layers) > 6:
        raise StyleError("text_layers must be a list of up to 6 layers")
    if layers and not window:
        raise StyleError("text_layers: the crop layout's renderer can't draw persistent text layers yet (use layout window)")
    out["text_layers"], names = [], set()
    for i, layer in enumerate(layers):
        out["text_layers"].append(_layer(layer, i, set(out["slots"]), names))
        names.add(layer["id"])
    if "inserts" in spec:
        ins = spec["inserts"]
        _keys(ins, {"box", "fit", "background", "fade_in_s", "fade_out_s", "media", "pacing"}, "inserts")
        if not window:
            raise StyleError("inserts: the crop layout keeps the house full-screen inserts; an insert box needs layout window")
        if ins.get("fit", "contain") != "contain":
            raise StyleError("inserts.fit: the renderer can only contain-fit inserts in a box yet")
        if ins.get("media", ["image"]) != ["image"]:
            raise StyleError("inserts.media: the renderer can only draw still images in an insert box yet")
        r = {"box": _rect(ins.get("box"), "inserts.box"), "fit": "contain",
             "background": _color(ins["background"], "inserts.background") if "background" in ins else None,
             "fade_in_s": _num(ins.get("fade_in_s", 0), "inserts.fade_in_s", 0, 2),
             "fade_out_s": _num(ins.get("fade_out_s", 0), "inserts.fade_out_s", 0, 2), "media": ["image"]}
        if "pacing" in ins:
            p = ins["pacing"]
            _keys(p, {"min_s", "max_s", "share_min", "share_max", "first_by_s", "min_gap_s", "max_per_s", "required"}, "inserts.pacing")
            r["pacing"] = {k: _num(v, f"inserts.pacing.{k}", 0, 600) for k, v in p.items() if k != "required"}
            r["pacing"]["required"] = bool(p.get("required", True))
            for a, b in (("min_s", "max_s"), ("share_min", "share_max")):
                if a in r["pacing"] and b in r["pacing"] and r["pacing"][a] > r["pacing"][b]:
                    raise StyleError(f"inserts.pacing.{a} must not be above {b}")
            for k in ("share_min", "share_max"):
                if r["pacing"].get(k, 0) > 1:
                    raise StyleError(f"inserts.pacing.{k} is a share of the runtime from 0 to 1")
        out["inserts"] = r
    if "joins" in spec:
        _keys(spec["joins"], {"punch_in"}, "joins")
        if not window:
            raise StyleError("joins.punch_in: the crop layout's renderer can't punch in yet (use layout window)")
        out["joins"] = {"punch_in": _num(spec["joins"].get("punch_in", 1.0), "joins.punch_in", 1.0, 1.3)}
    if "finish" in spec:
        f = spec["finish"]
        _keys(f, {"fade_in_s", "fade_out_s", "loudness_lufs", "true_peak_db"}, "finish")
        if not window:
            raise StyleError("finish: the crop layout uses James' encode.py unchanged; fades and loudness need layout window")
        out["finish"] = {"fade_in_s": _num(f.get("fade_in_s", 0), "finish.fade_in_s", 0, 2),
                         "fade_out_s": _num(f.get("fade_out_s", 0), "finish.fade_out_s", 0, 2)}
        if ("loudness_lufs" in f) != ("true_peak_db" in f):
            raise StyleError("finish: give loudness_lufs and true_peak_db together")
        if "loudness_lufs" in f:
            out["finish"]["loudness_lufs"] = _num(f["loudness_lufs"], "finish.loudness_lufs", -30, -8)
            out["finish"]["true_peak_db"] = _num(f["true_peak_db"], "finish.true_peak_db", -9, 0)
    rules = spec.get("agent_rules", {})
    _keys(rules, set(AGENT_RULES), "agent_rules")
    out["agent_rules"] = {k: _text(v, f"agent_rules.{k}", 4000) for k, v in rules.items()}
    refs = spec.get("references", [])
    if not isinstance(refs, list) or not 1 <= len(refs) <= 3:
        raise StyleError("references must list 1-3 reference Shorts (links or files in references/)")
    out["references"] = []
    for i, ref in enumerate(refs):
        _keys(ref, {"title", "url", "file", "duration_s", "notes"}, f"references[{i}]")
        row = {"title": _text(ref.get("title"), f"references[{i}].title", 120)}
        if ("url" in ref) == ("file" in ref):
            raise StyleError(f"references[{i}] needs exactly one of url or file")
        if "url" in ref:
            if not isinstance(ref["url"], str) or not re.fullmatch(r"https://[^\s]{4,400}", ref["url"]):
                raise StyleError(f"references[{i}].url must be an https link")
            row["url"] = ref["url"]
        else:
            if not isinstance(ref["file"], str) or not REF_RE.fullmatch(ref["file"]) or files is None or ref["file"] not in files:
                raise StyleError(f"references[{i}].file must name a file shipped in the pack under references/")
            row["file"] = ref["file"]
        if "duration_s" in ref:
            row["duration_s"] = _num(ref["duration_s"], f"references[{i}].duration_s", 1, 180)
        if "notes" in ref:
            row["notes"] = _text(ref["notes"], f"references[{i}].notes", 600)
        out["references"].append(row)
    if window and not out["preset"].get("caption", {}).get("font_path"):
        raise StyleError("preset.caption.font is required with layout window")
    return out


def decode_pack(pack) -> dict[str, bytes]:
    """{'files': {path: text | {'base64': ...}}} -> {path: bytes}. Data only: style.json, STYLE.md, references/*."""
    if not isinstance(pack, dict) or set(pack) != {"files"} or not isinstance(pack["files"], dict):
        raise StyleError("pack must be {'files': {path: text or {'base64': ...}}}")
    out, total = {}, 0
    for rel, value in pack["files"].items():
        if not isinstance(rel, str):
            raise StyleError("file names must be text")
        suffix = Path(rel).suffix.lower()
        if suffix in SCRIPT_KINDS or (isinstance(value, str) and value.startswith("#!")):
            raise StyleError(f"{rel}: packs hold data only; scripts and code files are refused")
        if rel not in ("style.json", "STYLE.md") and not REF_RE.fullmatch(rel):
            raise StyleError(f"{rel}: not allowed in a pack (only style.json, STYLE.md and references/<name>.mp4|jpg|png|webp)")
        if isinstance(value, str):
            if rel.startswith("references/"):
                raise StyleError(f"{rel}: reference files must be sent as {{'base64': ...}}")
            data = value.encode()
        elif isinstance(value, dict) and set(value) == {"base64"} and isinstance(value["base64"], str):
            try:
                data = base64.b64decode(value["base64"], validate=True)
            except ValueError:
                raise StyleError(f"{rel}: invalid base64") from None
        else:
            raise StyleError(f"{rel}: value must be text or {{'base64': ...}}")
        if rel.startswith("references/"):
            if len(data) > REF_MAX or not MAGIC[suffix](data[:16]):
                raise StyleError(f"{rel}: must be a real {suffix} file of at most {REF_MAX >> 20} MiB")
        else:
            if len(data) > TEXT_MAX:
                raise StyleError(f"{rel}: at most {TEXT_MAX >> 10} KiB")
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                raise StyleError(f"{rel}: must be UTF-8 text") from None
        total += len(data)
        out[rel] = data
    if total > PACK_MAX:
        raise StyleError(f"the pack is over {PACK_MAX >> 20} MiB")
    if "style.json" not in out or "STYLE.md" not in out:
        raise StyleError("a pack needs style.json and STYLE.md")
    if len([r for r in out if r.startswith("references/")]) > 3:
        raise StyleError("at most 3 reference files")
    return out


def pack_sha256(files: dict[str, bytes]) -> str:
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode() + b"\0" + hashlib.sha256(files[rel]).hexdigest().encode() + b"\n")
    return h.hexdigest()


def check_pack(pack) -> tuple[dict, dict[str, bytes], str]:
    files = decode_pack(pack)
    try:
        spec = json.loads(files["style.json"])
    except json.JSONDecodeError as e:
        raise StyleError(f"style.json is not valid JSON ({e.msg} at line {e.lineno})") from None
    resolved = validate_spec(spec, files)
    if not files["STYLE.md"].decode().strip():
        raise StyleError("STYLE.md is empty: it is the editing guide the agent follows for this style")
    return resolved, files, pack_sha256(files)


# ---------- registry ----------

def _dir(sid: str, version: str) -> Path:
    if not ID_RE.fullmatch(sid or "") or not VERSION_RE.fullmatch(str(version or "")):
        raise StyleError("style id or version is not valid")
    return ROOT / sid / str(version)


def _status(d: Path) -> dict:
    try:
        return json.loads((d / "status.json").read_text())
    except (OSError, ValueError):
        return {}


def _write_status(d: Path, st: dict):
    tmp = d / "status.json.tmp"
    tmp.write_text(json.dumps(st, indent=2))
    tmp.replace(d / "status.json")


def install(pack, publisher: str | None = None) -> dict:
    """Validate and store one pack version. The same bytes again are a no-op; other bytes under an existing version are refused."""
    resolved, files, digest = check_pack(pack)
    d = _dir(resolved["id"], resolved["version"])
    if d.is_dir():
        st = _status(d)
        if st.get("sha256") == digest:
            return describe(resolved["id"], resolved["version"])
        raise StyleError(f"{resolved['id']} version {resolved['version']} is already installed with different content; bump version")
    staging = d.with_name(d.name + ".new")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, mode=0o700)
    for rel, data in files.items():
        (staging / rel).parent.mkdir(parents=True, exist_ok=True)
        (staging / rel).write_bytes(data)
    (staging / "resolved.json").write_text(json.dumps(resolved, indent=2))
    _write_status(staging, {"sha256": digest, "installed_at": time.time(), "publisher": (publisher or "")[:200],
                            "test": None, "retired": False})
    staging.rename(d)
    return describe(resolved["id"], resolved["version"])


def house() -> dict:
    return {"id": HOUSE_ID, "version": HOUSE_VERSION, "name": "DeFleur house", "author": "James DeFleur", "builtin": True,
            "default": True, "layout": {"mode": "crop"}, "selectable": True, "retired": False,
            "test": {"pass": True, "note": "built in: today's preset and rules, unchanged"},
            "summary": "James DeFleur's house Shorts: fixed 9:16 face crop, motion graphics, ALL CAPS captions with the green spoken word."}


def describe(sid: str, version: str) -> dict:
    if sid == HOUSE_ID and str(version) == HOUSE_VERSION:
        return house()
    d = _dir(sid, version)
    if not (d / "resolved.json").is_file():
        raise StyleError(f"style {sid} version {version} is not installed")
    spec = json.loads((d / "resolved.json").read_text())
    st = _status(d)
    test = st.get("test")
    return {"id": sid, "version": str(version), "name": spec["name"], "author": spec["author"], "builtin": False, "default": False,
            "layout": {"mode": spec["layout"]["mode"]}, "slots": spec.get("slots", {}), "sha256": st.get("sha256"),
            "installed_at": st.get("installed_at"), "publisher": st.get("publisher"), "test": test,
            "retired": bool(st.get("retired")), "selectable": bool(test and test.get("pass")) and not st.get("retired"),
            "references": spec.get("references", [])}


def listing(include_hidden: bool = False) -> list[dict]:
    rows = [house()]
    if ROOT.is_dir():
        for sd in sorted(p for p in ROOT.iterdir() if p.is_dir() and ID_RE.fullmatch(p.name)):
            for vd in sorted((p for p in sd.iterdir() if p.is_dir() and VERSION_RE.fullmatch(p.name)), key=lambda p: int(p.name)):
                try:
                    row = describe(sd.name, vd.name)
                except (StyleError, OSError, ValueError):
                    continue
                if include_hidden or row["selectable"]:
                    rows.append(row)
    return rows


def resolve(sid: str | None, version: str | None = None, allow_untested: bool = False) -> dict | None:
    """None for the house style (nothing changes); else {id, version, sha256, spec, style_md} of a selectable pack."""
    if sid in (None, "", HOUSE_ID):
        if version not in (None, "", HOUSE_VERSION):
            raise StyleError(f"{HOUSE_ID} has only version {HOUSE_VERSION}")
        return None
    if not isinstance(sid, str) or not ID_RE.fullmatch(sid):
        raise StyleError("style must be a style id from capabilities.styles (or omit it for the house style)")
    if version in (None, ""):
        versions = [r for r in listing(include_hidden=allow_untested) if r["id"] == sid and (allow_untested or r["selectable"])]
        if not versions:
            raise StyleError(f"style {sid!r} has no version that passed its test render (see capabilities.styles)")
        version = versions[-1]["version"]
    version = str(version)
    row = describe(sid, version)
    if not allow_untested and row["retired"]:
        raise StyleError(f"style {sid} version {version} is retired")
    if not allow_untested and not row["selectable"]:
        raise StyleError(f"style {sid} version {version} hasn't passed its test render yet")
    d = _dir(sid, version)
    return {"id": sid, "version": version, "sha256": row["sha256"], "spec": json.loads((d / "resolved.json").read_text()),
            "style_md": (d / "STYLE.md").read_text()}


def record_test(sid: str, version: str, result: dict) -> dict:
    d = _dir(sid, version)
    st = _status(d)
    st["test"] = {**result, "at": time.time()}
    _write_status(d, st)
    return describe(sid, version)


def retire(sid: str, version: str | None, retired: bool = True) -> list[dict]:
    if sid == HOUSE_ID:
        raise StyleError(f"{HOUSE_ID} is the default and can't be retired")
    vs = [version] if version else [p.name for p in (ROOT / sid).iterdir() if VERSION_RE.fullmatch(p.name)] if (ROOT / sid).is_dir() else []
    if not vs:
        raise StyleError(f"style {sid!r} is not installed")
    out = []
    for v in vs:
        d = _dir(sid, v)
        if not d.is_dir():
            raise StyleError(f"style {sid} version {v} is not installed")
        st = _status(d)
        st["retired"] = bool(retired)
        _write_status(d, st)
        out.append(describe(sid, v))
    return out


# ---------- agent contract ----------

def apply_rules(guide: dict, contract: dict, chosen: dict | None) -> tuple[dict, dict]:
    """Copies of GUIDE and MOTION_CONTRACT with the style-specific parts replaced by the pack's rules. House: unchanged objects."""
    if not chosen:
        return guide, contract
    spec = chosen["spec"]
    rules = spec.get("agent_rules", {})
    c = json.loads(json.dumps(contract))
    g = json.loads(json.dumps(guide))
    if "caption_band" in rules:
        c["page_rules"] = [rules["caption_band"] if "captions live in" in r else r for r in c["page_rules"]]
    if "beat_layout" in rules:
        head = c["beat_rules"].split("James' house layout:")[0]
        c["beat_rules"] = head + rules["beat_layout"]
    for key in ("captions", "inserts", "sequence"):
        if key in rules:
            c[key] = rules[key] if key != "sequence" else [s.strip() for s in rules[key].split("\n") if s.strip()]
    if "default_edit" in rules:
        g["default_edit"] = rules["default_edit"]
    g["motion_contract"] = c
    g["style"] = {"id": chosen["id"], "version": chosen["version"], "name": spec["name"], "author": spec["author"],
                  "layout": spec["layout"], "STYLE.md": chosen["style_md"], "slots": spec.get("slots", {}),
                  "approval": rules.get("approval"), "insert_box": spec.get("inserts"), "joins": spec.get("joins"),
                  "note": ("This project uses this style: follow its STYLE.md and the replaced rules above; where they differ from "
                           "James' house text, the style wins.")}
    return g, c


def pacing_problems(plan: dict, spec: dict, duration: float | None) -> list[str]:
    """Plain reasons a plan breaks the pack's insert pacing (empty when it fits or the pack has no pacing)."""
    ins_rule = spec.get("inserts")
    if not ins_rule or not ins_rule.get("pacing"):
        return []
    p = ins_rule["pacing"]
    ins = plan.get("inserts", []) or []
    out = []
    if not ins:
        return ["this style needs image inserts (STYLE.md pacing); the plan has none"] if p.get("required", True) else []
    for i, r in enumerate(ins):
        d = float(r["end"]) - float(r["start"])
        if "min_s" in p and d < p["min_s"] - 1e-6:
            out.append(f"insert {i} holds {d:.2f} s; this style holds each image at least {p['min_s']:g} s")
        if "max_s" in p and d > p["max_s"] + 1e-6:
            out.append(f"insert {i} holds {d:.2f} s; this style holds each image at most {p['max_s']:g} s")
        if Path(str(r.get("asset", ""))).suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            out.append(f"insert {i}: this style's insert box takes still images (.png/.jpg/.webp) only")
        if r.get("fit", "contain") != "contain":
            out.append(f"insert {i}: this style contain-fits images in its box (fit 'contain')")
    for i in range(1, len(ins)):
        gap = float(ins[i]["start"]) - float(ins[i - 1]["end"])
        if "min_gap_s" in p and gap < p["min_gap_s"] - 1e-6:
            out.append(f"inserts {i - 1} and {i} are {gap:.2f} s apart; this style keeps at least {p['min_gap_s']:g} s of live footage between images")
    if "first_by_s" in p and float(ins[0]["start"]) > p["first_by_s"] + 1e-6:
        out.append(f"the first image starts at {float(ins[0]['start']):.2f} s; this style shows one by {p['first_by_s']:g} s")
    if duration:
        share = sum(float(r["end"]) - float(r["start"]) for r in ins) / duration
        if "share_min" in p and share < p["share_min"] - 1e-6:
            out.append(f"images cover {share:.0%} of the runtime; this style wants {p['share_min']:.0%}-{p.get('share_max', 1):.0%}")
        if "share_max" in p and share > p["share_max"] + 1e-6:
            out.append(f"images cover {share:.0%} of the runtime; this style wants {p.get('share_min', 0):.0%}-{p['share_max']:.0%}")
        if "max_per_s" in p and p["max_per_s"] > 0 and len(ins) > duration / p["max_per_s"] + 1e-6:
            out.append(f"{len(ins)} images in {duration:.1f} s; this style allows at most 1 per {p['max_per_s']:g} s ({int(duration // p['max_per_s'])})")
    return out


def check_slots(spec: dict, slots) -> dict:
    rules = spec.get("slots", {})
    if not rules:
        if slots:
            raise StyleError("this style has no text slots; leave slots out")
        return {}
    if not isinstance(slots, dict) or set(slots) - set(rules):
        raise StyleError(f"slots must be an object with {', '.join(sorted(rules))}")
    out = {}
    for name, rule in rules.items():
        v = slots.get(name)
        if v is None or (isinstance(v, str) and not v.strip()):
            if rule["required"]:
                raise StyleError(f"slot {name!r} is required in this style ({rule['hint']}); get it approved with the cut and image plan")
            continue
        if not isinstance(v, str) or len(v.strip()) > rule["max_chars"] or "\n" in v:
            raise StyleError(f"slot {name!r} must be one line of at most {rule['max_chars']} characters")
        out[name] = v.strip()
    return out


def check_joins(joins, duration: float | None = None) -> list[float]:
    if joins in (None, []):
        return []
    if not isinstance(joins, list) or len(joins) > 4 or not all(isinstance(t, (int, float)) and not isinstance(t, bool) and t > 0 for t in joins) \
            or joins != sorted(joins) or (duration is not None and joins[-1] >= duration):
        raise StyleError("joins must be up to 4 increasing source seconds where the excerpt jumps to a later range")
    return [round(float(t), 3) for t in joins]


def caption_style(spec: dict, house_caption: dict) -> dict:
    """The caption block a style renders with: the resolved house caption, the pack's caption keys on top."""
    out = {k: v for k, v in house_caption.items() if not k.endswith("_note")}
    out.update(spec.get("preset", {}).get("caption", {}))
    return out


def pack_from_dir(folder: Path) -> dict:
    """A pack folder (style.json, STYLE.md, references/) -> the {'files': ...} shape install() takes."""
    files = {}
    for p in sorted(Path(folder).rglob("*")):
        if p.is_file():
            rel = p.relative_to(folder).as_posix()
            files[rel] = p.read_text() if rel in ("style.json", "STYLE.md") else {"base64": base64.b64encode(p.read_bytes()).decode()}
    return {"files": files}


def check_resolved(spec: dict) -> dict:
    """A resolved spec passed back in a stage input: schema, layout mode and every font file still installed here."""
    if not isinstance(spec, dict) or spec.get("schema") != SCHEMA or spec.get("layout", {}).get("mode") not in ("crop", "window"):
        raise StyleError("not a resolved style pack")
    fonts = [spec.get("preset", {}).get("caption", {}).get("font_path")]
    for layer in spec.get("text_layers", []):
        fonts += [layer.get("font_path")] + [r["font_path"] for r in layer.get("runs", [])]
    for f in fonts:
        if f is not None and (not isinstance(f, str) or not f.startswith(FONT_DIR) or ".." in f or not Path(f).is_file()):
            raise StyleError(f"font {f} isn't installed on this server")
    if spec["layout"]["mode"] == "window" and not spec.get("preset", {}).get("caption", {}).get("safe_rect"):
        raise StyleError("a window style needs its caption band")
    return spec
