"""Shared configuration for the weekly World Sound refresh.

Every constant here was carried over from the hand-run build (radio/build/*,
radio/build_public/*) so the weekly command reproduces the same recipe. Where a
value was hand-authored once (region idiom in the prompts, the name lexicon) it
is marked; nothing is silently re-derived.
"""
from __future__ import annotations

import os
from pathlib import Path

RADIO = Path(__file__).resolve().parent.parent
REPO = RADIO.parent
MARATHON = Path("/Users/kalam/ableton-v1-wt-continuous/marathon")
AUDIO_BRIEF = Path("/Users/kalam/ableton-v1/audio-brief")
FIX_ROOT = MARATHON / "fixtures"

# interpreters: no single venv has both psycopg (marathon) and librosa/essentia
# (audio-brief). refresh.sh dispatches each step to the right one.
PY_MARATHON = MARATHON / ".venv/bin/python"
PY_AUDIO = AUDIO_BRIEF / ".venv/bin/python"

# 14 regions, in the order the library has always carried them.
CITY = {
    "KE": ("Nairobi", "Kenya", "Africa/Nairobi"),
    "AE": ("Dubai", "United Arab Emirates", "Asia/Dubai"),
    "TZ": ("Dar es Salaam", "Tanzania", "Africa/Dar_es_Salaam"),
    "NG": ("Lagos", "Nigeria", "Africa/Lagos"),
    "GH": ("Accra", "Ghana", "Africa/Accra"),
    "UG": ("Kampala", "Uganda", "Africa/Kampala"),
    "ZA": ("Johannesburg", "South Africa", "Africa/Johannesburg"),
    "GB": ("London", "United Kingdom", "Europe/London"),
    "BR": ("Sao Paulo", "Brazil", "America/Sao_Paulo"),
    "KR": ("Seoul", "South Korea", "Asia/Seoul"),
    "MX": ("Mexico City", "Mexico", "America/Mexico_City"),
    "US": ("Los Angeles", "United States", "America/Los_Angeles"),
    "IN": ("Mumbai", "India", "Asia/Kolkata"),
    "ID": ("Jakarta", "Indonesia", "Asia/Jakarta"),
    # sunset coverage — one city per hour of longitude (added 2026-09-04)
    "PT": ("Lisbon", "Portugal", "Europe/Lisbon"),
    "EG": ("Cairo", "Egypt", "Africa/Cairo"),
    "AR": ("Buenos Aires", "Argentina", "America/Argentina/Buenos_Aires"),
    "CO": ("Bogota", "Colombia", "America/Bogota"),
    "PH": ("Manila", "Philippines", "Asia/Manila"),
    "AU": ("Sydney", "Australia", "Australia/Sydney"),
    "NZ": ("Auckland", "New Zealand", "Pacific/Auckland"),
    "CV": ("Praia", "Cape Verde", "Atlantic/Cape_Verde"),
}
REGIONS = tuple(CITY)

# GH is not in YouTube's country-code dropdown; it comes from the location
# route (marathon design/LOCATION_CHARTS.md). Its ranks are list positions.
LOCATION_REGIONS = {"GH", "CV"}
CHART_SLUG = "top-songs"
LOCATION_SLUG = "location-top-songs"

# genre-matched BPM priors, exactly as chosen in radio/build/step3_analysis.py
# (MX..KR) and experiments/regional-mirror-2026-09-04/run_analysis.py (KE/AE/TZ).
# Memory rule pj-librosa-bpm-prior: always pass start_bpm.
PRIORS = {
    "KE": 105.0, "AE": 100.0, "TZ": 105.0,
    "NG": 108.0, "GH": 108.0, "UG": 108.0, "ZA": 112.0,
    "GB": 125.0, "BR": 110.0, "KR": 115.0,
    "MX": 120.0, "US": 100.0, "IN": 105.0, "ID": 105.0,
    "PT": 110.0, "EG": 100.0, "AR": 100.0, "CO": 100.0,
    "PH": 100.0, "AU": 110.0, "NZ": 110.0, "CV": 100.0,
}

TOP_N = 5          # chart ranks resolved per region
TRACKS_PER_REGION = 4
CHUNKS = 4

# --- the public recipe (A/B 2 verdict E1+E3, A/B 3 verdict: parallel @ 0.42) --
VARIANT, SECONDS, STEPS, CFG, NOISE = "medium", 36, 8, 1.0, 0.42
# SA3 chunks fade over their last several seconds; generate 36 s and keep the first BODY_S
# so the taper is never on air (measured 2026-09-05: 41 of 76 tracks dipped >6 dB at the joins)
BODY_S = 30
ENERGY_SUFFIX = (", high energy, driving dancefloor groove, vocal chops and "
                 "call-and-response hooks, bright, loud and punchy")
VOCAL_SUFFIX = (", with a prominent lead vocal line, expressive sung melody, "
                "vocal ad-libs")
XFADE = 2.0
LOUDNORM_I, LOUDNORM_TP = -14, -1
MP3_KBPS = "192k"

# measured 2026-09-04: 20.5 GPU-min for 56 tracks x 5 calls
GPU_S_PER_CALL = 20.5 * 60 / (56 * 5)
CALLS_PER_TRACK = 1 + CHUNKS

SPACE = "kalamishere/audiogen"
HF_TOKEN_PATH = Path.home() / ".cache/huggingface/token"
API_TOKEN_PATH = Path.home() / ".config/abv1/audiogen-token"

DSN = os.environ.get("MARATHON_DSN",
                     "postgresql://marathon:marathon@localhost:5432/marathon")


def week_paths(week: str) -> dict:
    """Every week-stamped location. Nothing here ever overwrites last week."""
    return {
        "fixtures": FIX_ROOT / f"regional-previews-{week}",
        "build": RADIO / f"build_{week}",
        "audio": RADIO / f"audio_{week}",
    }


def build_dirs(week: str) -> dict:
    p = week_paths(week)
    b = p["build"]
    d = {
        "root": b, "analysis": b / "analysis", "stage1": b / "stage1",
        "chunks": b / "chunks", "wav": b / "wav", "logs": b / "logs",
        "fixtures": p["fixtures"], "audio": p["audio"],
    }
    return d
