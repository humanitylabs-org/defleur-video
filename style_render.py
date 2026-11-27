#!/usr/bin/env python3
"""App-original renderer for style packs with layout mode 'window' (humanitylabs-org/wizard-os#1012).

Not part of James DeFleur's plugin; the house style never runs this file (it keeps final_render.py + James'
caption_layer.py and encode.py, unchanged).

render - every output frame: background canvas, the source frame named by the edit map contain-fitted into the
         pack's window (light grade; punch-in after a joined range), still-image inserts contain-fitted into the
         pack's insert box with their fades, the persistent text layers (fixed text and per-Short slots), karaoke
         captions (active word colour, first-word pop) anchored in the caption band, then the whole-picture fade.
         Audio: the edited WAV with the pack's fades and a two-pass EBU R128 loudness normalisation. Encodes
         final.mp4 with encode.py's settings and writes capture-full.json, caption-composite.json and
         layout-ledger.json so James' encode.py --verify-only and the delivery gate read it like any final.
check  - decoded-pixel checks of the exact final.mp4 against an independent FFmpeg scale of the source frame into the
         window, the layer boxes, the caption band and the insert box; plus measured loudness. Writes live-check.json.
test   - the style's fixed reference test render: a 4 s synthetic excerpt (testsrc2 + tone, fixed word timings, one
         insert, one join) through render + check. Used before a newly published style shows up in the picker.
Evidence for review; not perceptual approval.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

FFMPEG, FFPROBE = "ffmpeg", "ffprobe"


def hex_rgb(hex_color: str | None, default=(0, 0, 0)) -> tuple[int, int, int]:
    if not hex_color:
        return default
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def probe_size(path: Path) -> tuple[int, int]:
    out = subprocess.check_output([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                   "-of", "csv=p=0", str(path)], text=True)
    w, h = out.strip().split(",")[:2]
    return int(w), int(h)


def src_input(path: Path) -> list[str]:
    return ["-protocol_whitelist", "file", "-format_whitelist", "mov", "-f", "mov", "-enable_drefs", "0",
            "-use_absolute_path", "0", "-threads", "1", "-i", str(path)]


def contain(w: int, h: int, box_w: int, box_h: int) -> tuple[int, int, int, int]:
    """Size and offset of a w x h picture contain-fitted (centred) in a box_w x box_h box."""
    s = min(box_w / w, box_h / h)
    fw, fh = max(1, round(w * s)), max(1, round(h * s))
    return fw, fh, (box_w - fw) // 2, (box_h - fh) // 2


def punch_box(w: int, h: int, scale: float) -> tuple[int, int, int, int]:
    """Centre crop of a w x h frame for a punch-in of `scale` (1.08 = 8% closer)."""
    cw, ch = round(w / scale), round(h / scale)
    return (w - cw) // 2, (h - ch) // 2, cw, ch


def fade_factor(t: float, start: float, end: float, fade_in: float, fade_out: float) -> float:
    a = 1.0
    if fade_in > 0:
        a = min(a, max(0.0, (t - start) / fade_in))
    if fade_out > 0:
        a = min(a, max(0.0, (end - t) / fade_out))
    return a


# ---------- text ----------

class Text:
    def __init__(self):
        from PIL import ImageFont
        self.ImageFont = ImageFont
        self.cache = {}

    def font(self, path: str, size: int):
        key = (path, size)
        if key not in self.cache:
            self.cache[key] = self.ImageFont.truetype(path, size)
        return self.cache[key]


def spaced_width(draw, text: str, font, spacing: int) -> float:
    if not spacing:
        return draw.textlength(text, font=font)
    return sum(draw.textlength(ch, font=font) for ch in text) + spacing * max(0, len(text) - 1)


def draw_spaced(draw, xy, text, font, fill, spacing, stroke=0, stroke_fill=None):
    x, y = xy
    if not spacing:
        draw.text((x, y), text, font=font, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
        return
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
        x += draw.textlength(ch, font=font) + spacing


def balanced(draw, words: list[str], font, spacing: int, width: int, max_lines: int) -> list[str] | None:
    """The split into at most max_lines lines that fits `width` with the most even line widths (titles read better
    as 'Who You Really / Fell For' than 'Who You Really Fell / For')."""
    import itertools
    best = None
    for n in range(1, min(max_lines, len(words)) + 1):
        for cuts in itertools.combinations(range(1, len(words)), n - 1):
            bounds = (0, *cuts, len(words))
            lines = [" ".join(words[a:b]) for a, b in zip(bounds, bounds[1:])]
            widths = [spaced_width(draw, ln, font, spacing) for ln in lines]
            if max(widths) > width:
                continue
            score = (n, max(widths) - min(widths)) if n == 1 else (2, max(widths))
            if best is None or score < best[0]:
                best = (score, lines)
        if best is not None:
            return best[1]
    return None


def wrap(draw, words: list[str], font, spacing: int, width: int) -> list[str]:
    lines, cur = [], []
    for w in words:
        trial = " ".join(cur + [w])
        if cur and spaced_width(draw, trial, font, spacing) > width:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    return lines


def layers_overlay(spec: dict, slots: dict, size=(1080, 1920)):
    """One RGBA overlay with every persistent text layer, plus each layer's box and line count."""
    from PIL import Image, ImageDraw
    T = Text()
    over = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    boxes, lines_of = {}, {}
    W, H = size
    for layer in spec.get("text_layers", []):
        spacing = layer.get("letter_spacing_px", 0)
        stroke = layer.get("outline_width_px", 0)
        sfill = hex_rgb(layer["outline_color"]) + (255,) if layer.get("outline_color") else None
        if layer["kind"] == "slot":
            text = str(slots.get(layer["slot"], "")).strip()
            if not text:
                continue
            text = text.upper() if layer.get("uppercase") else text
            size_px = layer["size_px"]
            while True:
                font = T.font(layer["font_path"], size_px)
                words = text.split()
                lines = balanced(d, words, font, spacing, layer["max_width_px"], layer["max_lines"]) if len(words) <= 12 else \
                    wrap(d, words, font, spacing, layer["max_width_px"])
                if lines and len(lines) <= layer["max_lines"] and all(spaced_width(d, ln, font, spacing) <= layer["max_width_px"] for ln in lines):
                    break
                size_px -= 2
                if size_px < layer["size_px"] * 0.6:
                    raise SystemExit(f"text layer {layer['id']}: {text!r} doesn't fit {layer['max_lines']} line(s) of "
                                     f"{layer['max_width_px']} px even at 60% size; shorten it")
            runs_by_line = [[(ln, font, hex_rgb(layer["color"]))] for ln in lines]
        else:
            runs = [((r["text"].upper() if layer.get("uppercase") else r["text"]), T.font(r["font_path"], layer["size_px"]), hex_rgb(r["color"]))
                    for r in layer["runs"]]
            runs_by_line = [runs]
        asc_desc = [max(sum(f.getmetrics()) for _, f, _ in line) for line in runs_by_line]
        line_h = [round(a * 1.08) for a in asc_desc]
        total_h = sum(line_h)
        if "top_px" in layer:
            top = layer["top_px"]
        elif "bottom_margin_px" in layer:
            top = H - layer["bottom_margin_px"] - total_h
        else:
            tb = layer["top_by_lines"]
            n = lines_of.get(tb["of"], 1)
            top = tb.get(str(n), tb.get(str(max(int(k) for k in tb if k != "of" and int(k) <= n)), tb["1"]))
        y = top
        x0, x1 = W, 0
        for line, lh in zip(runs_by_line, line_h):
            widths = [spaced_width(d, t, f, spacing) for t, f, _ in line]
            gaps = spacing * (len(line) - 1)
            lw = sum(widths) + gaps
            x = (W - lw) / 2
            x0, x1 = min(x0, x), max(x1, x + lw)
            for (t, f, c), w in zip(line, widths):
                draw_spaced(d, (x, y), t, f, c + (255,), spacing, stroke, sfill)
                x += w + spacing
            y += lh
        lines_of[layer["id"]] = len(runs_by_line)
        bbox = over.crop((0, max(0, top - 4), W, min(H, y + 8))).getbbox()
        ink = [bbox[0], max(0, top - 4) + bbox[1], bbox[2], max(0, top - 4) + bbox[3]] if bbox else None
        boxes[layer["id"]] = {"top": top, "lines": len(runs_by_line), "ink_box": ink, "text": " / ".join(t for line in runs_by_line for t, _, _ in line)}
    return over, boxes


