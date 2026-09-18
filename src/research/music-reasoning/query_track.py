"""Describe an arbitrary track by what it is near.

  python query_track.py /path/to/track.mp3

Reads: the CLAP vectors built by run_embed (emb/lib, emb/real), library.json
(prompt + region + readout per hisia track), real_meta.json + real_genres.json
(region + Apple genre per chart preview).

Writes a JSON blob and prints a description. Measurement first, prose second:
every phrase in the description is traceable to a number printed above it.
"""
import argparse, json, re, subprocess, sys, tempfile
from collections import Counter
from pathlib import Path
import numpy as np

R = Path(__file__).resolve().parent
SITE = R.parents[2]
AUDIO_BRIEF = Path("/Users/kalam/ableton-v1/audio-brief")
CKPT = Path.home() / (".cache/huggingface/hub/models--lukewys--laion_clap/snapshots/"
                      "b3708341862f581175dba5c356a4ebf74a9b6651/"
                      "music_audioset_epoch_15_esc_90.14.pt")

sys.path.insert(0, str(R))
from families import lib_family, real_family  # noqa: E402


def embed(path: Path) -> np.ndarray:
    out = Path(tempfile.mkdtemp()) / "q.npy"
    env = {"LAION_CLAP_MUSIC_CKPT": str(CKPT), "PATH": "/usr/bin:/bin"}
    subprocess.run([str(AUDIO_BRIEF / ".venv/bin/python"), str(AUDIO_BRIEF / "clap_worker.py"),
                    str(path), str(out)], check=True, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    v = np.load(out).astype(np.float32)
    return v / np.linalg.norm(v)


def analyse(path: Path) -> dict:
    """bpm / key / loudness with librosa, in audio-brief's venv."""
    code = r'''
import json, sys, numpy as np, librosa
y, sr = librosa.load(sys.argv[1], sr=22050, mono=True)
tempo = float(np.atleast_1d(librosa.beat.beat_track(y=y, sr=sr, start_bpm=100)[0])[0])
chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
PITCH = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
maj = np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88])
mnr = np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])
def best(prof):
    return max(((np.corrcoef(np.roll(prof, i), chroma)[0,1], i) for i in range(12)))
(cm, im), (cn, iN) = best(maj), best(mnr)
mode, root = ("major", im) if cm >= cn else ("minor", iN)
rms = float(20*np.log10(np.sqrt(np.mean(y**2)) + 1e-9))
cent = float(librosa.feature.spectral_centroid(y=y, sr=sr).mean())
print(json.dumps({"bpm": round(tempo,1), "key": PITCH[root], "mode": mode,
                  "rms_db": round(rms,1), "centroid_hz": round(cent),
                  "duration_s": round(len(y)/sr,1)}))
'''
    p = subprocess.run([str(AUDIO_BRIEF / ".venv/bin/python"), "-c", code, str(path)],
                       capture_output=True, text=True)
    if p.returncode != 0:
        return {"error": p.stderr.strip()[-300:]}
    return json.loads(p.stdout)


def load(sub, ids):
    keep, M = [], []
    for i in ids:
        f = R / "emb" / sub / f"{i}.npy"
        if f.exists():
            v = np.load(f).astype(np.float32)
            M.append(v / np.linalg.norm(v)); keep.append(i)
    return keep, np.stack(M)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("track")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--describe", action="store_true",
                    help="one readable block instead of the raw JSON")
    ap.add_argument("--json", default=None)
    ap.add_argument("--keep-self", action="store_true",
                    help="keep neighbours that are the query recording itself "
                         "(the chart set may already contain it)")
    a = ap.parse_args()
    path = Path(a.track)

    lib = {t["id"]: t for t in json.load(open(SITE / "library.json"))["tracks"]}
    meta = {m["key"]: m for m in json.load(open(R / "real_meta.json"))}
    gen = json.load(open(R / "real_genres.json"))

    q = embed(path)
    feats = analyse(path)

    lib_ids, L = load("lib", list(lib))
    real_ids, Q = load("real", list(meta))


    sl = q @ L.T
    sr_ = q @ Q.T
    if not a.keep_self:
        # The query can be in the chart set already (YoYo charted in UG). A
        # track retrieving itself makes any genre vote look perfect, so drop a
        # neighbour whose artist or title shows up in the filename, and any
        # near-identical vector.
        stem = re.sub(r"[^a-z0-9]+", " ", path.stem.lower())
        for j, key in enumerate(real_ids):
            m = meta[key]
            nm = re.sub(r"[^a-z0-9]+", " ", f'{m["artist"]} {m["title"]}'.lower()).split()
            hit = sum(1 for w in nm if len(w) > 3 and w in stem)
            if sr_[j] > 0.93 or (hit and hit >= max(1, len([w for w in nm if len(w) > 3]) // 2)):
                sr_[j] = -2
    # the charts repeat: one recording holds several slots (weeks x cities).
    # Keep its best slot, or the list is the same record three times.
    seen = set()
    orr = []
    for j in np.argsort(-sr_):
        if sr_[j] < -1:
            continue
        m = meta[real_ids[j]]
        fp = str(m.get("deezer_id") or f'{m["artist"]}|{m["title"]}'.lower())
        if fp in seen:
            continue
        seen.add(fp); orr.append(j)
        if len(orr) >= a.k:
            break
    ol = np.argsort(-sl)[:a.k]

    lib_hits = [{"id": lib_ids[j], "cos": round(float(sl[j]), 3),
                 "region": lib[lib_ids[j]]["region"],
                 "family": lib_family(lib[lib_ids[j]]["sa3_prompt"]),
                 "prompt": lib[lib_ids[j]]["sa3_prompt"]} for j in ol]
    real_hits = [{"key": real_ids[j], "cos": round(float(sr_[j]), 3),
                  "region": meta[real_ids[j]]["region"],
                  "artist": meta[real_ids[j]]["artist"],
                  "title": meta[real_ids[j]]["title"],
                  "genre": (gen.get(real_ids[j]) or {}).get("label"),
                  "family": real_family((gen.get(real_ids[j]) or {}).get("label"))}
                 for j in orr]

    def vote(hits, key):
        c = Counter()
        for h in hits:
            if h.get(key):
                c[h[key]] += h["cos"]
        if not c:
            return None, 0.0
        top = c.most_common(2)
        margin = top[0][1] / sum(c.values())
        return top[0][0], round(margin, 2)

    out = {"track": str(path), "features": feats,
           "library_neighbours": lib_hits, "real_neighbours": real_hits,
           "vote_family_library": vote(lib_hits, "family"),
           "vote_family_real": vote(real_hits, "family"),
           "vote_region_real": vote(real_hits, "region"),
           "vote_region_library": vote(lib_hits, "region")}

    if a.describe:
        print(describe(out))
    else:
        print(json.dumps(out, indent=1, ensure_ascii=False))
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1, ensure_ascii=False)




# --- the sentence -----------------------------------------------------------
# Measured per-family reliability of the family call, from metrics.py (route 2,
# kNN over real previews, k=8, duplicates masked). Printed with the answer so
# the description can't overclaim: "afro" is worth four times "hiphop".
FAMILY_RECALL = {"afro": 0.74, "latin": 0.56, "pop": 0.48, "east-asian-pop": 0.39,
                 "reggae": 0.33, "hiphop": 0.18, "arabic": 0.0, "dance": 0.0,
                 "country": 0.0, "rock": 0.0, "indian": 0.0, "rnb": 0.0}
STOP = {"instrumental", "chart", "bpm", "key", "major", "minor", "with", "and",
        "the", "a", "an", "of", "crossover", "sway"}


def describe(out: dict) -> str:
    f = out["features"]
    rn, ln = out["real_neighbours"], out["library_neighbours"]
    fam, fam_w = out["vote_family_real"]
    reg, reg_w = out["vote_region_real"]
    near = "; ".join(f'{h["artist"]} — {h["title"]} ({h["region"]}, {h["cos"]})'
                     for h in rn[:3])
    regions = "/".join(dict.fromkeys(h["region"] for h in rn))
    # whole clauses, not bag-of-words: the prompts name instruments and grooves
    # in phrases ("live log-drum and shaker percussion"), and the words alone
    # come out as "warm, forward, prominent".
    NAMES = re.compile(r"drum|bass|guitar|perc|synth|pad|horn|string|flute|oud|"
                       r"piano|key|vocal|chant|clap|shaker|groove|swing|riff|"
                       r"beat|log|kick|808|accordion|marimba|kora|sabar|riddim")
    clauses = []
    for h in ln[:3]:
        for c in h["prompt"].split(","):
            c = c.strip()
            if NAMES.search(c.lower()) and c.lower() not in [x.lower() for x in clauses]:
                clauses.append(c)
    vocab = "; ".join(clauses[:5])
    rel = FAMILY_RECALL.get(fam)
    top_cos = rn[0]["cos"] if rn else 0.0
    lines = [
        f'{f.get("bpm")} BPM, {f.get("key")} {f.get("mode")}, '
        f'{f.get("rms_db")} dB RMS, {f.get("duration_s")}s',
        f'Nearest charting records: {near}',
        f'Family: {fam} ({fam_w:.0%} of the neighbour weight'
        + (f'; that call is right {rel:.0%} of the time on this corpus)' if rel is not None else ')'),
        f'Chart neighbourhood: {regions} — top vote {reg} ({reg_w:.0%}). '
        f'City top-1 runs at 15% over 60 cities (chance 1.7%), so read this as a '
        f'neighbourhood, not a country.',
        f'Sounds named in the nearest generated prompts: {vocab}',
    ]
    if top_cos < 0.65:
        lines.insert(0, f'LOW CONFIDENCE: closest chart record sits at {top_cos:.2f} '
                        f'(a typical chart pair is 0.57, a close one 0.76). Nothing in '
                        f'the corpus is near this track; read the rest as weak.')
    return "\n".join(lines)

if __name__ == "__main__":
    main()
