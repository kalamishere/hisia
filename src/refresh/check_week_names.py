"""Run radio/check_names.py over this week's names.json before any GPU is spent.

check_names.py reads a library shape, so the names are wrapped in a stub
library first. It now takes the manifest path as argv[2] (the only change made
to an existing script) so it checks against THIS week's chart, not last week's.
"""
from __future__ import annotations

import argparse, json, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import RADIO, build_dirs  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--week", required=True)
a = ap.parse_args()
D = build_dirs(a.week)
names = json.loads((D["root"] / "names.json").read_text())
stub = D["root"] / "names_check.json"
stub.write_text(json.dumps({"tracks": [{"id": k, "artist": v["artist"], "title": v["title"]}
                                       for k, v in names.items()]}))
sys.exit(subprocess.run([sys.executable, str(RADIO / "check_names.py"), str(stub),
                         str(D["fixtures"] / "manifest.json")]).returncode)
