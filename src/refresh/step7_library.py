"""Step 7 - write build_<week>/library.json + library.private.json and validate.

radio/build_public/step7_library_public.py, with the region blocks rebuilt from
THIS week's readout/genre/prompts (the hand-run version carried them over from
the previous library, which is exactly what a weekly refresh must not do), and
the same validation: ids unique, mp3 present, duration > 100 s, LUFS within
1.5 of -14, seed_source synthetic, no seed_mode, and no real chart artist or
title text inside a fictional name.

Runs on audio-brief's venv (soundfile not needed; stdlib only).
"""
from __future__ import annotations

import argparse, json, re, sys, unicodedata
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (CHUNKS, CITY, ENERGY_SUFFIX, NOISE, TRACKS_PER_REGION,  # noqa: E402
                    VOCAL_SUFFIX, build_dirs)


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", required=True)
    a = ap.parse_args()
    D = build_dirs(a.week)

    readout = json.loads((D["root"] / "regional_readout.json").read_text())
    genres = json.loads((D["root"] / "genre_labels.json").read_text())
    prompts = json.loads((D["root"] / "prompts.json").read_text())
    names = json.loads((D["root"] / "names.json").read_text())
    stitch = {r["id"]: r for r in json.loads((D["logs"] / "stitch.json").read_text())}
    gens = json.loads((D["logs"] / "gens.json").read_text())
    man = json.loads((D["fixtures"] / "manifest.json").read_text())
    regions = [r for r in CITY if r in readout]

    lib = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "chart_week": a.week,
           "recipe": "two-stage synthetic (E1+E3): text-only stage one from the "
                     "region readout, then four a2a chunks from that gen at 0.42. "
                     "No recording is ever an input.",
           "regions": {}, "tracks": []}
    private = {"note": "Synthetic set: no real seed titles exist. Stage-one seeds "
                       "and prompts per track.",
               "chart_week": a.week, "tracks": {}}

    skipped = []
    for r in regions:
        ro = readout[r]
        city, country, tz = CITY[r]
        lib["regions"][r] = {
            "city": city, "country": country, "tz": tz,
            "readout": {"bpm": ro["bpm_median"], "mode": ro["dominant_mode"],
                        "lufs": ro["lufs_i_median"],
                        "instruments": list(ro["mean_instrument_vector"])[:3],
                        "moods": list(ro["mean_mood_vector"])[:3],
                        "n_tracks": ro["n_tracks"],
                        "excluded_tracks": ro["excluded_tracks"],
                        "bpm_iqr": ro["bpm_iqr"]},
            "genre_family": prompts[r].get(
                "genre_family",
                genres[r]["genre_family_summary"].split(": ", 1)[1].replace("/", " / ")),
            "sa3_prompt": prompts[r]["sa3_prompt"],
            "suno_prompt": prompts[r]["suno_prompt"],
        }
        base = prompts[r]["sa3_prompt"]
        cities_of = ro.get("cities_of", {})
        # "after #k": the city's own hits come first, the world hits fill in after
        ranks = sorted(range(1, 6), key=lambda n: (cities_of.get(f"{r}-{n}", 1) > 1, n))
        for k in range(1, TRACKS_PER_REGION + 1):
            tid = f"{r}-0{k}"
            after = ranks[k - 1] if k - 1 < len(ranks) else k
            n_cities = cities_of.get(f"{r}-{after}", 1)
            st = stitch.get(tid)
            if not st or st.get("status") != "ok":
                skipped.append(tid); print(f"SKIP {tid}: no stitched audio"); continue
            g = [x for x in gens if x["track"] == tid and x["status"] == "ok"]
            chunk_rows = sorted([x for x in g if x["stage"].startswith("c")],
                                key=lambda y: y["stage"])
            s1 = [x for x in g if x["stage"] == "stage1"]
            lib["tracks"].append({
                "id": tid, "region": r, "file": f"audio/{tid}.mp3",
                "duration_s": st["duration_s"], "title": names[tid]["title"],
                "artist": names[tid]["artist"], "mirrors_rank": after,
                "mirrors_cities": n_cities, "seed_source": "synthetic", "vibe": NOISE, "chunks": st["chunks"],
                "seeds": [x["seed"] for x in chunk_rows],
                "stage1_seed": s1[0]["seed"] if s1 else None, "lufs": st["lufs"]})
            private["tracks"][tid] = {
                "fictional_artist": names[tid]["artist"],
                "fictional_title": names[tid]["title"], "region": r, "mirrors_rank": after,
                "stage1_seed": s1[0]["seed"] if s1 else None,
                "stage1_prompt": base + VOCAL_SUFFIX + ENERGY_SUFFIX,
                "chunk_prompt": base + ENERGY_SUFFIX,
                "chunk_seeds": [x["seed"] for x in chunk_rows],
                "init_noise_level": NOISE}

    (D["root"] / "library.json").write_text(json.dumps(lib, indent=2, ensure_ascii=False))
    (D["root"] / "library.private.json").write_text(
        json.dumps(private, indent=2, ensure_ascii=False))

    # ---- validation ----
    errs = []
    ids = [t["id"] for t in lib["tracks"]]
    if len(ids) != len(set(ids)):
        errs.append("duplicate track ids")
    if len(ids) != len(regions) * TRACKS_PER_REGION:
        errs.append(f"tracks={len(ids)} != {len(regions) * TRACKS_PER_REGION}")
    for t in lib["tracks"]:
        if not (D["audio"] / f"{t['id']}.mp3").exists():
            errs.append(f"{t['id']}: missing mp3")
        if t["duration_s"] <= 100:
            errs.append(f"{t['id']}: duration {t['duration_s']}s <= 100")
        if t["lufs"] is None or abs(t["lufs"] + 14) > 1.5:
            errs.append(f"{t['id']}: lufs {t['lufs']} off target")
        if t["seed_source"] != "synthetic":
            errs.append(f"{t['id']}: seed_source {t['seed_source']}")
        if "seed_mode" in t:
            errs.append(f"{t['id']}: seed_mode present")
        if t["chunks"] != CHUNKS:
            errs.append(f"{t['id']}: {t['chunks']} chunks")

    real_tokens, real_strings = set(), []
    for r in regions:
        for t in man.get(r, []):
            for field in (t["artist"], t["title"]):
                real_strings.append(norm(field))
                for part in re.split(r"[,&()]| feat | ft ", field):
                    p = norm(part).strip()
                    if len(p) > 3:
                        real_tokens.add(p)
    for tid, n in names.items():
        for field in (n["artist"], n["title"]):
            f = norm(field).strip()
            for rs in real_strings:
                rs = " ".join(rs.split())
                if len(rs) > 3 and re.search(rf"\b{re.escape(rs)}\b", f):
                    errs.append(f"{tid}: '{field}' contains real string '{rs}'")
            for tok in real_tokens:
                if re.search(rf"\b{re.escape(tok)}\b", f):
                    errs.append(f"{tid}: '{field}' contains real name token '{tok}'")

    ls = [t["lufs"] for t in lib["tracks"] if t["lufs"] is not None]
    print(json.dumps({"week": a.week, "regions": len(lib["regions"]),
                      "tracks": len(lib["tracks"]), "skipped": skipped,
                      "lufs_min": min(ls) if ls else None,
                      "lufs_max": max(ls) if ls else None, "errors": errs}, indent=2))
    print("VALIDATION", "FAILED" if errs else "PASSED")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
