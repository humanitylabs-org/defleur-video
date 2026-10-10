#!/usr/bin/env python3
"""Caption overlay adapter for a locked DeFleur timeline.

The default style is James DeFleur's house Shorts captions (defaults/james-preset.json): a heavy sans in ALL CAPS, white
words, the spoken word turns green and grows slightly only while it is actually spoken, at most one yellow key term per
chunk, a black stroke plus a short shadow, and no plates, pills or boxes. Chunks are short phrases that break at sentence
ends, real pauses and long words.

Optional style keys (the neutral preset omits them): uppercase, active_scale, shadow_px, emphasis_color,
break_on_punctuation, min_scale. Key terms come from visual-plan.json `caption_emphasis` (a list of edited-timeline
seconds, or {"t": seconds}) or locked-timeline.json `emphasis_times`.
"""
from __future__ import annotations

import argparse
import bisect
import json
from pathlib import Path
from typing import Any, Callable

SENTENCE_END = (".", "?", "!", ":", ";")
LONG_WORD = 9          # a word at least this long ends its chunk (CONTROVERSIAL, INFORMATION ... never fused with tail words)
PHRASE_PAUSE_S = 0.35  # a real pause between words starts a new chunk


def _color(value: str) -> tuple[int, int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6 or any(char not in "0123456789abcdefABCDEF" for char in value):
        raise ValueError("caption colors must be #RRGGBB")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), 255)


def _chunks(words: list[dict], maximum_words: int, maximum_chars: int, break_on_punctuation: bool = False) -> list[list[int]]:
    result, current, length = [], [], 0

    def flush():
        nonlocal current, length
        if current:
            result.append(current)
        current, length = [], 0

    for index, word in enumerate(words):
        token = str(word.get("word", "")).strip()
        next_length = length + len(token) + (1 if current else 0)
        if current and (len(current) >= maximum_words or next_length > maximum_chars):
            flush()
        if current and break_on_punctuation and float(word["start"]) - float(words[current[-1]]["end"]) >= PHRASE_PAUSE_S:
            flush()
        current.append(index)
        length += len(token) + (1 if len(current) > 1 else 0)
        if break_on_punctuation and (token.endswith(SENTENCE_END) or (token.endswith(",") and len(current) >= 2)
                                     or len(token.strip(".,?!:;\"'")) >= LONG_WORD):
            flush()
    flush()
    if break_on_punctuation:
        # No orphans: a lone word closing a phrase borrows the last word of a 3+ word chunk before it
        # ("THE FIRST LEVEL IS | MONEY" -> "THE FIRST LEVEL | IS MONEY") when the two chunks are one phrase.
        for k in range(1, len(result)):
            prev, cur = result[k - 1], result[k]
            prev_tail = str(words[prev[-1]].get("word", "")).strip()
            if (len(cur) == 1 and len(prev) >= 3 and not prev_tail.endswith(SENTENCE_END + (",",))
                    and float(words[cur[0]]["start"]) - float(words[prev[-1]]["end"]) < PHRASE_PAUSE_S):
                result[k] = [prev.pop()] + cur
    return result


def style_chunks(words: list[dict], style: dict) -> list[list[int]]:
    """The exact chunking caption_engine uses for this style (for cue counts in checks)."""
    style = style.get("caption", style)
    return _chunks(words, int(style["max_words"]), int(style["max_chars"]), bool(style.get("break_on_punctuation", False)))


def _display(token: str, uppercase: bool) -> str:
    token = token.strip()
    return token.upper().rstrip(".,;:") if uppercase else token


