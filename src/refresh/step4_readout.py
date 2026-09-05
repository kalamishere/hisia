"""Step 4 - aggregate the per-region readout, then write prompts and names.

The aggregation is radio/build/step4_readout.py verbatim in maths (raw-median
octave fold, numpy IQR, mode majority, median LUFS-I/LRA, mean tag vectors,
md5 dupes and unresolved previews excluded); only the region list and the paths
are parameterised. Prompt and name writing live in refresh/prompts.py and
refresh/names.py - read the module docstrings there: the region idiom is
carried from the signed-off 2026-08-24 set, the numbers are this week's.

Runs on audio-brief's venv (numpy).
"""
from __future__ import annotations

import argparse, json, statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import names as names_mod  # noqa: E402
import prompts as prompts_mod  # noqa: E402
from config import RADIO, REGIONS, TRACKS_PER_REGION, build_dirs  # noqa: E402


def octave_fold_to(bpm, median):
    return min([bpm, bpm * 2, bpm / 2], key=lambda c: abs(c - median))


def mean_vec(vecs):
    keys = set()
    for v in vecs:
        keys |= set(v)
    out = {k: round(sum(v.get(k, 0.0) for v in vecs) / len(vecs), 4) for k in keys}
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", required=True)
    ap.add_argument("--regions", default=",".join(REGIONS))
    ap.add_argument("--prompts", choices=("auto", "keep"), default="auto",
                    help="auto: rebuild the measured half of each prompt from "
                         "this week's readout; keep: reuse the live library's "
                         "prompt text verbatim")
    a = ap.parse_args()
    regions = [r.strip().upper() for r in a.regions.split(",") if r.strip()]
    D = build_dirs(a.week)

    man = json.loads((D["fixtures"] / "manifest.json").read_text())
    dupes = json.loads((D["root"] / "dupes.json").read_text())
    dup_ids = {t for ids in dupes.values() if len(ids) > 1 for t in ids}
    # how many cities a chart entry appears in this week (1 = only here)
    cities_of = {t: len(ids) for ids in dupes.values() for t in ids}
    unresolved = {f"{r}-{t['rank']}" for r, ts in man.items() for t in ts
                  if not t.get("preview_path")}
    genres = json.loads((D["root"] / "genre_labels.json").read_text())

    # a --regions subset run updates the week's files, it never truncates them
    rpath = D["root"] / "regional_readout.json"
    out = json.loads(rpath.read_text()) if rpath.exists() else {}
    for region in regions:
        included, excluded, shared = [], [], []
        for t in man.get(region, []):
            tid = f"{region}-{t['rank']}"
            if tid in unresolved:
                excluded.append(tid)
                continue
            p = D["analysis"] / f"{tid}.json"
            if not p.exists():
                print("MISSING analysis", tid)
                excluded.append(tid)
                continue
            d = json.loads(p.read_text())
            row = {"id": tid, "bpm": d["bpm"], "key": d.get("key"),
                   "key_mode": d["key_mode"], "lufs_i": d["lufs_i"],
                   "lufs_lra": d["lufs_lra"],
                   "tags_instrument": d.get("tags_instrument", []),
                   "tags_mood": d.get("tags_mood", [])}
            (shared if tid in dup_ids else included).append(row)
        # the readout is built from the city's own hits; a chart that is entirely
        # the world chart (Sydney, Auckland) falls back to all of it, flagged
        shared_chart = False
        if len(included) < 2 and shared:
            included = included + shared
            shared_chart = True
        else:
            excluded += [t["id"] for t in shared]
        if not included:
            print(f"{region}: NO usable tracks this week - region dropped")
            out.pop(region, None)
            continue
        bpm_raw = [t["bpm"] for t in included]
        med_raw = statistics.median(bpm_raw)
        bpm_folded = [octave_fold_to(b, med_raw) for b in bpm_raw]
        q1, q3 = np.percentile(bpm_folded, [25, 75])
        modes = [t["key_mode"] for t in included]
        mc = {"major": modes.count("major"), "minor": modes.count("minor")}
        out[region] = {
            "n_tracks": len(included), "excluded_tracks": excluded,
            "shared_chart": shared_chart,
            "cities_of": {f"{region}-{t['rank']}": cities_of.get(f"{region}-{t['rank']}", 1)
                          for t in man.get(region, [])},
            "track_ids": [t["id"] for t in included], "bpm_raw": bpm_raw,
            "bpm_folded": [round(b, 2) for b in bpm_folded],
            "bpm_median": round(statistics.median(bpm_folded), 2),
            "bpm_iqr": [round(q1, 2), round(q3, 2)],
            "keys": [t["key"] for t in included], "mode_counts": mc,
            "dominant_mode": "major" if mc["major"] > mc["minor"] else "minor",
            "lufs_i_median": round(statistics.median([t["lufs_i"] for t in included]), 2),
            "lufs_lra_median": round(statistics.median([t["lufs_lra"] for t in included]), 2),
            "mean_instrument_vector": mean_vec(
                [{x["label"]: x["score"] for x in t["tags_instrument"]} for t in included]),
            "mean_mood_vector": mean_vec(
                [{x["label"]: x["score"] for x in t["tags_mood"]} for t in included]),
        }
    (D["root"] / "regional_readout.json").write_text(json.dumps(out, indent=2))

    # ---- prompts ----
    live = json.loads((RADIO / "library.json").read_text())
    P = {}
    for r in out:
        fam = genres[r]["genre_family_summary"].split(": ", 1)[1].replace("/", " / ")
        built = prompts_mod.build(r, out[r], fam)
        if a.prompts == "keep" and r in live["regions"]:
            P[r] = {"sa3_prompt": live["regions"][r]["sa3_prompt"],
                    "suno_prompt": live["regions"][r]["suno_prompt"],
                    "_measured": built["_measured"], "_source": "kept_from_live_library"}
        else:
            P[r] = built | {"_source": "rebuilt_from_readout"}
        P[r]["genre_family"] = fam
    (D["root"] / "prompts.json").write_text(json.dumps(P, indent=2, ensure_ascii=False))

    # ---- names ----
    N = names_mod.build(a.week, list(out), man, TRACKS_PER_REGION)
    (D["root"] / "names.json").write_text(json.dumps(N, indent=2, ensure_ascii=False))

    for r in out:
        v = out[r]
        prev = live["regions"].get(r, {}).get("readout", {})
        print(f"{r} n={v['n_tracks']} excl={v['excluded_tracks']} "
              f"bpm={v['bpm_median']} (was {prev.get('bpm')}) "
              f"mode={v['dominant_mode']} (was {prev.get('mode')}) "
              f"lufs={v['lufs_i_median']} inst={list(v['mean_instrument_vector'])[:3]} "
              f"mood={list(v['mean_mood_vector'])[:3]}")
    print(f"prompts: {len(P)} regions ({a.prompts}); names: {len(N)}")


if __name__ == "__main__":
    main()
