"""Step 1 - this week's charts for the 14 regions, resolved to Deezer previews.

Same route as the first fourteen (radio/build/step0_previews.py): YouTube
`top-songs` from marathon's signals table (GH via the location route), parsed
with marathon.youtube.parse_chart / parse_location_chart, resolved with
marathon.embed_signals.resolve_audio.

Reads the DB READ-ONLY. When the requested week is not in the DB it shells out
to marathon's own CLI (`marathon.cli harvest-youtube` / `harvest-locations`) so
that the only writer of signals rows is marathon itself. --dry-run never
harvests and never writes to the DB.

Writes fixtures/regional-previews-<week>/ (NEW dir per week; the old one is
never touched) with a manifest.json carrying the same fields as today's, plus
`week`. Misses are recorded as resolved:false - never substituted.

Runs on marathon's venv (psycopg).
"""
from __future__ import annotations

import argparse, json, re, subprocess, sys, unicodedata, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/Users/kalam/ableton-v1-wt-continuous/marathon")

import psycopg  # noqa: E402
from config import (CHART_SLUG, DSN, LOCATION_REGIONS, LOCATION_SLUG, MARATHON,  # noqa: E402
                    PY_MARATHON, REGIONS, TOP_N, week_paths)
from marathon.youtube import parse_chart, parse_location_chart  # noqa: E402
from marathon.embed_signals import resolve_audio, NoAudio  # noqa: E402


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def sim(a, b):
    A, B = set(norm(a).split()), set(norm(b).split())
    return round(len(A & B) / len(A | B), 3) if A | B else 0.0


def slug(s, n=40):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", norm(s))).strip("-")[:n].strip("-")


def _weeks_in_db(conn, regions):
    rows = conn.execute(
        "select raw->'meta'->>'week' w, region from signals"
        " where source='youtube' and raw->'meta'->>'chart' in (%s,%s)"
        " and region = any(%s) and raw->'meta'->>'week' is not null",
        (CHART_SLUG, LOCATION_SLUG, list(regions))).fetchall()
    weeks = {}
    for w, r in rows:
        weeks.setdefault(w, set()).add(r)
    return weeks


def resolve_week(conn, regions, want: str) -> tuple[str, dict]:
    weeks = _weeks_in_db(conn, regions)
    if not weeks:
        sys.exit("no youtube chart weeks in the DB for these regions")
    if want == "latest":
        week = max(weeks)
    else:
        week = want
    return week, {w: sorted(weeks.get(w, ())) for w in sorted(weeks, reverse=True)[:4]}


def chart_rows(conn, region, week):
    slug_ = LOCATION_SLUG if region in LOCATION_REGIONS else CHART_SLUG
    row = conn.execute(
        "select raw->'payload' from signals where source='youtube' and region=%s"
        " and raw->'meta'->>'week'=%s and raw->'meta'->>'chart'=%s"
        " order by id desc limit 1", (region, week, slug_)).fetchone()
    if not row:
        return None, slug_
    payload = row[0]
    if region in LOCATION_REGIONS:
        entries, _identity = parse_location_chart(payload)
    else:
        entries = parse_chart(payload)
    entries = sorted([e for e in entries if e.get("rank")], key=lambda e: e["rank"])
    return entries[:TOP_N], slug_


