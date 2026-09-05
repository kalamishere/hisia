"""Step 6 - stitch each track's 4 chunks into one ~1:52 piece.

radio/build_public/step6_stitch_public.py verbatim (tail trim ported from
sa3-livestream cb54451, 2.0 s equal-power crossfade, two-pass ffmpeg loudnorm
I=-14/TP=-1, wav kept, mp3 at 192 kbps); only the paths are week-stamped and
the constants come from refresh/config.py.

Runs on audio-brief's venv (soundfile, numpy) + ffmpeg.
"""
from __future__ import annotations

import argparse, json, re, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from config import BODY_S, LOUDNORM_I, LOUDNORM_TP, MP3_KBPS, XFADE, build_dirs  # noqa: E402


def trim_tail(x, sr, threshold=0.01, window_ms=20, fade_ms=5, min_keep_s=1.0):
    n = len(x)
    w = max(1, int(sr * window_ms / 1000))
    fade = max(1, int(sr * fade_ms / 1000))
    keep = int(sr * min_keep_s)
    mono = x.mean(axis=1) if x.ndim > 1 else x
    end = n
    last = n
    while end >= max(w, keep):
        start = max(0, end - w)
        if np.sqrt(np.mean(mono[start:end] ** 2)) > threshold:
            last = end
            break
        end -= w
    if last >= n - w or last < keep:
        return x, 0.0
    cut = min(n, last + fade)
    y = x[:cut].copy()
    g = np.linspace(1.0, 0.0, min(fade, len(y)))
    y[-len(g):] *= g[:, None] if y.ndim > 1 else g
    return y, (n - cut) / sr * 1000


def stitch(paths):
    parts, trims = [], []
    sr = None
    for p in paths:
        x, s = sf.read(str(p), always_2d=True, dtype="float32")
        sr = s
        y, ms = trim_tail(x, s)
        y = y[: int(BODY_S * s)]   # drop the generated taper: only the first BODY_S seconds go on air
        parts.append(y); trims.append(round(ms, 1))
    xf = int(XFADE * sr)
    out = parts[0]
    for nxt in parts[1:]:
        k = min(xf, len(out), len(nxt))
        t = np.linspace(0, np.pi / 2, k, dtype=np.float32)
        a, b = np.sin(t)[:, None], np.cos(t)[:, None]
        out = np.concatenate([out[:-k], out[-k:] * b + nxt[:k] * a, nxt[k:]], axis=0)
    return out, sr, trims


def loudnorm(src, dst_wav, dst_mp3):
    tgt = f"loudnorm=I={LOUDNORM_I}:TP={LOUDNORM_TP}:LRA=11"
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(src), "-af",
                        tgt + ":print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    st = json.loads(re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S)[-1])
    af = (f"{tgt}:measured_I={st['input_i']}:measured_TP={st['input_tp']}:"
          f"measured_LRA={st['input_lra']}:measured_thresh={st['input_thresh']}:"
          f"offset={st['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af", af,
                    "-ar", "44100", "-ac", "2", "-sample_fmt", "s16", str(dst_wav)],
                   check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(dst_wav), "-codec:a",
                    "libmp3lame", "-b:a", MP3_KBPS, str(dst_mp3)], check=True)
    return st


def measure(path):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
                        "-filter_complex", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    tail = p.stderr[-1500:]
    i = re.search(r"I:\s*(-?[\d.]+)\s*LUFS", tail)
    tp = re.search(r"Peak:\s*(-?[\d.]+)\s*dBFS", tail)
    lra = re.search(r"LRA:\s*(-?[\d.]+)\s*LU", tail)
    return (float(i.group(1)) if i else None, float(tp.group(1)) if tp else None,
            float(lra.group(1)) if lra else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", required=True)
    a = ap.parse_args()
    D = build_dirs(a.week)
    D["wav"].mkdir(parents=True, exist_ok=True)
    D["audio"].mkdir(parents=True, exist_ok=True)

    gens = json.loads((D["logs"] / "gens.json").read_text())
    tracks = sorted({g["track"] for g in gens})
    rows = []
    for tid in tracks:
        have = sorted((D["chunks"] / tid).glob("c*.wav"), key=lambda p: int(p.stem[1:]))
        if len(have) < 4:
            print(f"{tid}: only {len(have)}/4 chunks, stitching what exists", flush=True)
        if not have:
            rows.append({"id": tid, "status": "FAIL_no_chunks"}); continue
        out, sr, trims = stitch(have)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            sf.write(tmp.name, out, sr, subtype="PCM_16")
            st = loudnorm(tmp.name, D["wav"] / f"{tid}.wav", D["audio"] / f"{tid}.mp3")
        lufs, tp, lra = measure(D["audio"] / f"{tid}.mp3")
        info = sf.info(str(D["wav"] / f"{tid}.wav"))
        rows.append({"id": tid, "status": "ok", "chunks": len(have), "trimmed_ms": trims,
                     "duration_s": round(info.duration, 2), "lufs": lufs,
                     "true_peak_db": tp, "lra": lra, "pre_lufs": float(st["input_i"])})
        print(f"{tid} {round(info.duration,1)}s lufs={lufs} tp={tp} trims={trims}", flush=True)

    SJ = D["logs"] / "stitch.json"
    old = {r["id"]: r for r in (json.loads(SJ.read_text()) if SJ.exists() else [])}
    old.update({r["id"]: r for r in rows})
    SJ.write_text(json.dumps(list(old.values()), indent=2))
    ls = [r["lufs"] for r in rows if r.get("lufs") is not None]
    print(f"tracks={len(rows)} lufs range {min(ls):.2f}..{max(ls):.2f}")


if __name__ == "__main__":
    main()
