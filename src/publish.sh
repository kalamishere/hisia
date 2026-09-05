#!/usr/bin/env bash
# Publish the radio page + library + audio to the hisia site repo (kalamishere/hisia → hisia.live).
# Refuses to publish a library that contains real-recording seeds: the public site runs the two-stage recipe only.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SITE="${HISIA_SITE:-$HOME/hisia-site}"

python3 "$HERE/check_names.py" "$HERE/library.json"
# the page's script must parse — a broken page once shipped with working-looking markup
python3 - "$HERE/index.html" <<'PY'
import re, subprocess, sys, tempfile, os
js = re.findall(r'<script>(.*?)</script>', open(sys.argv[1]).read(), re.S)
for i, body in enumerate(js):
    f = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False); f.write(body); f.close()
    r = subprocess.run(['node', '--check', f.name], capture_output=True, text=True); os.unlink(f.name)
    if r.returncode: print(f"REFUSING: index.html script {i} does not parse:\n{r.stderr[-400:]}"); sys.exit(1)
print(f"page scripts parse ({len(js)})")
PY
if python3 - "$HERE/library.json" <<'EOF'
import json, sys
lib = json.load(open(sys.argv[1]))
bad = [t["id"] for t in lib["tracks"] if t.get("seed_source", "recording") != "synthetic"]
if bad:
    print(f"REFUSING: {len(bad)} tracks seeded from recordings (seed_source != synthetic), e.g. {bad[:5]}")
    sys.exit(1)
EOF
then :; else exit 1; fi

rsync -a "$HERE/index.html" "$HERE/library.json" "$SITE/"
mkdir -p "$SITE/audio" && rsync -a --delete "$HERE/audio/" "$SITE/audio/"
cd "$SITE"
git add -A
git commit -q -m "library $(python3 -c "import json;print(json.load(open('library.json'))['chart_week'])") · $(date +%F)" || echo "nothing to publish"
git push -q
echo "published $(ls audio | wc -l | tr -d ' ') tracks → $(git remote get-url origin)"
