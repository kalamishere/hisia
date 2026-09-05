"""Step 5 - the public recipe, week-stamped.

radio/build_public/step5_gens_public.py with three changes: prompts come from
this week's build dir (falling back to the live library), paths are
week-stamped, and --dry-run prints the plan instead of calling the Space.

Per track k of region r (unchanged - A/B 2 verdict E1+E3, A/B 3 verdict
"parallel at 0.42"):
  stage one : /generate, sa3_prompt + VOCAL_SUFFIX + ENERGY_SUFFIX, seed 100k+11
  chunks    : /generate_a2a from that wav, sa3_prompt + ENERGY_SUFFIX,
              init_noise_level 0.42, seeds 100k+12 .. 100k+15

Runs on audio-brief's venv (gradio_client, soundfile, scipy).
"""
from __future__ import annotations

import argparse, json, shutil, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (API_TOKEN_PATH, CALLS_PER_TRACK, CFG, CHUNKS, ENERGY_SUFFIX,  # noqa: E402
                    GPU_S_PER_CALL, HF_TOKEN_PATH, NOISE, RADIO, REGIONS, SECONDS,
                    SPACE, STEPS, TRACKS_PER_REGION, VARIANT, VOCAL_SUFFIX,
                    build_dirs)


def load_prompts(D, regions):
    p = D["root"] / "prompts.json"
    if p.exists():
        d = json.loads(p.read_text())
        src = str(p)
    else:
        d = {r: v for r, v in json.loads((RADIO / "library.json").read_text())["regions"].items()}
        src = str(RADIO / "library.json") + " (live library - this week's prompts not built)"
    return {r: d[r]["sa3_prompt"] for r in regions if r in d}, src


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", required=True)
    ap.add_argument("--regions", default=",".join(REGIONS))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    regions = [r.strip().upper() for r in a.regions.split(",") if r.strip()]
    D = build_dirs(a.week)
    for k in ("stage1", "chunks", "logs"):
        D[k].mkdir(parents=True, exist_ok=True)

    PROMPT, src = load_prompts(D, regions)
    regions = [r for r in regions if r in PROMPT]
    total = len(regions) * TRACKS_PER_REGION * CALLS_PER_TRACK

    if a.dry_run:
        plan = []
        for r in regions:
            for k in range(1, TRACKS_PER_REGION + 1):
                tid = f"{r}-0{k}"
                plan.append({"track": tid, "stage": "stage1", "seed": 100 * k + 11,
                             "api": "/generate", "seconds": SECONDS, "steps": STEPS,
                             "prompt": PROMPT[r] + VOCAL_SUFFIX + ENERGY_SUFFIX})
                for i in range(CHUNKS):
                    plan.append({"track": tid, "stage": f"c{i+1}", "seed": 100 * k + 12 + i,
                                 "api": "/generate_a2a", "init_noise_level": NOISE,
                                 "seconds": SECONDS, "steps": STEPS,
                                 "prompt": PROMPT[r] + ENERGY_SUFFIX})
        (D["logs"] / "gens_plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False))
        gpu = total * GPU_S_PER_CALL
        print(f"DRY RUN - no Space call made ({SPACE} untouched)")
        print(f"  prompts from : {src}")
        print(f"  regions      : {len(regions)} ({','.join(regions)})")
        print(f"  tracks       : {len(regions) * TRACKS_PER_REGION}"
              f"  ({TRACKS_PER_REGION}/region, {CHUNKS} chunks each)")
        print(f"  Space calls  : {total}  ({len(regions) * TRACKS_PER_REGION} x /generate"
              f" + {len(regions) * TRACKS_PER_REGION * CHUNKS} x /generate_a2a)")
        print(f"  model        : {VARIANT}, {SECONDS}s, {STEPS} steps, cfg {CFG}, "
              f"init_noise {NOISE}")
        print(f"  est GPU      : {gpu:.0f} s = {gpu/60:.1f} GPU-min "
              f"(from the measured 20.5 GPU-min / 56 tracks)")
        print(f"  plan written : {D['logs'] / 'gens_plan.json'}")
        print(f"  example stage-one prompt:\n    {plan[0]['prompt']}")
        return

    from gradio_client import Client, handle_file
    import soundfile as sf

    HF = HF_TOKEN_PATH.read_text().strip()
    API = API_TOKEN_PATH.read_text().strip()
    GENLOG = D["logs"] / "gens.json"
    rows = json.loads(GENLOG.read_text()) if GENLOG.exists() else []
    ok_keys = {(x["track"], x["stage"]) for x in rows if x["status"] == "ok"}

    def save():
        GENLOG.write_text(json.dumps(rows, indent=2, default=str))

    def ensure_pcm16_44100(path: Path) -> Path:
        info = sf.info(str(path))
        if info.samplerate == 44100 and info.subtype == "PCM_16":
            return path
        data, sr = sf.read(str(path))
        fixed = path.with_name(path.stem + "-pcm16.wav")
        if sr != 44100:
            from scipy.signal import resample
            data = resample(data, int(round(data.shape[0] * 44100 / sr)), axis=0)
        sf.write(str(fixed), data, 44100, subtype="PCM_16")
        return fixed

    client = Client(SPACE, token=HF, verbose=False)
    t_start = time.time()
    n = 0

    def call(track, region, stage, seed, dst, fn):
        nonlocal n
        n += 1
        if (track, stage) in ok_keys and dst.exists():
            print(f"[{n}/{total}] {track} {stage} cached", flush=True)
            return dst
        status, wall, err, meta = "FAIL", None, "", None
        for attempt in (1, 2):
            t0 = time.time()
            try:
                wav, meta = fn()
                wall = round(time.time() - t0, 1)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(wav, dst)
                status = "ok"
                break
            except Exception as e:
                wall = round(time.time() - t0, 1)
                err = f"{type(e).__name__}: {e}"[:400]
                print(f"  {track} {stage} attempt {attempt} failed after {wall}s: {err}",
                      flush=True)
                if attempt == 1:
                    time.sleep(20)
        m = meta if isinstance(meta, dict) else {}
        rows.append({"track": track, "region": region, "stage": stage, "seed": seed,
                     "status": status, "wall_s": wall, "gen_wall_s": m.get("gen_wall_s"),
                     "server_seed": m.get("seed"), "error": err})
        save()
        print(f"[{n}/{total}] {track} {stage} seed={seed} {status} {wall}s "
              f"gpu={m.get('gen_wall_s')} elapsed={round(time.time()-t_start)}s", flush=True)
        return dst if status == "ok" else None

    for r in regions:
        base = PROMPT[r]
        p_stage1 = base + VOCAL_SUFFIX + ENERGY_SUFFIX
        p_chunk = base + ENERGY_SUFFIX
        for k in range(1, TRACKS_PER_REGION + 1):
            tid = f"{r}-0{k}"
            s1_seed = 100 * k + 11
            s1 = call(tid, r, "stage1", s1_seed, D["stage1"] / f"{tid}.wav",
                      lambda p=p_stage1, s=s1_seed: client.predict(
                          API, VARIANT, p, "", SECONDS, STEPS, CFG, s, api_name="/generate"))
            if s1 is None:
                print(f"{tid}: stage1 failed twice, skipping its {CHUNKS} chunks", flush=True)
                n += CHUNKS
                continue
            init = ensure_pcm16_44100(s1)
            for i in range(CHUNKS):
                seed = 100 * k + 12 + i
                call(tid, r, f"c{i+1}", seed, D["chunks"] / tid / f"c{i+1}.wav",
                     lambda ip=init, p=p_chunk, s=seed: client.predict(
                         API, VARIANT, handle_file(str(ip)), p, "", NOISE, SECONDS,
                         STEPS, CFG, s, api_name="/generate_a2a"))

    ok = sum(1 for x in rows if x["status"] == "ok")
    gpu = sum(float(x["gen_wall_s"]) for x in rows if x.get("gen_wall_s"))
    print(f"DONE ok={ok}/{total} gpu_s={gpu:.1f} wall_s={round(time.time()-t_start)}")
    if ok < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
