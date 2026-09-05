#!/usr/bin/env bash
# The weekly World Sound refresh, one command.
#
#   radio/refresh.sh --week <YYYY-MM-DD|latest> [--regions KE,AE,...] [--dry-run]
#                    [--skip-harvest] [--prompts auto|keep] [--allow-shrink]
#
# 1 harvest   this week's YouTube top-songs for the 14 regions -> top 5 per region
#             resolved to Deezer previews in a NEW week-stamped fixtures dir
# 2 readouts  md5 dedupe, audio-brief analysis (no demucs: the public recipe has
#             no recording seeds), aggregation, genre labels, prompts, names
# 3 generate  the public two-stage recipe (E1+E3, 4 chunks at 0.42), stitch,
#             library.json (seed_source synthetic, chart_week set), then swap in
# 4 publish   radio/publish.sh, then sync hisia-stream/ and print the deploy
#             reminder - hisia-stream/deploy.sh is Kalam's to run (HF write token)
#
# --dry-run does everything except the Space calls and the publish: it harvests
# read-only (marathon's own CLI is the only writer of signals, and it is not
# invoked under --dry-run), builds this week's readouts and prompts, and prints
# what would be generated with an estimated GPU cost.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REFRESH="$HERE/refresh"
PY_MARATHON="/Users/kalam/ableton-v1-wt-continuous/marathon/.venv/bin/python"
PY_AUDIO="/Users/kalam/ableton-v1/audio-brief/.venv/bin/python"
HISIA="$(cd "$HERE/.." && pwd)/hisia-stream"

WEEK="latest"; REGIONS="KE,AE,TZ,NG,GH,UG,ZA,GB,BR,KR,MX,US,IN,ID"
DRY=0; SKIP_HARVEST=0; PROMPTS="auto"; SHRINK=""
while [ $# -gt 0 ]; do
  case "$1" in
    --week) WEEK="$2"; shift 2;;
    --regions) REGIONS="$2"; shift 2;;
    --prompts) PROMPTS="$2"; shift 2;;
    --dry-run) DRY=1; shift;;
    --skip-harvest) SKIP_HARVEST=1; shift;;
    --allow-shrink) SHRINK="--allow-shrink"; shift;;
    -h|--help) sed -n '2,20p' "$0"; exit 0;;
    *) echo "unknown argument: $1" >&2; exit 2;;
  esac
done
for p in "$PY_MARATHON" "$PY_AUDIO"; do
  [ -x "$p" ] || { echo "missing interpreter $p" >&2; exit 1; }
done
command -v ffmpeg >/dev/null || { echo "ffmpeg not on PATH" >&2; exit 1; }

step() { echo; echo "=== $* ==="; }
LOG="$(mktemp -t wsrefresh)"

# --- 1 harvest -------------------------------------------------------------
step "1/8 harvest  week=$WEEK regions=$REGIONS"
H=( --week "$WEEK" --regions "$REGIONS" )
[ "$DRY" = 1 ] && H+=( --dry-run )
[ "$SKIP_HARVEST" = 1 ] && H+=( --skip-harvest )
"$PY_MARATHON" "$REFRESH/step1_harvest.py" "${H[@]}" | tee "$LOG"
WEEK="$(grep '^WEEK ' "$LOG" | tail -1 | awk '{print $2}')"
[ -n "$WEEK" ] || { echo "harvest did not resolve a week" >&2; exit 1; }
echo "resolved week: $WEEK"
BUILD="$HERE/build_$WEEK"
FIXTURES="/Users/kalam/ableton-v1-wt-continuous/marathon/fixtures/regional-previews-$WEEK"

# --- 2 readouts ------------------------------------------------------------
step "2/8 analysis (no demucs: public recipe has no recording seeds)"
"$PY_AUDIO" "$REFRESH/step2_analysis.py" --week "$WEEK" --regions "$REGIONS"

step "3/8 genre labels (marathon DB by deezer_id, iTunes fallback)"
"$PY_MARATHON" "$REFRESH/step3_genre.py" --week "$WEEK" --regions "$REGIONS"

step "4/8 readouts, prompts ($PROMPTS) and fictional names"
"$PY_AUDIO" "$REFRESH/step4_readout.py" --week "$WEEK" --regions "$REGIONS" \
    --prompts "$PROMPTS"

# names must clear the real-name check against THIS week's manifest before a
# single GPU second is spent
"$PY_AUDIO" "$REFRESH/check_week_names.py" --week "$WEEK"

# --- 3 generate ------------------------------------------------------------
step "5/8 generate (public two-stage recipe)"
G=( --week "$WEEK" --regions "$REGIONS" )
[ "$DRY" = 1 ] && G+=( --dry-run )
"$PY_AUDIO" "$REFRESH/step5_gens.py" "${G[@]}"

if [ "$DRY" = 1 ]; then
  echo
  echo "=== dry run complete ==="
  echo "  fixtures : $FIXTURES"
  echo "  build    : $BUILD"
  echo "  not run  : Space generation, stitch, library swap, publish"
  exit 0
fi

step "6/8 stitch"
"$PY_AUDIO" "$REFRESH/step6_stitch.py" --week "$WEEK"

step "7/8 library + validation"
"$PY_AUDIO" "$REFRESH/step7_library.py" --week "$WEEK"
"$PY_AUDIO" "$HERE/check_names.py" "$BUILD/library.json" "$FIXTURES/manifest.json"

step "8/8 swap into radio/library.json + radio/audio/"
"$PY_AUDIO" "$REFRESH/step8_swap.py" --week "$WEEK" $SHRINK

# --- 4 publish -------------------------------------------------------------
step "publish (site)"
"$HERE/publish.sh"

step "sync hisia-stream"
mkdir -p "$HISIA/radio/audio"
cp "$HERE/library.json" "$HISIA/radio/library.json"
rsync -a --delete "$HERE/audio/" "$HISIA/radio/audio/"
echo "synced $(ls "$HISIA/radio/audio" | wc -l | tr -d ' ') mp3s into $HISIA/radio"
cat <<EOF

NEXT (Kalam runs this - it needs the HF write token, refresh.sh never calls it):

    cd $HISIA && ./deploy.sh

EOF
