"""Step 2 - md5 dedupe across all regions, then audio-brief analysis.

Copied from radio/build/step3_analysis.py (librosa bpm/key/loudness + Essentia
tags, no stems, no midi, no CLAP - 8 GB Mac) with three changes, none silent:
  * the region list and the BPM priors come from refresh/config.py, so all 14
    regions run from one table;
  * the dedupe (md5 of the preview bytes, the rule from the experiment's
    measure_v2.py) is computed here rather than read from a hand-made
    dupes.json;
  * paths are week-stamped.

demucs/stems are NOT run: the public recipe never uses a recording as a seed.

Runs on audio-brief's venv.
"""
from __future__ import annotations

import argparse, hashlib, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/Users/kalam/ableton-v1/audio-brief")

from config import PRIORS, REGIONS, build_dirs  # noqa: E402
from pipeline import analyze, to_json  # noqa: E402


def dupes_of(man, fix: Path, regions):
    """md5 appearing in >1 region -> dropped from every region's readout."""
    md5 = {}
    for r in regions:
        for t in man.get(r, []):
            if t.get("preview_path"):
                p = fix / t["preview_path"]
                if p.exists():
                    md5[f"{r}-{t['rank']}"] = hashlib.md5(p.read_bytes()).hexdigest()
    by_hash = {}
    for tid, h in md5.items():
        by_hash.setdefault(h, []).append(tid)
    for h in by_hash:
        by_hash[h].sort()
    return by_hash


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", required=True)
    ap.add_argument("--regions", default=",".join(REGIONS))
    a = ap.parse_args()
    regions = [r.strip().upper() for r in a.regions.split(",") if r.strip()]
    D = build_dirs(a.week)
    FIX = D["fixtures"]
    D["analysis"].mkdir(parents=True, exist_ok=True)
    D["logs"].mkdir(parents=True, exist_ok=True)

    man = json.loads((FIX / "manifest.json").read_text())
    # the dedupe is always computed across EVERY region in the manifest, never
    # only the --regions subset: a track that charts in a region outside the
    # subset still carries no regional information for the one inside it.
    dupes = dupes_of(man, FIX, list(man))
    (D["root"] / "dupes.json").write_text(json.dumps(dupes, indent=2))
    dup_ids = {t for ids in dupes.values() if len(ids) > 1 for t in ids}
    print(f"cross-region duplicates dropped: {sorted(dup_ids)}", flush=True)

    log = []
    for region in regions:
        for t in man.get(region, []):
            tid = f"{region}-{t['rank']}"
            if not t.get("preview_path"):
                print(f"{tid} skipped (preview unresolved)", flush=True)
                log.append({"id": tid, "status": "skipped_unresolved"})
                continue
            out = D["analysis"] / f"{tid}.json"
            if out.exists():
                print(f"{tid} exists", flush=True)
                continue
            if tid in dup_ids:
                # identical bytes elsewhere this week: reuse that analysis rather than
                # measuring the same file twice (the readout may still use it as a fallback)
                sib = next((x for ids in dupes.values() if tid in ids for x in ids
                            if x != tid and (D["analysis"] / f"{x}.json").exists()), None)
                if sib:
                    d = json.loads((D["analysis"] / f"{sib}.json").read_text())
                    d.update({"_region": region, "_rank": t["rank"], "_artist": t["artist"],
                              "_title": t["title"], "_copied_from": sib})
                    out.write_text(json.dumps(d, indent=1))
                    print(f"{tid} analysis copied from {sib} (cross-region duplicate)", flush=True)
                    log.append({"id": tid, "status": "copied_duplicate", "from": sib})
                    continue
            wd = D["analysis"] / "work" / region / f"r{t['rank']}"
            wd.mkdir(parents=True, exist_ok=True)
            t0 = time.perf_counter()
            an = analyze(str(FIX / t["preview_path"]), bpm_prior=PRIORS[region],
                         workdir=str(wd), run_stems=False, run_midi=False,
                         run_tags=True, run_embedding=False)
            dt = round(time.perf_counter() - t0, 1)
            d = json.loads(to_json(an))
            d.update({"_region": region, "_rank": t["rank"], "_artist": t["artist"],
                      "_title": t["title"], "_bpm_prior": PRIORS[region], "_wall_s": dt})
            out.write_text(json.dumps(d, indent=2))
            print(f"{tid} bpm={d.get('bpm')} key={d.get('key')} {d.get('key_mode')} "
                  f"lufs={d.get('lufs_i')} errs={[e['stage'] for e in d.get('errors', [])]} "
                  f"{dt}s", flush=True)
            log.append({"id": tid, "status": "ok", "wall_s": dt,
                        "errors": [e["stage"] for e in d.get("errors", [])]})

    (D["logs"] / "analysis.json").write_text(json.dumps(log, indent=2))
    print("analysis done:", sum(1 for x in log if x["status"] == "ok"), "analysed")


if __name__ == "__main__":
    main()