def run_marathon_harvest(regions, dry_run: bool):
    """marathon's own CLI does the writing - we never INSERT signals ourselves."""
    country = [r for r in regions if r not in LOCATION_REGIONS]
    cmds = []
    if country:
        cmds.append([str(PY_MARATHON), "-m", "marathon.cli", "harvest-youtube",
                     "--regions", ",".join(country), "--charts", CHART_SLUG])
    if any(r in LOCATION_REGIONS for r in regions):
        cmds.append([str(PY_MARATHON), "-m", "marathon.cli", "harvest-locations"])
    for cmd in cmds:
        print("HARVEST (marathon CLI, writes signals):", " ".join(cmd), flush=True)
        if dry_run:
            print("  dry-run: not executed", flush=True)
            continue
        subprocess.run(cmd, cwd=str(MARATHON), check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", default="latest")
    ap.add_argument("--regions", default=",".join(REGIONS))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-harvest", action="store_true")
    a = ap.parse_args()
    regions = [r.strip().upper() for r in a.regions.split(",") if r.strip()]

    with psycopg.connect(DSN) as conn:
        conn.read_only = True
        week, seen = resolve_week(conn, regions, a.week)
        have = set(seen.get(week, ()))
        missing = [r for r in regions if r not in have]
        print(f"weeks in DB (newest first): "
              f"{ {w: len(v) for w, v in seen.items()} }", flush=True)
        print(f"week = {week}; regions with rows: {len(have)}/{len(regions)}"
              f"{'; missing ' + ','.join(missing) if missing else ''}", flush=True)

    if missing and not a.skip_harvest:
        run_marathon_harvest(missing, a.dry_run)

    with psycopg.connect(DSN) as conn:
        conn.read_only = True
        if a.week == "latest" and not a.dry_run and not a.skip_harvest:
            week, _ = resolve_week(conn, regions, "latest")
            print(f"week after harvest = {week}", flush=True)

        FIX = week_paths(week)["fixtures"]
        FIX.mkdir(parents=True, exist_ok=True)
        mpath = FIX / "manifest.json"
        man = json.loads(mpath.read_text()) if mpath.exists() else {}

        if a.skip_harvest and all(r in man for r in regions):
            print(f"--skip-harvest: reusing {mpath} "
                  f"({sum(len(man[r]) for r in regions)} entries, "
                  f"{sum(1 for r in regions for t in man[r] if t.get('resolved'))} resolved)")
            print("WEEK", week)
            return

        report = {}
        for region in regions:
            entries, slug_ = chart_rows(conn, region, week)
            if entries is None:
                print(f"{region}: NO CHART ROW for {week}/{slug_}", flush=True)
                report[region] = {"n": 0, "resolved": 0, "error": "no chart row"}
                continue
            out = []
            for e in entries:
                artist, title, rank = e["artist_name"], e["track_name"], e["rank"]
                rec = {"rank": rank, "artist": artist, "title": title,
                       "youtube_id": (e["meta"] or {}).get("video_id"),
                       "week": week, "chart": slug_}
                if (e["meta"] or {}).get("rank_is_list_position"):
                    rec["rank_is_list_position"] = True
                try:
                    url, prov = resolve_audio(artist, title, {})
                except NoAudio as ex:
                    rec.update({"deezer_id": None, "preview_path": None,
                                "resolved": False, "route": None,
                                "error": str(ex), "match_confidence": 0.0})
                    print(f"{region}-{rank} MISS  {artist} - {title}", flush=True)
                    out.append(rec)
                    continue
                ma, mt = prov.get("matched_artist"), prov.get("matched_title")
                conf = {"deezer_search": 0.9, "deezer_search_loose": 0.75,
                        "deezer_search_relaxed": 0.6}.get(prov["route"], 0.5)
                name = f"{rank}-{slug(artist, 24)}-{slug(title, 24)}.mp3"
                dst = FIX / region / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with urllib.request.urlopen(url, timeout=60) as r:
                        data = r.read()
                except Exception as ex:   # a preview URL that 404s is a miss,
                    rec.update({"deezer_id": prov.get("deezer_id"),          # not a substitution
                                "preview_path": None, "resolved": False,
                                "route": prov["route"], "error": f"download: {ex}",
                                "match_confidence": conf})
                    print(f"{region}-{rank} DOWNLOAD MISS {ex}", flush=True)
                    out.append(rec)
                    continue
                dst.write_bytes(data)
                rec.update({"deezer_id": prov.get("deezer_id"),
                            "preview_path": f"{region}/{name}",
                            "match_confidence": conf, "resolved": True,
                            "route": prov["route"], "matched_artist": ma,
                            "matched_title": mt, "artist_sim": sim(artist, ma),
                            "title_sim": sim(title, mt), "bytes": len(data)})
                print(f"{region}-{rank} {prov['route']:22s} "
                      f"a={rec['artist_sim']} t={rec['title_sim']} | "
                      f"{artist} - {title}  ->  {ma} - {mt}", flush=True)
                out.append(rec)
            man[region] = out
            report[region] = {"n": len(out),
                              "resolved": sum(1 for x in out if x["resolved"])}

    mpath.write_text(json.dumps(man, indent=2, ensure_ascii=False))
    (FIX / "harvest_report.json").write_text(
        json.dumps({"week": week, "regions": report}, indent=2))
    print(json.dumps({"week": week, "fixtures": str(FIX), "regions": report}, indent=2))
    print("WEEK", week)


if __name__ == "__main__":
    main()
