"""Step 8 - swap this week's set in, only on full success.

  radio/library.json          -> radio/private/prev_<oldweek>/library.json
  radio/library.private.json  -> radio/private/prev_<oldweek>/library.private.json
  radio/audio/                -> radio/private/prev_<oldweek>/audio/
  build_<week>/library.json         -> radio/library.json
  build_<week>/library.private.json -> radio/library.private.json
  audio_<week>/                     -> radio/audio/

Refuses unless every track is seed_source == synthetic, every mp3 exists, and
the new library carries as many regions as it built. Descendant of
radio/build_public/step8_swap.py; the fixed 14/56 counts became "what this
week's build validated" so a region that loses its chart does not wedge the
swap - the counts are printed and a shrink needs --allow-shrink.
"""
from __future__ import annotations

import argparse, json, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import RADIO, build_dirs  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", required=True)
    ap.add_argument("--allow-shrink", action="store_true")
    a = ap.parse_args()
    D = build_dirs(a.week)
    PRIV = RADIO / "private"

    new = json.loads((D["root"] / "library.json").read_text())
    bad = [t["id"] for t in new["tracks"] if t.get("seed_source") != "synthetic"]
    if bad:
        sys.exit(f"REFUSING: non-synthetic tracks {bad[:5]}")
    missing = [t["id"] for t in new["tracks"] if not (D["audio"] / f"{t['id']}.mp3").exists()]
    if missing:
        sys.exit(f"REFUSING: missing audio for {missing}")

    live_path = RADIO / "library.json"
    old_week = None
    if live_path.exists():
        old = json.loads(live_path.read_text())
        old_week = old.get("chart_week", "unknown")
        if (len(new["regions"]) < len(old["regions"])
                or len(new["tracks"]) < len(old["tracks"])) and not a.allow_shrink:
            sys.exit(f"REFUSING: new set is smaller "
                     f"({len(new['regions'])} regions / {len(new['tracks'])} tracks vs "
                     f"{len(old['regions'])} / {len(old['tracks'])}). "
                     f"Pass --allow-shrink if that is intended.")
        if old_week == a.week:
            print(f"note: the live library is already chart_week {old_week}; "
                  f"the previous set will be archived as prev_{old_week}")

    dest = PRIV / f"prev_{old_week or 'none'}"
    dest.mkdir(parents=True, exist_ok=True)
    for f in ("library.json", "library.private.json"):
        if (RADIO / f).exists():
            shutil.move(str(RADIO / f), str(dest / f))
    if (RADIO / "audio").exists():
        if (dest / "audio").exists():
            shutil.rmtree(dest / "audio")
        shutil.move(str(RADIO / "audio"), str(dest / "audio"))

    shutil.copy(D["root"] / "library.json", RADIO / "library.json")
    shutil.copy(D["root"] / "library.private.json", RADIO / "library.private.json")
    shutil.copytree(D["audio"], RADIO / "audio")

    for t in new["tracks"]:
        assert (RADIO / t["file"]).exists(), t["file"]
    print(f"swapped: {len(new['tracks'])} tracks / {len(new['regions'])} regions live; "
          f"previous set archived in {dest}")


if __name__ == "__main__":
    main()
