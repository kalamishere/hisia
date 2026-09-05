#!/usr/bin/env python
"""Zero-shot world-instrument / feel tagging with LAION-CLAP.

Why this exists
---------------
The radio's tags today come from Essentia heads whose vocabularies simply do
not contain the words we need. Measured over the 103 charting previews in
radio/build_2026-08-24/analysis/:

  * `mtg_jamendo_instrument` has 40 labels, ZERO of them non-Western. Across
    all 103 tracks only 11 distinct instrument labels ever reach a top-5:
    drums, bass, synthesizer, keyboard, percussion, guitar, electricguitar,
    piano, acousticguitar, electricpiano, drummachine.
  * `mtg_jamendo_moodtheme` has 56 labels drawn from a production-music
    library, so "happy" (76/103) and "love" (71/103) dominate every region.

A dholak cannot be reported as a dholak by a model that has never been given
the word. Zero-shot CLAP has no fixed vocabulary: we write the words.

What this does
--------------
1. Embeds a chosen set of chart previews with the LAION-CLAP *music*
   checkpoint (HTSAT-base, music_audioset_epoch_15_esc_90.14.pt) - the same
   checkpoint audio-brief/clap_worker.py uses, so the vectors are comparable
   to everything already in the marathon corpus.
2. Embeds ~80 concept prompts, each written 3 ways, and averages the three
   text vectors into one concept vector.
3. Scores every (track, concept) pair by cosine similarity, and reports both
   the RAW ranking and a CORPUS-CENTERED ranking.

The centering is the whole trick. Raw CLAP cosines are not comparable across
prompts: some concepts sit near the centre of the text manifold and score
~0.30 against literally any audio, while rarer words sit low and never win
even when the instrument is plainly present. Subtracting each concept's mean
score over the corpus (and dividing by its std) removes that per-prompt prior
and asks the only question that matters: "is this concept unusually strong
for THIS track compared with the other tracks we scored?"

Memory discipline
-----------------
This is an 8 GB machine that may be running a local SA3 generation. The
checkpoint is ~2.2 GB and torch adds more. So: refuse to start while
`sa3_mlx` is alive (poll, don't crash), load the model exactly once, run one
sequential batch, write JSON, exit. Never import torch in a long-lived
process.

Usage
-----
    audio-brief/.venv/bin/python radio/research/zeroshot_tags.py \
        --out radio/research/zeroshot_results.json

    --regions IN,AE,KE,TZ,CV,MX,CO,BR,PH   which regions to sample
    --per-region 3                          previews per region
    --no-wait                               skip the SA3 guard (don't)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

FIXTURES = Path(
    "/Users/kalam/ableton-v1-wt-continuous/marathon/fixtures/regional-previews-2026-08-24"
)
RADIO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = RADIO_ROOT / "build_2026-08-24" / "analysis"
LIBRARY = RADIO_ROOT / "library.json"
CKPT = Path.home() / (
    ".cache/huggingface/hub/models--lukewys--laion_clap/snapshots/"
    "b3708341862f581175dba5c356a4ebf74a9b6651/music_audioset_epoch_15_esc_90.14.pt"
)

CLAP_SR = 48_000

# ---------------------------------------------------------------------------
# The vocabulary. Each entry is (bucket, concept, [3 phrasings]).
#
# Three phrasings per concept, deliberately varied: a bare noun phrase, a
# "recording featuring X" frame, and a descriptive sentence. CLAP's text tower
# is sensitive to framing; averaging three reduces the variance of any one
# unlucky wording. Buckets let the card ask for "one instrument + one feel"
# rather than five near-synonyms.
# ---------------------------------------------------------------------------

def _p(concept: str, *extra: str) -> list[str]:
    return [concept, f"a recording featuring {concept}", *extra]


VOCAB: list[tuple[str, str, list[str]]] = [
    # --- South Asian -------------------------------------------------------
    ("instrument", "tabla", _p("tabla drums", "Indian tabla hand drums playing a tala cycle")),
    ("instrument", "dholak", _p("dholak drum", "a dholak barrel drum played by hand in an Indian song")),
    ("instrument", "dhol", _p("dhol drum", "loud double-headed dhol drum in a bhangra beat")),
    ("instrument", "sitar", _p("sitar", "a plucked sitar with sympathetic strings")),
    ("instrument", "harmonium", _p("harmonium", "a hand-pumped Indian harmonium reed organ")),
    ("instrument", "bansuri flute", _p("bansuri bamboo flute", "an Indian bamboo flute melody")),
    ("instrument", "sarangi", _p("sarangi", "a bowed sarangi playing an ornamented Indian melody")),
    ("instrument", "santoor", _p("santoor", "a hammered santoor dulcimer")),
    ("instrument", "tanpura drone", _p("tanpura drone", "a continuous tanpura drone under an Indian melody")),
    ("instrument", "veena", _p("veena", "a plucked South Indian veena")),
    ("instrument", "mridangam", _p("mridangam", "a Carnatic mridangam double-headed drum")),
    # --- Middle East / North Africa ---------------------------------------
    ("instrument", "oud", _p("oud", "a fretless oud lute playing an Arabic maqam")),
    ("instrument", "qanun", _p("qanun", "a plucked qanun zither with Arabic tuning")),
    ("instrument", "ney flute", _p("ney flute", "a breathy ney reed flute")),
    ("instrument", "darbuka", _p("darbuka goblet drum", "a darbuka playing an Arabic rhythm")),
    ("instrument", "riq tambourine", _p("riq tambourine", "a jingling riq frame drum")),
    ("instrument", "arabic strings section", _p("Arabic string orchestra", "a unison Arabic violin section with quarter tones")),
    # --- Sub-Saharan Africa ------------------------------------------------
    ("instrument", "log drum", _p("log drum bass", "a deep pitched log drum bassline in amapiano")),
    ("instrument", "talking drum", _p("talking drum", "a West African talking drum bending in pitch")),
    ("instrument", "shekere", _p("shekere", "a beaded shekere gourd shaker")),
    ("instrument", "djembe", _p("djembe", "a hand-played djembe drum")),
    ("instrument", "kora", _p("kora", "a 21-string kora harp from West Africa")),
    ("instrument", "mbira thumb piano", _p("mbira thumb piano", "a plucked mbira kalimba")),
    ("instrument", "marimba loop", _p("African marimba", "a repeating wooden marimba riff")),
    ("instrument", "highlife guitar", _p("highlife guitar", "a clean interlocking African guitar riff")),
    ("instrument", "afrobeats log-drum kit", _p("afrobeats percussion kit", "syncopated afrobeats shaker and rim percussion")),
    # --- Latin America / Caribbean / Lusophone -----------------------------
    ("instrument", "accordion", _p("accordion", "a squeezed accordion lead melody")),
    ("instrument", "bajo sexto", _p("bajo sexto", "a twelve-string bajo sexto in a norteno band")),
    ("instrument", "mariachi trumpet", _p("mariachi trumpets", "bright paired mariachi trumpets")),
    ("instrument", "tuba bass", _p("tuba bassline", "an oompah tuba bassline in a banda group")),
    ("instrument", "requinto guitar", _p("requinto guitar", "a nylon requinto guitar lead line")),
    ("instrument", "cuatro", _p("cuatro", "a strummed Venezuelan cuatro")),
    ("instrument", "cavaquinho", _p("cavaquinho", "a strummed cavaquinho in a samba")),
    ("instrument", "pandeiro", _p("pandeiro", "a pandeiro Brazilian frame drum")),
    ("instrument", "surdo drum", _p("surdo drum", "a deep surdo drum marking a samba pulse")),
    ("instrument", "steel pan", _p("steel pan", "a struck steel drum pan from Trinidad")),
    ("instrument", "conga", _p("congas", "hand-played conga drums")),
    ("instrument", "timbales", _p("timbales", "a timbales fill in a salsa band")),
    ("instrument", "reggaeton dembow", _p("dembow drum pattern", "the reggaeton dembow kick and snare pattern")),
    ("instrument", "funk carioca beat", _p("baile funk beat", "a Brazilian funk carioca tamborzao beat")),
    # --- SE Asia / Pacific -------------------------------------------------
    ("instrument", "gamelan", _p("gamelan", "a bronze gamelan gong ensemble")),
    ("instrument", "kulintang gongs", _p("kulintang gongs", "a row of tuned Filipino kulintang gongs")),
    ("instrument", "ukulele", _p("ukulele", "a strummed ukulele")),
    ("instrument", "angklung", _p("angklung", "shaken bamboo angklung tubes")),
    # --- Western / studio baseline (control) -------------------------------
    ("instrument", "acoustic guitar", _p("acoustic guitar", "a strummed steel-string acoustic guitar")),
    ("instrument", "electric guitar", _p("electric guitar", "a distorted electric guitar")),
    ("instrument", "piano", _p("acoustic piano", "an acoustic grand piano")),
    ("instrument", "synthesizer", _p("synthesizer", "a synthesizer pad or lead")),
    ("instrument", "808 sub bass", _p("808 sub bass", "a sliding 808 sub-bass in a trap beat")),
    ("instrument", "drum machine", _p("drum machine", "a programmed electronic drum machine")),
    ("instrument", "string section", _p("orchestral string section", "a lush orchestral string arrangement")),
    ("instrument", "brass section", _p("brass section", "a punchy horn section")),
    ("instrument", "saxophone", _p("saxophone", "a saxophone solo")),
    ("instrument", "handclaps", _p("handclaps", "layered handclaps on the backbeat")),
    # --- Voice -------------------------------------------------------------
    ("voice", "playback vocal", _p("Bollywood playback singing", "an ornamented Indian film playback vocal")),
    ("voice", "female lead vocal", _p("a female lead singer", "a woman singing the lead melody")),
    ("voice", "male lead vocal", _p("a male lead singer", "a man singing the lead melody")),
    ("voice", "duet", _p("a male and female duet", "two singers trading lines")),
    ("voice", "call-and-response chorus", _p("call and response chorus", "a lead singer answered by a group chorus")),
    ("voice", "group chant", _p("a chanting crowd", "a shouted group chant")),
    ("voice", "auto-tuned lead", _p("heavily auto-tuned vocals", "a pitch-corrected melodic vocal with audible autotune")),
    ("voice", "rapped verse", _p("rapping", "a rapped verse over a beat")),
    ("voice", "melisma", _p("melismatic singing", "a singer running many notes on one syllable")),
    ("voice", "spoken adlib", _p("spoken ad-libs", "shouted spoken ad-libs over the beat")),
    ("voice", "instrumental, no vocals", _p("an instrumental with no singing", "purely instrumental music")),
    # --- Feel / scene ------------------------------------------------------
    ("feel", "wedding celebration", _p("wedding celebration music", "music for a wedding procession and dancing")),
    ("feel", "monsoon romance", _p("rain-soaked romantic film song", "a longing romantic melody from a film scene")),
    ("feel", "devotional", _p("devotional religious music", "a sacred devotional chant")),
    ("feel", "street party", _p("outdoor street party music", "loud music at a block party")),
    ("feel", "club late night", _p("late-night club music", "a dark hypnotic club track")),
    ("feel", "beach and sunshine", _p("sunny beach music", "breezy tropical daytime music")),
    ("feel", "heartbreak lament", _p("a heartbreak ballad", "a sorrowful song about lost love")),
    ("feel", "defiant swagger", _p("boastful confident music", "a swaggering hard-edged track")),
    ("feel", "cinematic drama", _p("dramatic film score", "a sweeping cinematic build")),
    ("feel", "nostalgic retro", _p("nostalgic retro recording", "an old-fashioned vintage-sounding record")),
    ("feel", "rural working song", _p("countryside working song", "a rustic folk song from the countryside")),
    ("feel", "protest and struggle", _p("protest song", "a defiant song about hardship and struggle")),
    ("feel", "sensual slow groove", _p("a slow sensual groove", "a sultry mid-tempo groove")),
    ("feel", "funeral / mourning", _p("mourning music", "solemn music for a funeral")),
    ("feel", "children's playful", _p("playful children's music", "a bouncy childlike tune")),
    ("feel", "live crowd recording", _p("a live recording with an audience", "music recorded live with crowd noise")),
]


# ---------------------------------------------------------------------------
# SA3 guard
# ---------------------------------------------------------------------------

def wait_for_sa3(max_minutes: int = 40, poll_s: int = 30) -> None:
    """Refuse to load a 2.2 GB checkpoint while a local SA3 gen holds the RAM."""
    deadline = time.time() + max_minutes * 60
    first = True
    while time.time() < deadline:
        r = subprocess.run(["pgrep", "-f", "sa3_mlx"], capture_output=True, text=True)
        if r.returncode != 0:
            if not first:
                print("[guard] sa3_mlx clear - proceeding", file=sys.stderr)
            return
        if first:
            print(f"[guard] sa3_mlx running (pids {r.stdout.split()}); waiting...", file=sys.stderr)
            first = False
        time.sleep(poll_s)
    raise SystemExit("[guard] sa3_mlx still running after the wait window - aborting")


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def pick_tracks(regions: list[str], per_region: int) -> list[dict]:
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    picked: list[dict] = []
    for reg in regions:
        rows = manifest.get(reg, [])
        n = 0
        for row in sorted(rows, key=lambda r: r.get("rank", 99)):
            path = FIXTURES / row.get("preview_path", "")
            if not path.exists():
                continue
            # Skip the global crossover record that appears in half the
            # regions - it tells us nothing about a local scene.
            if "shakira" in path.name and reg not in ("US", "GB"):
                continue
            picked.append(
                {
                    "region": reg,
                    "rank": row["rank"],
                    "artist": row.get("artist", ""),
                    "title": row.get("title", ""),
                    "path": str(path),
                    "key": f"{reg}-{row['rank']}",
                }
            )
            n += 1
            if n >= per_region:
                break
    return picked


def essentia_tags(key: str) -> dict:
    f = ANALYSIS / f"{key}.json"
    if not f.exists():
        return {}
    d = json.loads(f.read_text())
    return {
        "instrument": [t["label"] for t in d.get("tags_instrument", [])[:5]],
        "mood": [t["label"] for t in d.get("tags_mood", [])[:3]],
        "genre": [t["label"] for t in d.get("tags_genre", [])[:3]],
    }


# ---------------------------------------------------------------------------
# Published-track selection (radio/audio/*.mp3 + radio/library.json)
# ---------------------------------------------------------------------------

def pick_published_tracks(regions: list[str] | None) -> list[dict]:
    """The 76 tracks actually on air, from radio/library.json.

    These are synthetic generations, not chart previews, so there is no
    per-track Essentia analysis (build_2026-08-24/analysis/ only covers the
    chart previews SA3 was seeded from). The closest thing to "current
    library tags" is the per-REGION readout baked into library.json at
    generation time (instruments/moods from Essentia over the seed previews,
    plus the hand-written genre_family) - so we attach that to every track in
    the region for the comparison table.
    """
    data = json.loads(LIBRARY.read_text())
    lib_regions = data.get("regions", {})
    picked: list[dict] = []
    for t in data["tracks"]:
        reg = t["region"]
        if regions and reg not in regions:
            continue
        path = RADIO_ROOT / t["file"]
        if not path.exists():
            continue
        ro = lib_regions.get(reg, {}).get("readout", {})
        picked.append(
            {
                "region": reg,
                "rank": t.get("mirrors_rank", 0),
                "artist": t.get("artist", ""),
                "title": t.get("title", ""),
                "path": str(path),
                "key": t["id"],
                "library_tags": {
                    "instruments": ro.get("instruments", []),
                    "moods": ro.get("moods", []),
                    "genre_family": lib_regions.get(reg, {}).get("genre_family", ""),
                },
            }
        )
    return picked


def library_tags(track: dict) -> dict:
    lt = track.get("library_tags") or {}
    return {
        "instrument": lt.get("instruments", []),
        "mood": lt.get("moods", []),
        "genre": [lt.get("genre_family", "")] if lt.get("genre_family") else [],
    }


# ---------------------------------------------------------------------------
# CLAP
# ---------------------------------------------------------------------------

def l2(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-12)


def load_audio(path: str) -> np.ndarray:
    import librosa

    y, _ = librosa.load(path, sr=CLAP_SR, mono=True)
    # Take the middle 10 s: previews often open on an intro that is not
    # representative of the arrangement.
    win = CLAP_SR * 10
    if len(y) > win:
        start = (len(y) - win) // 2
        y = y[start : start + win]
    else:
        y = np.pad(y, (0, win - len(y)))
    return y.astype(np.float32)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--source",
        choices=["published", "charts"],
        default="published",
        help="published = the 76 on-air tracks in radio/audio/ (priority); "
        "charts = the chart previews in radio/build_2026-08-24/analysis/",
    )
    ap.add_argument("--regions", default="")
    ap.add_argument("--per-region", type=int, default=0)
    ap.add_argument("--out", default=str(Path(__file__).with_name("zeroshot_results.json")))
    ap.add_argument("--ckpt", default=str(CKPT))
    ap.add_argument("--no-wait", action="store_true")
    ap.add_argument("--topk", type=int, default=5)
    args = ap.parse_args()

    regions = [r.strip() for r in args.regions.split(",") if r.strip()]
    if args.source == "published":
        tracks = pick_published_tracks(regions or None)
    else:
        tracks = pick_tracks(
            regions or "IN,AE,KE,TZ,CV,MX,CO,BR,PH".split(","),
            args.per_region or 3,
        )
    if not tracks:
        raise SystemExit("no tracks selected")
    print(f"[sel] {len(tracks)} {args.source} tracks: " + ", ".join(t["key"] for t in tracks), file=sys.stderr)

    if not args.no_wait:
        wait_for_sa3()

    import torch  # noqa: F401  (imported late, after the guard)
    import laion_clap

    model = laion_clap.CLAP_Module(enable_fusion=False, amodel="HTSAT-base")
    model.load_ckpt(args.ckpt)
    print("[clap] checkpoint loaded", file=sys.stderr)

    # --- text side ---------------------------------------------------------
    flat, spans = [], []
    for _bucket, _concept, phr in VOCAB:
        spans.append((len(flat), len(flat) + len(phr)))
        flat.extend(phr)
    temb = model.get_text_embedding(flat, use_tensor=False)
    temb = l2(np.asarray(temb, dtype=np.float32))
    concept_vecs = l2(np.stack([temb[a:b].mean(axis=0) for a, b in spans]))
    print(f"[clap] {len(VOCAB)} concepts from {len(flat)} prompts", file=sys.stderr)

    # --- audio side (one sequential batch) ---------------------------------
    aud = []
    for t in tracks:
        y = load_audio(t["path"])
        e = model.get_audio_embedding_from_data(x=y[None, :], use_tensor=False)
        aud.append(np.asarray(e, dtype=np.float32)[0])
        print(f"[clap] embedded {t['key']}", file=sys.stderr)
    A = l2(np.stack(aud))

    # --- scoring -----------------------------------------------------------
    S = A @ concept_vecs.T  # [tracks, concepts] cosine
    # Corpus centering: remove each concept's prompt prior.
    mu = S.mean(axis=0, keepdims=True)
    sd = S.std(axis=0, keepdims=True) + 1e-9
    Z = (S - mu) / sd

    buckets = [b for b, _, _ in VOCAB]
    names = [c for _, c, _ in VOCAB]

    out = {
        "checkpoint": args.ckpt,
        "n_concepts": len(VOCAB),
        "n_prompts": len(flat),
        "tracks": [],
        "concept_prior": {
            names[i]: round(float(mu[0, i]), 4) for i in np.argsort(mu[0])[::-1]
        },
    }
    for i, t in enumerate(tracks):
        raw_order = np.argsort(S[i])[::-1][: args.topk]
        z_order = np.argsort(Z[i])[::-1][: args.topk]

        def by_bucket(bucket: str, k: int) -> list[dict]:
            idx = [j for j in np.argsort(Z[i])[::-1] if buckets[j] == bucket][:k]
            return [{"label": names[j], "z": round(float(Z[i, j]), 2), "cos": round(float(S[i, j]), 4)} for j in idx]

        tags = library_tags(t) if args.source == "published" else essentia_tags(t["key"])
        out["tracks"].append(
            {
                **{k: t[k] for k in ("key", "region", "rank", "artist", "title")},
                "essentia": tags,
                "zeroshot_raw": [
                    {"label": names[j], "cos": round(float(S[i, j]), 4)} for j in raw_order
                ],
                "zeroshot_centered": [
                    {"label": names[j], "z": round(float(Z[i, j]), 2), "cos": round(float(S[i, j]), 4)}
                    for j in z_order
                ],
                "card": {
                    "instruments": by_bucket("instrument", 3),
                    "voice": by_bucket("voice", 2),
                    "feel": by_bucket("feel", 2),
                },
            }
        )

    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"[out] {args.out}", file=sys.stderr)

    # Human-readable comparison to stdout.
    for row in out["tracks"]:
        print("\n" + "=" * 78)
        print(f"{row['key']}  {row['artist']} - {row['title']}")
        e = row["essentia"]
        print(f"  essentia inst : {', '.join(e.get('instrument', [])) or '-'}")
        print(f"  essentia mood : {', '.join(e.get('mood', [])) or '-'}")
        print(f"  essentia genre: {', '.join(e.get('genre', [])) or '-'}")
        print(f"  zs raw        : {', '.join(x['label'] for x in row['zeroshot_raw'])}")
        zs = ", ".join("{}({})".format(x["label"], x["z"]) for x in row["zeroshot_centered"])
        print(f"  zs centered   : {zs}")
        c = row["card"]
        print(
            "  CARD          : "
            + ", ".join(x["label"] for x in c["instruments"])
            + " | "
            + ", ".join(x["label"] for x in c["voice"])
            + " | "
            + ", ".join(x["label"] for x in c["feel"])
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