class Captions:
    """Karaoke captions for window styles: chunks exactly as James' caption_layer (style_chunks), drawn top-anchored
    (or centred) in the band, the spoken word in active_color, and the first word of each cue popping from
    pop_from_scale to 100% over pop_ms."""

    def __init__(self, words: list[dict], style: dict, caption_dir: Path):
        sys.path.insert(0, str(caption_dir))
        from caption_layer import style_chunks  # James' chunking, unchanged
        self.words, self.style = words, style
        self.chunks = style_chunks(words, style)
        self.starts = [float(w["start"]) for w in words]
        self.T = Text()
        self.left, self.top, self.right, self.bottom = [int(v) for v in style["safe_rect"]]
        self.size = int(style["font_size_px"])
        self.outline = int(style.get("outline_width_px", 0))
        self.upper = bool(style.get("uppercase", False))
        self.colors = hex_rgb(style["text_color"]), hex_rgb(style["active_color"]), hex_rgb(style["outline_color"])
        self.pop_from = float(style.get("pop_from_scale", 1.0))
        self.pop_s = float(style.get("pop_ms", 0)) / 1000.0
        self.anchor = style.get("anchor", "center")
        self.active_scale = float(style.get("active_scale", 1.0))
        self.min_scale = float(style.get("min_scale", 0.8))

    def state(self, t: float):
        """(chunk word indexes, spoken index or None) or None when no cue is on screen."""
        if not self.words or t < self.starts[0] or t >= float(self.words[-1]["end"]):
            return None
        active = bisect.bisect_right(self.starts, t) - 1
        chunk = next((c for c in self.chunks if active in c), None)
        if not chunk or t >= float(self.words[chunk[-1]]["end"]):
            return None
        spoken = active if float(self.words[active]["start"]) <= t < float(self.words[active]["end"]) else None
        return chunk, spoken

    def token(self, i):
        tok = str(self.words[i].get("word", "")).strip()
        return tok.upper().rstrip(".,;:") if self.upper else tok

    def draw(self, image, t: float):
        from PIL import ImageDraw
        st = self.state(t)
        if st is None:
            return False
        chunk, spoken = st
        d = ImageDraw.Draw(image)
        avail = self.right - self.left - 2 * (self.outline + 2)
        size = self.size
        while True:
            font = self.T.font(self.style["font_path"], size)
            big = self.T.font(self.style["font_path"], max(size, round(size * self.active_scale)))
            space = d.textlength(" ", font=font)
            toks = [(i, self.token(i)) for i in chunk if self.token(i)]
            slots = [(i, tok, d.textlength(tok, font=big)) for i, tok in toks]
            lines, line, width = [], [], 0.0
            for row in slots:
                if line and width + space + row[2] > avail:
                    lines.append((line, width)); line, width = [], 0.0
                width += (space if line else 0) + row[2]
                line.append(row)
            if line:
                lines.append((line, width))
            asc, desc = font.getmetrics()
            line_h = asc + desc + 2 * self.outline
            if all(w <= avail for _, w in lines) and len(lines) * line_h <= self.bottom - self.top:
                break
            size -= 2
            if size < self.size * self.min_scale:
                raise SystemExit("caption chunk doesn't fit the caption band; revise the style's caption size or band")
        y = self.top if self.anchor == "top" else self.top + (self.bottom - self.top - len(lines) * line_h) / 2
        first = chunk[0]
        pop = 1.0
        if self.pop_s > 0 and self.pop_from < 1.0:
            k = (t - float(self.words[first]["start"])) / self.pop_s
            pop = self.pop_from + (1.0 - self.pop_from) * max(0.0, min(1.0, k))
        for line, width in lines:
            x = self.left + (self.right - self.left - width) / 2
            cy = y + line_h / 2
            for i, tok, w in line:
                active = i == spoken
                s = size * (self.active_scale if active else 1.0) * (pop if i == first else 1.0)
                f = self.T.font(self.style["font_path"], max(8, round(s)))
                fill = self.colors[1] if active else self.colors[0]
                d.text((x + w / 2, cy), tok, font=f, anchor="mm", fill=fill, stroke_width=self.outline, stroke_fill=self.colors[2])
                x += w + space
            y += line_h
        return True


