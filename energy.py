#!/usr/bin/env python3
"""App-original helper (not part of James DeFleur's plugin).

Write a 10 ms RMS energy envelope (dBFS per frame) of a PCM s16 WAV. The app uses it
to check that a proposed or applied cut is actually near-silent: ASR can skip whole
sentences, and a gap in the transcript is not proof of silence.
"""
from __future__ import annotations

import argparse
import json
import wave
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--frame", type=float, default=0.01)
    args = parser.parse_args()
    import numpy as np
    with wave.open(str(args.wav), "rb") as reader:
        if reader.getsampwidth() != 2:
            raise SystemExit("WAV must be PCM s16")
        rate, channels, total = reader.getframerate(), reader.getnchannels(), reader.getnframes()
        hop = max(1, round(rate * args.frame))
        db: list[float] = []
        voice: list[float] = []
        tail: list[float] = []
        freqs = np.fft.rfftfreq(hop, 1 / rate)
        band = (freqs >= 300) & (freqs <= 3400)  # voice band: room rumble, hum and handling noise sit below it
        hp = (freqs >= 300) & (freqs <= 8000)    # tail band: sibilant word tails, without the rumble
        window = np.hanning(hop)  # Hann: without it, loud rumble/hum leaks across the spectrum into the voice band
        wnorm = hop * float(np.sum(window ** 2))
        carry = np.zeros(0, np.float64)

        def frames_db(frames):
            power = np.mean(frames ** 2, axis=1)
            db.extend(np.where(power > 0, 10 * np.log10(np.maximum(power, 1e-30)), -120.0).round(1).tolist())
            spec = np.abs(np.fft.rfft(frames * window, axis=1)) ** 2
            vp = 2 * spec[:, band].sum(axis=1) / wnorm  # mean-square power of the in-band component (window-normalized)
            voice.extend(np.where(vp > 0, 10 * np.log10(np.maximum(vp, 1e-30)), -120.0).round(1).tolist())
            tp = 2 * spec[:, hp].sum(axis=1) / wnorm
            tail.extend(np.where(tp > 0, 10 * np.log10(np.maximum(tp, 1e-30)), -120.0).round(1).tolist())

        while True:
            raw = reader.readframes(rate * 30)  # stream 30 s at a time: bounded memory for long sources
            if not raw:
                break
            x = np.frombuffer(raw, np.int16).reshape(-1, channels).astype(np.float64).mean(axis=1) / 32768.0
            x = np.concatenate([carry, x])
            n = len(x) // hop
            frames_db(x[: n * hop].reshape(n, hop))
            carry = x[n * hop:]
        if len(carry):
            frames_db(np.pad(carry, (0, hop - len(carry))).reshape(1, hop))
    out = {"frame_s": hop / rate, "sample_rate": rate, "samples": total, "dbfs": [max(-120.0, v) for v in db],
           "voice_dbfs": [max(-120.0, v) for v in voice], "voice_band_hz": [300, 3400],
           "tail_dbfs": [max(-120.0, v) for v in tail], "tail_band_hz": [300, 8000],
           "basis": "RMS dBFS per frame of the 48 kHz PCM source (mono mix), broadband, 300-3400 Hz voice band and "
                    "300-8000 Hz tail band; "
                    "evidence for silence checks, not a VAD model."}
    args.out.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"frames": len(db), "frame_s": out["frame_s"]}))


if __name__ == "__main__":
    main()
