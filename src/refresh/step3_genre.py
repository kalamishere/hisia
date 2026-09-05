"""Step 3 - genre labels per region.

Copied from radio/build/step2_genre_new.py unchanged in logic: primary is a
read-only SELECT on marathon signals.raw->'genre' keyed by deezer_id, fallback
is the keyless iTunes Search. No writes to the DB. Only the region list and the
paths are parameterised.

Runs on marathon's venv (psycopg).
"""
from __future__ import annotations

import argparse, json, sys, time, urllib.parse, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import psycopg  # noqa: E402
from config import DSN, REGIONS, build_dirs  # noqa: E402


def db_genre(conn, deezer_id):
    with conn.cursor() as cur:
        cur.execute("select raw->'genre' from signals where raw->'audio'->>'deezer_id' = %s"
                    " and raw->'genre' is not null limit 1", (str(deezer_id),))
        row = cur.fetchone()
    return row[0] if row else None


def itunes_genre(artist, title):
    for term in (f"{artist} {title}", title):
        q = urllib.parse.urlencode({"term": term, "media": "music",
                                    "entity": "song", "limit": 5})
        try:
            with urllib.request.urlopen("https://itunes.apple.com/search?" + q,
                                        timeout=15) as r:
                d = json.load(r)
        except Exception as e:
            print("  itunes error", e, flush=True); time.sleep(3); continue
        for res in d.get("results", []):
            if res.get("primaryGenreName"):
                return {"label": res["primaryGenreName"], "source": "itunes",
                        "taxonomy": "apple", "matched_artist": res.get("artistName"),
                        "matched_title": res.get("trackName"), "query": term}
        time.sleep(1)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", required=True)
    ap.add_argument("--regions", default=",".join(REGIONS))
    a = ap.parse_args()
    regions = [r.strip().upper() for r in a.regions.split(",") if r.strip()]
    D = build_dirs(a.week)
    man = json.loads((D["fixtures"] / "manifest.json").read_text())
    dupes = json.loads((D["root"] / "dupes.json").read_text())
    dup_ids = {t for ids in dupes.values() if len(ids) > 1 for t in ids}

    gpath = D["root"] / "genre_labels.json"
    out = json.loads(gpath.read_text()) if gpath.exists() else {}
    with psycopg.connect(DSN) as conn:
        conn.read_only = True
        for r in regions:
            tracks = []
            for t in man.get(r, []):
                tid = f"{r}-{t['rank']}"
                g = None
                if t.get("deezer_id"):
                    g = db_genre(conn, t["deezer_id"])
                    if g:
                        g = dict(g); g["_via"] = "marathon_db"
                if g is None:
                    g = itunes_genre(t["artist"], t["title"])
                    if g:
                        g["_via"] = "itunes_search"
                if g is None:
                    g = {"label": None, "source": "none"}
                tracks.append({"rank": t["rank"], "artist": t["artist"],
                               "title": t["title"], "deezer_id": t.get("deezer_id"),
                               "genre": g, "resolved": t.get("resolved", True),
                               "is_cross_region_duplicate": tid in dup_ids})
                print(f"{tid} {t['title'][:30]!r} -> {g.get('label')} "
                      f"({g.get('source')})", flush=True)
            kept = [x for x in tracks
                    if not x["is_cross_region_duplicate"] and x["resolved"]]
            labels, seen = [], set()
            for x in kept:
                l = x["genre"]["label"]
                if l and l not in seen:
                    seen.add(l); labels.append(l)
            out[r] = {"tracks": tracks, "genre_family_summary": f"{r}: " + "/".join(labels)}

    gpath.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    for r in regions:
        print(out[r]["genre_family_summary"])


if __name__ == "__main__":
    main()