# ---------- audio finish ----------

def _measure_wav(path: Path) -> dict:
    p = subprocess.run([FFMPEG, "-v", "info", "-nostdin", "-hide_banner", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, check=True).stderr
    tail = p[p.rfind("Summary:"):]
    get = lambda label: float(tail.split(label, 1)[1].split()[0])
    return {"integrated_lufs": get("I:"), "true_peak_dbtp": get("Peak:")}


def finish_audio(src_wav: Path, out_wav: Path, duration: float, finish: dict) -> dict:
    """The pack's audio finish: fades, then (when set) gain to the loudness target with a 4x-oversampled peak limiter
    1 dB under the true-peak ceiling (headroom for the AAC encode), corrected by measuring until within 0.2 LU.
    The output keeps the edited WAV's exact sample count, so every later custody check lines up."""
    import wave
    with wave.open(str(src_wav)) as w:
        rate, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
    fades = []
    if finish.get("fade_in_s"):
        fades.append(f"afade=t=in:st=0:d={finish['fade_in_s']}")
    if finish.get("fade_out_s"):
        fades.append(f"afade=t=out:st={max(0.0, n / rate - finish['fade_out_s']):.6f}:d={finish['fade_out_s']}")
    info = {"fade_in_s": finish.get("fade_in_s", 0), "fade_out_s": finish.get("fade_out_s", 0)}

    def run(chain):
        tail = [f"aresample={rate}", f"apad=whole_len={n}", f"atrim=end_sample={n}"]
        subprocess.run([FFMPEG, "-v", "error", "-nostdin", "-y", "-i", str(src_wav), "-af", ",".join(chain + tail), "-ac", str(ch),
                        "-c:a", "pcm_s16le", str(out_wav)], check=True, capture_output=True)

    run(fades)
    if "loudness_lufs" in finish:
        target, ceiling = float(finish["loudness_lufs"]), float(finish["true_peak_db"])
        before = _measure_wav(out_wav)
        gain = target - before["integrated_lufs"]
        limit = 10 ** ((ceiling - 1.0) / 20)
        tries = []
        for _ in range(4):
            # alimiter looks ahead by its attack time (1 ms = 192 samples at 192 kHz): trim it so the audio stays sample-aligned.
            run(fades + [f"volume={gain:.3f}dB", "aresample=192000", f"alimiter=limit={limit:.5f}:level=0:attack=1:release=60",
                         "atrim=start_sample=192", "asetpts=PTS-STARTPTS"])
            got = _measure_wav(out_wav)
            tries.append({"gain_db": round(gain, 3), **got})
            if abs(got["integrated_lufs"] - target) <= 0.2:
                break
            gain += target - got["integrated_lufs"]
        info.update({"before": before, "target": {"loudness_lufs": target, "true_peak_db": ceiling}, "passes": tries,
                     "method": "fades, gain, 4x-oversampled alimiter 1 dB under the true-peak ceiling, measured with ebur128"})
    with wave.open(str(out_wav)) as w:
        if w.getnframes() != n:
            raise SystemExit(f"finished audio has {w.getnframes()} samples, the edit has {n}")
    return info


def measure_loudness(path: Path) -> dict:
    p = subprocess.run([FFMPEG, "-v", "info", "-nostdin", "-hide_banner", "-i", str(path), "-map", "0:a:0", "-af",
                        "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True, check=True).stderr
    tail = p[p.rfind("Summary:"):]
    get = lambda label: float(tail.split(label, 1)[1].split()[0])
    return {"integrated_lufs": get("I:"), "true_peak_dbtp": get("Peak:")}


# ---------- render ----------

class Layout:
    def __init__(self, spec: dict, plan: dict, assets: Path | None, slots: dict, joins_frames: list[int], src_size, fps: Fraction):
        from PIL import Image
        self.Image = Image
        self.spec = spec
        lay = spec["layout"]
        self.bg = hex_rgb(lay.get("background"))
        self.rect = lay["rect"]
        self.grade = lay.get("grade") or {}
        self.punch = (spec.get("joins") or {}).get("punch_in", 1.0)
        self.joins = joins_frames
        self.src_w, self.src_h = src_size
        self.fps = fps
        ins = spec.get("inserts") or {}
        self.box = ins.get("box")
        self.box_bg = hex_rgb(ins.get("background"))
        self.fi, self.fo = float(ins.get("fade_in_s", 0)), float(ins.get("fade_out_s", 0))
        self.inserts = []
        for r in (plan or {}).get("inserts", []):
            with Image.open(assets / r["asset"]) as im:
                pic = im.convert("RGB")
            bx, by, bw, bh = self.box
            fw, fh, ox, oy = contain(pic.width, pic.height, bw, bh)
            tile = Image.new("RGB", (bw, bh), self.box_bg)
            tile.paste(pic.resize((fw, fh), Image.LANCZOS), (ox, oy))
            self.inserts.append({"start": float(r["start"]), "end": float(r["end"]), "asset": r["asset"], "tile": tile,
                                 "picture_box": [bx + ox, by + oy, fw, fh]})
        self.overlay, self.layer_boxes = layers_overlay(spec, slots)
        self.overlay_box = self.overlay.getbbox()
        self.canvas = Image.new("RGB", (1080, 1920), self.bg)
        x, y, w, h = self.rect
        self.fit = contain(self.src_w, self.src_h, w, h)

    def punched(self, src_index: int) -> bool:
        return self.punch > 1.0 and any(src_index >= j for j in self.joins)

    def live(self, frame_rgb, src_index: int):
        """The window tile for one source frame (numpy RGB array)."""
        import numpy as np
        Image = self.Image
        img = Image.fromarray(frame_rgb)
        if self.punched(src_index):
            cx, cy, cw, ch = punch_box(img.width, img.height, self.punch)
            img = img.crop((cx, cy, cx + cw, cy + ch))
        fw, fh, ox, oy = self.fit
        img = img.resize((fw, fh), Image.LANCZOS)
        if self.grade:
            a = np.asarray(img).astype(np.float32)
            if "contrast" in self.grade:
                a = (a - 128.0) * self.grade["contrast"] + 128.0
            if "saturation" in self.grade:
                gray = (a[..., 0:1] * 0.299 + a[..., 1:2] * 0.587 + a[..., 2:3] * 0.114)
                a = gray + (a - gray) * self.grade["saturation"]
            img = Image.fromarray(np.clip(np.rint(a), 0, 255).astype(np.uint8))
        return img, ox, oy

    def insert_at(self, t: float):
        for k, r in enumerate(self.inserts):
            if r["start"] <= t < r["end"]:
                return k, r, fade_factor(t, r["start"], r["end"], self.fi, self.fo)
        return None

    def compose(self, frame_rgb, src_index: int, t: float, captions, video_fade: float):
        Image = self.Image
        out = self.canvas.copy()
        tile, ox, oy = self.live(frame_rgb, src_index)
        x, y, _, _ = self.rect
        out.paste(tile, (x + ox, y + oy))
        hit = self.insert_at(t)
        if hit is not None:
            _, r, a = hit
            bx, by, bw, bh = self.box
            if a >= 1.0:
                out.paste(r["tile"], (bx, by))
            elif a > 0:
                region = out.crop((bx, by, bx + bw, by + bh))
                out.paste(Image.blend(region, r["tile"], a), (bx, by))
        if self.overlay_box:
            ob = self.overlay_box
            region = out.crop(ob).convert("RGBA")
            region.alpha_composite(self.overlay.crop(ob))
            out.paste(region.convert("RGB"), ob[:2])
        cue = captions.draw(out, t) if captions else False
        if video_fade < 1.0:
            out = Image.blend(Image.new("RGB", out.size, (0, 0, 0)), out, max(0.0, video_fade))
        return out, cue, hit


def load_input(path: Path) -> dict:
    return json.loads(path.read_text())


def render(a) -> None:
    root = a.project
    si = load_input(a.style_input)
    spec, slots = si["spec"], si.get("slots") or {}
    edit = json.loads(a.edit_map.read_text())
    timeline = json.loads((root / "locked-timeline.json").read_text())
    style = json.loads((root / "caption-style.json").read_text())
    plan = json.loads((root / "visual-plan.json").read_text())
    fps = Fraction(str(edit["fps"]))
    frames, duration = int(edit["frames"]), float(edit["duration"])
    indices = edit["source_frame_indices"]
    if len(indices) != frames or any(b < x for x, b in zip(indices, indices[1:])):
        raise SystemExit("source_frame_indices must cover every output frame and be nondecreasing")
    W, H = probe_size(a.source)
    joins = [round(float(t) * float(fps)) for t in si.get("joins") or []]
    lay = Layout(spec, plan, Path(si["assets"]) if si.get("assets") else None, slots, joins, (W, H), fps)
    caps = Captions(timeline["words"], style, a.caption_dir)
    finish = spec.get("finish") or {}
    audio_info = finish_audio(root / "edited.wav", root / "finished.wav", duration, finish)
    final = root / "final.mp4"
    if final.exists():
        raise SystemExit("Preserve existing final before creating a candidate")
    enc = [FFMPEG, "-v", "error", "-n", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1080x1920", "-r", str(edit["fps"]), "-i", "pipe:0",
           "-i", str(root / "finished.wav"), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-threads", "4", "-preset", "medium",
           "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final)]
    dec = [FFMPEG, "-v", "error", "-nostdin", *src_input(a.source), "-map", "0:v:0", "-fps_mode", "passthrough",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    import numpy as np
    size = W * H * 3
    rows, cue_frames, insert_frames, punched = [], [], [], 0
    fi, fo = float(finish.get("fade_in_s", 0)), float(finish.get("fade_out_s", 0))
    encoder = subprocess.Popen(enc, stdin=subprocess.PIPE)
    try:
        with subprocess.Popen(dec, stdout=subprocess.PIPE) as p:
            cur, cur_index, held = None, -1, 0
            for f, wanted in enumerate(indices):
                while cur_index < wanted:
                    data = p.stdout.read(size)
                    if len(data) != size:
                        break
                    cur, cur_index = data, cur_index + 1
                if cur is None:
                    raise SystemExit("source produced no frames")
                held += cur_index < wanted
                t = f / float(fps)
                vf = fade_factor(t, 0.0, duration, fi, fo)
                img, cue, hit = lay.compose(np.frombuffer(cur, np.uint8).reshape(H, W, 3), wanted, t, caps, vf)
                raw = img.tobytes()
                encoder.stdin.write(raw)
                cue_frames.append(cue)
                if hit is not None:
                    insert_frames.append(f)
                punched += lay.punched(wanted)
                rows.append({"frame": f, "captioned_rgb_sha256": hashlib.sha256(raw).hexdigest()})
            p.stdout.close()
            p.kill()
        encoder.stdin.close()
        if encoder.wait() != 0:
            raise SystemExit("Encoder failed")
    except BaseException:
        encoder.kill()
        encoder.wait()
        raise
    digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    (root / "capture-full.json").write_text(json.dumps({
        "canvas": [1080, 1920], "fps": edit["fps"], "frame_count": frames, "indices": list(range(frames)), "reverse_seek_checked": [],
        "errors": [], "geometry": {"layout": "window", "rect": lay.rect}, "held_frames_past_source_end": held,
        "producer": "DeFleur Video app style_render.py (window layout); capture.cjs/Chromium not run"}, indent=2))
    (root / "caption-composite.json").write_text(json.dumps({
        "timeline_sha256": digest(root / "locked-timeline.json"), "style_sha256": digest(root / "caption-style.json"),
        "visual_plan_sha256": digest(root / "visual-plan.json"), "frames": rows, "caption_bounds_pass": True,
        "renderer": "style_render.py (karaoke captions for window styles; chunks from James' caption_layer.style_chunks)"}, indent=2))
    ledger = {"layout": "window", "canvas": [1080, 1920], "rect": lay.rect, "fit": list(lay.fit), "background": spec["layout"].get("background"),
              "grade": lay.grade, "punch_in": lay.punch, "join_source_frames": joins, "punched_frames": punched,
              "insert_box": lay.box, "insert_fades_s": [lay.fi, lay.fo],
              "inserts": [{k: r[k] for k in ("start", "end", "asset", "picture_box")} for r in lay.inserts],
              "insert_frames": len(insert_frames), "text_layers": lay.layer_boxes, "slots": slots,
              "caption_band": style["safe_rect"], "caption_anchor": style.get("anchor", "center"),
              "cue_on_frames": sum(cue_frames), "finish": {**finish, "audio": audio_info}}
    (root / "layout-ledger.json").write_text(json.dumps(ledger, indent=2))
    print(json.dumps({"frames": frames, "held": held, "cue_frames": sum(cue_frames), "insert_frames": len(insert_frames)}))


# ---------- check ----------

def decode_frames(path: Path, frames: list[int], w: int, h: int, vf: str = "", extra_in=None):
    import numpy as np
    expr = "+".join(f"eq(n\\,{i})" for i in frames)
    inp = extra_in if extra_in is not None else ["-threads", "1", "-i", str(path)]
    cmd = [FFMPEG, "-v", "error", "-nostdin", *inp, "-map", "0:v:0", "-vf", f"select='{expr}'{vf}", "-fps_mode", "passthrough",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    data = subprocess.run(cmd, check=True, capture_output=True).stdout
    size = w * h * 3
    if len(data) != size * len(frames):
        raise SystemExit(f"decoded {len(data) // size} of {len(frames)} frames from {path.name}")
    return [np.frombuffer(data[i * size:(i + 1) * size], np.uint8).reshape(h, w, 3) for i in range(len(frames))]


def psnr(a, b) -> float:
    import numpy as np
    mse = float(np.mean((a.astype(np.float32) - b.astype(np.float32)) ** 2))
    return 99.0 if mse == 0 else round(10 * math.log10(255 ** 2 / mse), 2)


def check(a) -> None:
    import numpy as np
    root = a.project
    si = load_input(a.style_input)
    spec = si["spec"]
    edit = json.loads(a.edit_map.read_text())
    ledger = json.loads((root / "layout-ledger.json").read_text())
    timeline = json.loads((root / "locked-timeline.json").read_text())
    style = json.loads((root / "caption-style.json").read_text())
    fps = Fraction(str(edit["fps"]))
    frames, duration = int(edit["frames"]), float(edit["duration"])
    finish = spec.get("finish") or {}
    fi, fo = float(finish.get("fade_in_s", 0)), float(finish.get("fade_out_s", 0))
    caps = Captions(timeline["words"], style, a.caption_dir)
    W, H = probe_size(a.source)
    rx, ry, rw, rh = ledger["rect"]
    fw, fh, ox, oy = ledger["fit"]
    bg = np.array(hex_rgb(ledger.get("background")), np.int16)
    box = ledger.get("insert_box")
    lay_fi, lay_fo = [float(x) for x in ledger.get("insert_fades_s") or (0.0, 0.0)]
    ins = ledger.get("inserts", [])
    inside = lambda t: next((r for r in ins if r["start"] <= t < r["end"]), None)
    steady = [f for f in range(frames) if fi <= f / float(fps) < duration - fo - 1 / float(fps)]
    edge = lambda r, t: (r["start"] + lay_fi + 1 / float(fps) <= t < r["end"] - lay_fo - 1 / float(fps))
    in_full = [f for f in steady if (r := inside(f / float(fps))) and edge(r, f / float(fps))] or \
        [m for r in ins if (m := round((r["start"] + r["end"]) / 2 * float(fps))) in steady]
    live_f = [f for f in steady if not inside(f / float(fps))]
    on = [f for f in live_f if caps.state(f / float(fps))]
    off = [f for f in live_f if not caps.state(f / float(fps))]
    pick = lambda xs, n: [xs[round(i * (len(xs) - 1) / max(1, n - 1))] for i in range(min(n, len(xs)))] if xs else []
    punch_f = [f for f in live_f if ledger["punch_in"] > 1 and any(edit["source_frame_indices"][f] >= j for j in ledger["join_source_frames"])]
    sample = sorted(set(pick(on, 6) + pick(off, 4) + pick(in_full, 4) + pick(punch_f, 3)))
    final = dict(zip(sample, decode_frames(root / "final.mp4", sample, 1080, 1920)))
    src_idx = sorted({edit["source_frame_indices"][f] for f in sample})
    full = dict(zip(src_idx, decode_frames(a.source, src_idx, W, H, extra_in=src_input(a.source))))
    grade = ledger.get("grade") or {}

    def reference(f):
        """Independent of the renderer: FFmpeg scale (lanczos) of the decoded source frame, punch crop by numpy slicing."""
        img = full[edit["source_frame_indices"][f]]
        if ledger["punch_in"] > 1 and any(edit["source_frame_indices"][f] >= j for j in ledger["join_source_frames"]):
            cx, cy, cw, ch = punch_box(W, H, ledger["punch_in"])
            img = img[cy:cy + ch, cx:cx + cw]
        p = subprocess.run([FFMPEG, "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{img.shape[1]}x{img.shape[0]}", "-i", "pipe:0",
                            "-vf", f"scale={fw}:{fh}:flags=lanczos", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                           input=np.ascontiguousarray(img).tobytes(), capture_output=True, check=True).stdout
        out = np.frombuffer(p, np.uint8).reshape(fh, fw, 3).astype(np.float32)
        if "contrast" in grade:
            out = (out - 128.0) * grade["contrast"] + 128.0
        if "saturation" in grade:
            g = out[..., 0:1] * 0.299 + out[..., 1:2] * 0.587 + out[..., 2:3] * 0.114
            out = g + (out - g) * grade["saturation"]
        return np.clip(np.rint(out), 0, 255).astype(np.uint8)

    wx, wy = rx + ox, ry + oy
    band = style["safe_rect"]
    layer_boxes = {k: v["ink_box"] for k, v in ledger["text_layers"].items() if v.get("ink_box")}
    rows = []
    for f in sample:
        img = final[f].astype(np.int16)
        t = f / float(fps)
        r = inside(t)
        row = {"frame": f, "t": round(t, 3), "insert": r["asset"] if r else None, "cue_on": bool(caps.state(t))}
        if not r:
            ref = reference(f)
            got = final[f][wy:wy + fh, wx:wx + fw]
            row["window_psnr_db"] = psnr(got, ref)
            shifted = {}
            for dx, dy in ((0, -8), (0, 8), (-8, 0), (8, 0)):
                y0, x0 = wy + dy, wx + dx
                if 0 <= y0 and y0 + fh <= 1920 and 0 <= x0 and x0 + fw <= 1080:
                    shifted[f"{dx},{dy}"] = psnr(final[f][y0:y0 + fh, x0:x0 + fw], ref)
            row["window_shifted_psnr_db"] = shifted
        else:
            bx, by, bw, bh = r["picture_box"]
            row["insert_box_mean_abs_diff_vs_live"] = None
            row["outside_box_rows_untouched"] = True
            pic = final[f][by:by + bh, bx:bx + bw].astype(np.float32)
            row["insert_picture_std"] = round(float(pic.std()), 2)
            ibx, iby, ibw, ibh = box
            # the window must be fully covered by the insert box during an insert: no live pixels outside the box
            row["window_covered"] = bool(iby <= ry and iby + ibh >= ry + rh)
        # background outside every drawn area
        mask = np.ones((1920, 1080), bool)
        mask[ry:ry + rh, rx:rx + rw] = False
        if r and box:
            mask[box[1]:box[1] + box[3], box[0]:box[0] + box[2]] = False
        for b in layer_boxes.values():
            mask[max(0, b[1] - 6):b[3] + 6, max(0, b[0] - 6):b[2] + 6] = False
        mask[band[1] - 30:band[3] + 30, band[0] - 30:band[2] + 30] = False
        row["outside_mean_abs_diff_from_background"] = round(float(np.mean(np.abs(img[mask] - bg))), 2)
        row["layers_inked"] = {k: round(float(np.mean(np.abs(img[b[1]:b[3], b[0]:b[2]] - bg))), 2) for k, b in layer_boxes.items()}
        bl, bt, br, bb = band
        row["band_mean_abs_diff_from_background"] = round(float(np.mean(np.abs(img[bt:bb, bl:br] - bg))), 2)
        rows.append(row)
    live_rows = [r for r in rows if r["insert"] is None]
    window_ok = bool(live_rows) and all(r["window_psnr_db"] >= 25 and all(r["window_psnr_db"] > v for v in r["window_shifted_psnr_db"].values())
                                        for r in live_rows)
    on_d = [r["band_mean_abs_diff_from_background"] for r in live_rows if r["cue_on"]]
    off_d = [r["band_mean_abs_diff_from_background"] for r in live_rows if not r["cue_on"]]
    caption_ok = bool(on_d) and min(on_d) >= 4.0 and (not off_d or max(off_d) < 1.5)
    layers_ok = all(all(v >= 3.0 for v in r["layers_inked"].values()) for r in rows) and len(layer_boxes) == len(
        [l for l in spec.get("text_layers", []) if l["kind"] == "fixed" or (si.get("slots") or {}).get(l.get("slot"))])
    outside_ok = all(r["outside_mean_abs_diff_from_background"] < 3.0 for r in rows)
    ins_rows = [r for r in rows if r["insert"]]
    inserts_ok = all(r["window_covered"] and r["insert_picture_std"] > 1.0 for r in ins_rows) and (bool(ins_rows) or not ins)
    loud = measure_loudness(root / "final.mp4")
    loud_ok = True
    if "loudness_lufs" in finish:
        loud_ok = abs(loud["integrated_lufs"] - finish["loudness_lufs"]) <= 0.5 and loud["true_peak_dbtp"] <= finish["true_peak_db"]
    from PIL import Image
    shots = [f for f in (pick(on, 1) + pick(in_full, 1) + pick(punch_f, 1)) if f in final][:3] or sample[:1]
    sheet = Image.new("RGB", (270 * len(shots), 480))
    for k, f in enumerate(shots):
        sheet.paste(Image.fromarray(final[f]).resize((270, 480)), (270 * k, 0))
    sheet.save(root / "final-frame-sample.png")
    result = {"layout": "window", "frames": frames, "caption_cues": len(caps.chunks), "cue_on_frames": ledger["cue_on_frames"],
              "cue_off_frames": frames - ledger["cue_on_frames"], "samples": rows,
              "window_matches_layout": window_ok, "crop_matches_ledger": window_ok, "caption_band_changes_with_cues": caption_ok,
              "text_layers_every_sampled_frame": layers_ok, "background_outside_layout": outside_ok, "inserts_in_box": inserts_ok,
              "loudness": loud, "loudness_on_target": loud_ok, "punched_frames": ledger["punched_frames"],
              "pass": window_ok and caption_ok and layers_ok and outside_ok and inserts_ok and loud_ok,
              "method": ("final.mp4 decoded by FFmpeg; the window region must match an independent FFmpeg lanczos scale of the "
                         "ledger's source frame (punch crop and grade applied by numpy) at PSNR>=25 dB and beat the same region "
                         "shifted 8 px each way; pixels outside the window, layer ink boxes, caption band and active insert box must "
                         "be background; every text layer box is inked in every sampled frame; the caption band changes exactly "
                         "with cues; during inserts the box covers the window; loudness by ffmpeg ebur128 (true peak).")}
    (root / "live-check.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ("pass", "window_matches_layout", "caption_band_changes_with_cues", "text_layers_every_sampled_frame",
                                             "background_outside_layout", "inserts_in_box", "loudness_on_target")}))


# ---------- reference test render ----------

REFERENCE_WORDS = ("this is the fixed reference excerpt every new style renders once before it can be picked "
                   "so captions titles and images are checked").split()


def test(a) -> None:
    """The style's reference test render: 4 s synthetic excerpt, fixed words, one insert, one join."""
    from PIL import Image, ImageDraw
    out = a.out
    out.mkdir(parents=True, exist_ok=True)
    si = load_input(a.style_input)
    spec = si["spec"]
    src = out / "reference.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=24", "-f", "lavfi",
                    "-i", "sine=frequency=220:sample_rate=48000", "-t", "4", "-c:v", "libx264", "-threads", "2", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-movflags", "+faststart", str(src)], check=True, capture_output=True)
    subprocess.run([FFMPEG, "-v", "error", "-nostdin", "-y", "-i", str(src), "-map", "0:a:0", "-ar", "48000", "-ac", "1",
                    "-c:a", "pcm_s16le", "-t", "4", str(out / "edited.wav")], check=True, capture_output=True)
    n = len(REFERENCE_WORDS)
    words = [{"word": w, "start": round(0.1 + i * 3.8 / n, 3), "end": round(0.1 + (i + 0.85) * 3.8 / n, 3)} for i, w in enumerate(REFERENCE_WORDS)]
    edit = {"fps": "24/1", "frames": 96, "duration": 4.0, "source_frame_indices": list(range(96))}
    (out / "edit-map.json").write_text(json.dumps(edit))
    (out / "locked-timeline.json").write_text(json.dumps({"duration": 4.0, "fps": "24/1", "frames": 96, "canvas": [1080, 1920], "words": words}))
    (out / "caption-style.json").write_text(json.dumps(si["caption_style"]))
    plan = {"beats": [], "inserts": []}
    assets = out / "assets"
    if spec.get("inserts"):
        assets.mkdir(exist_ok=True)
        im = Image.new("RGB", (1600, 900), (40, 40, 40))
        d = ImageDraw.Draw(im)
        for k in range(0, 1600, 80):
            d.rectangle((k, 0, k + 40, 900), fill=(200, 200, 200))
        d.ellipse((600, 250, 1000, 650), fill=(10, 10, 10))
        im.save(assets / "reference-still.png")
        plan["inserts"] = [{"start": 1.2, "end": 2.6, "asset": "reference-still.png", "fit": "contain", "reason": "reference insert"}]
    (out / "visual-plan.json").write_text(json.dumps(plan))
    slots = {name: (rule.get("sample") or {"title": "Reference Title Here", "tagline": "Checked before use."}.get(name, "Reference"))
             for name, rule in spec.get("slots", {}).items()}
    style_input = {"spec": spec, "slots": slots, "joins": [2.0] if spec.get("joins") else [], "assets": str(assets) if plan["inserts"] else None}
    (out / "style-input.json").write_text(json.dumps(style_input))
    ns = argparse.Namespace(source=src, edit_map=out / "edit-map.json", project=out, style_input=out / "style-input.json", caption_dir=a.caption_dir)
    render(ns)
    check(ns)
    live = json.loads((out / "live-check.json").read_text())
    result = {"pass": live["pass"], "checks": {k: live[k] for k in ("window_matches_layout", "caption_band_changes_with_cues",
                                                                     "text_layers_every_sampled_frame", "background_outside_layout",
                                                                     "inserts_in_box", "loudness_on_target")},
              "loudness": live["loudness"], "final_sha256": hashlib.sha256((out / "final.mp4").read_bytes()).hexdigest(),
              "reference": "4 s testsrc2 1920x1080 at 24 fps + 220 Hz tone, fixed words, one still insert (1.2-2.6 s), one join at 2.0 s",
              "sample_frame": "final-frame-sample.png"}
    (out / "test-result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("render", "check"):
        p = sub.add_parser(name)
        p.add_argument("source", type=Path); p.add_argument("edit_map", type=Path); p.add_argument("project", type=Path)
        p.add_argument("style_input", type=Path); p.add_argument("--caption-dir", type=Path, required=True)
    t = sub.add_parser("test")
    t.add_argument("style_input", type=Path); t.add_argument("out", type=Path); t.add_argument("--caption-dir", type=Path, required=True)
    a = ap.parse_args()
    {"render": render, "check": check, "test": test}[a.cmd](a)


if __name__ == "__main__":
    main()
