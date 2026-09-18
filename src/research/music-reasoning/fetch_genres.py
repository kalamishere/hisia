"""Ground-truth genre for the real chart previews.

Same source as the pipeline's step3 (iTunes Search, keyless, Apple taxonomy),
minus the marathon DB read - the DB isn't up in this session. One query per
track, 0.7s apart, cached so a rerun costs nothing.
"""
import json, sys, time, urllib.parse, urllib.request
from pathlib import Path

R = Path(__file__).parent
meta = json.load(open(R / "real_meta.json"))
out_path = R / "real_genres.json"
out = json.load(open(out_path)) if out_path.exists() else {}

def itunes(artist, title):
    for term in (f"{artist} {title}", title):
        q = urllib.parse.urlencode({"term": term, "media": "music",
                                    "entity": "song", "limit": 5})
        try:
            with urllib.request.urlopen("https://itunes.apple.com/search?" + q, timeout=15) as r:
                d = json.load(r)
        except Exception as e:
            print("  err", e, flush=True); time.sleep(3); continue
        for res in d.get("results", []):
            if res.get("primaryGenreName"):
                return {"label": res["primaryGenreName"], "source": "itunes",
                        "matched_artist": res.get("artistName"),
                        "matched_title": res.get("trackName"), "query": term}
        time.sleep(0.7)
    return None

# The same recording charts in several regions and several weeks. Look it up
# once by deezer_id and reuse the label - 881 chart slots are ~400 recordings.
by_id = {}
for t in meta:
    g = out.get(t["key"])
    if g and t.get("deezer_id"):
        by_id[t["deezer_id"]] = g

for i, t in enumerate(meta):
    if t["key"] in out:
        continue
    if t.get("deezer_id") in by_id:
        out[t["key"]] = by_id[t["deezer_id"]]
        continue
    g = itunes(t["artist"], t["title"])
    out[t["key"]] = g
    if g and t.get("deezer_id"):
        by_id[t["deezer_id"]] = g
    if i % 20 == 0:
        json.dump(out, open(out_path, "w"), indent=1)
        print(i, t["key"], g and g["label"], flush=True)
    time.sleep(0.7)
json.dump(out, open(out_path, "w"), indent=1)
hit = sum(1 for v in out.values() if v)
print(f"done {len(out)} tracks, {hit} labelled")