def caption_engine(project: Path, style_path: Path | None = None) -> Callable:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("Install Pillow on the media worker.") from exc
    timeline = json.loads((project / "locked-timeline.json").read_text(encoding="utf-8"))
    style_file = style_path or project / "caption-style.json"
    style = json.loads(style_file.read_text(encoding="utf-8"))
    style = style.get("caption", style)
    words = timeline.get("words")
    if not isinstance(words, list) or not words:
        raise ValueError("locked timeline needs words")
    required = ("font_path", "font_size_px", "max_words", "max_chars", "text_color", "active_color", "outline_color", "outline_width_px", "safe_rect")
    if any(key not in style for key in required):
        raise ValueError("caption style is incomplete")
    font_file = Path(str(style["font_path"])).expanduser()
    if not font_file.is_file():
        raise ValueError("caption style font_path must name an existing worker/project font")
    base_size = int(style["font_size_px"])
    active_scale = float(style.get("active_scale", 1.0))
    min_scale = float(style.get("min_scale", 1.0))
    if not 1.0 <= active_scale <= 1.3 or not 0.5 <= min_scale <= 1.0:
        raise ValueError("caption active_scale must be 1.0-1.3 and min_scale 0.5-1.0")
    uppercase = bool(style.get("uppercase", False))
    shadow = int(style.get("shadow_px", 0))
    emphasis = _color(str(style["emphasis_color"])) if style.get("emphasis_color") else None
    colors = _color(str(style["text_color"])), _color(str(style["active_color"])), _color(str(style["outline_color"]))
    outline = int(style["outline_width_px"])
    left, top, right, bottom = [int(value) for value in style["safe_rect"]]
    if left >= right or top >= bottom or outline < 0 or shadow < 0:
        raise ValueError("invalid caption safe rectangle")
    fonts: dict[int, Any] = {}

    def font_at(size: int):
        if size not in fonts:
            fonts[size] = ImageFont.truetype(str(font_file), size)
        return fonts[size]

    chunks = style_chunks(words, style)
    starts = [float(word["start"]) for word in words]
    if starts != sorted(starts) or any(float(w['end']) <= float(w['start']) for w in words):
        raise ValueError('Caption word timings must be ordered and positive')
    plan_file = project / 'visual-plan.json'
    plan = json.loads(plan_file.read_text()) if plan_file.exists() else {}
    suppress = timeline.get('caption_suppressions', timeline.get('caption_suppress', plan.get('caption_suppressions', plan.get('caption_suppress', []))))
    # Key terms: at most ONE yellow word per chunk (the first declared wins).
    key_words: set[int] = set()
    if emphasis is not None:
        marks = plan.get('caption_emphasis', timeline.get('emphasis_times', []))
        for mark in marks if isinstance(marks, list) else []:
            t = float(mark['t'] if isinstance(mark, dict) else mark)
            hit = next((i for i, w in enumerate(words) if float(w['start']) <= t < float(w['end'])), None)
            if hit is None:  # nearest word within 50 ms
                near = min(range(len(words)), key=lambda i: min(abs(t - float(words[i]['start'])), abs(t - float(words[i]['end']))))
                gap = min(abs(t - float(words[near]['start'])), abs(t - float(words[near]['end'])))
                hit = near if gap <= 0.05 else None
            if hit is None:
                continue
            chunk = next(c for c in chunks if hit in c)
            if not any(i in key_words for i in chunk):
                key_words.add(hit)

    def layout(painter, selected, size):
        """Lines for one chunk at a font size, or None when it does not fit the safe rectangle."""
        font, big = font_at(size), font_at(max(size, round(size * active_scale)))
        margin = outline + 2 + shadow
        available = right - left - 2 * margin
        spacing = painter.textlength(' ', font=font)
        lines, line, width = [], [], 0
        for index in selected:
            token = _display(str(words[index].get('word', '')), uppercase)
            if not token:
                continue
            # Each word owns a slot as wide as its enlarged (active) form, so the growing word never touches a neighbour.
            size_px = painter.textlength(token, font=big)
            if size_px > available:
                return None
            if line and width + spacing + size_px > available:
                lines.append((line, width)); line = []; width = 0
            width += (spacing if line else 0) + size_px
            line.append((index, token, size_px))
        if line:
            lines.append((line, width))
        line_height = sum(font.getmetrics()) + outline * 2
        if active_scale > 1:
            line_height = round(line_height * (1 + (active_scale - 1) / 2))
        if len(lines) * line_height > bottom - top - 2 * margin:
            return None
        return lines, line_height, spacing, font, big

    def draw(image, time_s: float):
        if any(float(row["start"]) <= time_s < float(row["end"]) for row in suppress):
            return image
        if time_s < starts[0] or time_s >= float(words[-1]['end']):
            return image
        active = bisect.bisect_right(starts, time_s) - 1
        selected = next((chunk for chunk in chunks if active in chunk), None)
        if not selected or time_s >= float(words[selected[-1]]['end']):
            return image
        canvas = image.convert('RGBA')
        spoken = active if float(words[active]['start']) <= time_s < float(words[active]['end']) else None
        # Fit the chunk at the configured size, then step down to min_scale. The measured ink box (glyphs, stroke,
        # shadow, the larger active word) must sit inside the safe rectangle; fail rather than draw outside it.
        size = base_size
        while size >= round(base_size * min_scale):
            overlay = Image.new('RGBA', canvas.size)
            painter = ImageDraw.Draw(overlay)
            fitted = layout(painter, selected, size)
            if fitted is not None:
                paint(painter, fitted, spoken)
                box = overlay.getbbox()
                if not box or (box[0] >= left and box[1] >= top and box[2] <= right and box[3] <= bottom):
                    return Image.alpha_composite(canvas, overlay).convert(image.mode)
            size -= 2
        raise ValueError('Rendered caption exceeds safe bounds; revise chunk/font before encoding')

    def paint(painter, fitted, spoken):
        lines, line_height, spacing, font, big = fitted
        shadow_fill = (0, 0, 0, 170)
        y = top + (bottom - top - len(lines) * line_height) / 2
        for line, width in lines:
            # Slots are fixed for the whole chunk (no reflow while words light up); each word is centred in its slot.
            x = left + (right - left - width) / 2
            cy = y + line_height / 2
            for index, token, size_px in line:
                is_active = index == spoken
                f = big if is_active else font
                fill = colors[1] if is_active else (emphasis if index in key_words else colors[0])
                cx = x + size_px / 2
                if shadow:
                    painter.text((cx + shadow, cy + shadow), token, font=f, anchor='mm', fill=shadow_fill,
                                 stroke_width=outline, stroke_fill=shadow_fill)
                painter.text((cx, cy), token, font=f, anchor='mm', fill=fill, stroke_width=outline, stroke_fill=colors[2])
                x += size_px + spacing
            y += line_height

    return draw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("input_image", type=Path)
    parser.add_argument("output_image", type=Path)
    parser.add_argument("--time", required=True, type=float)
    parser.add_argument("--style", type=Path)
    args = parser.parse_args()
    from PIL import Image
    rendered = caption_engine(args.project, args.style)(Image.open(args.input_image), args.time)
    args.output_image.parent.mkdir(parents=True, exist_ok=True)
    rendered.save(args.output_image)


if __name__ == "__main__":
    main()
