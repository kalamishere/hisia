"""Vernacular genre words, and whether the audio agrees with them.

Apple's taxonomy has no word for amapiano-as-played, bongo flava, mbalax or
coupe-decale; Essentia's heads have none either (src/research/LOCAL_TAGS.md:
40 instrument labels, zero non-Western). CLAP has no fixed vocabulary, so the
words can simply be written.

With no labels for these idioms, the chart itself is the check: a prototype for
"mbalax" should rank Senegalese records above the corpus average. Each idiom
gets its home regions declared up front, and the score is enrichment - how much
of the top 10 charted there, against how much of the corpus does.
"""
import json
from collections import Counter
from pathlib import Path
import numpy as np

R = Path(__file__).resolve().parent
CKPT = str(Path.home() / (".cache/huggingface/hub/models--lukewys--laion_clap/snapshots/"
                          "b3708341862f581175dba5c356a4ebf74a9b6651/"
                          "music_audioset_epoch_15_esc_90.14.pt"))

IDIOMS = {
    "amapiano":       (["amapiano", "amapiano with log drums and shakers",
                        "south african piano house"], {"ZA", "ZW", "MZ", "BW"}),
    "gqom":           (["gqom", "south african gqom drums", "durban gqom"], {"ZA"}),
    "bongo flava":    (["bongo flava", "tanzanian bongo flava",
                        "swahili afro-pop"], {"TZ", "KE", "UG"}),
    "mbalax":         (["mbalax", "senegalese mbalax with sabar drums",
                        "sabar percussion"], {"SN"}),
    "coupe-decale":   (["coupe decale", "ivorian coupe decale",
                        "abidjan dance music"], {"CI"}),
    "kuduro":         (["kuduro", "angolan kuduro", "afro house from luanda"], {"AO", "MZ"}),
    "corridos tumbados": (["corridos tumbados", "requinto guitar corrido",
                           "regional mexican corrido"], {"MX", "US"}),
    "sertanejo":      (["sertanejo", "sertanejo universitario",
                        "brazilian country duo"], {"BR"}),
    "funk carioca":   (["funk carioca", "baile funk from rio",
                        "brazilian favela funk"], {"BR"}),
    "bachata":        (["bachata", "dominican bachata guitar",
                        "bachata romantica"], {"DO", "CO", "ES"}),
    "dembow":         (["dembow", "dominican dembow", "reggaeton dembow beat"], {"DO", "PR"}),
    "dangdut":        (["dangdut", "indonesian dangdut koplo",
                        "dangdut with gendang drums"], {"ID", "MY"}),
    "mahraganat":     (["mahraganat", "egyptian shaabi mahraganat",
                        "cairo street electro shaabi"], {"EG"}),
    "khaleeji":       (["khaleeji", "gulf khaleeji music", "arabic oud and riq"], {"AE", "SA"}),
    "rai":            (["rai", "algerian rai", "moroccan chaabi"], {"MA"}),
    "arabesk":        (["arabesk", "turkish arabesk", "turkish pop with saz"], {"TR"}),
    "luk thung":      (["luk thung", "thai luk thung", "molam from isan"], {"TH"}),
    "v-pop":          (["vietnamese pop", "v-pop ballad", "vietnamese ballad"], {"VN"}),
    "dancehall":      (["dancehall", "jamaican dancehall riddim", "bashment"], {"JM"}),
    "afrobeats":      (["afrobeats", "nigerian afrobeats", "lagos afro-pop"], {"NG", "GH"}),
    "ethio-pop":      (["ethiopian pop", "amharic pop", "ethio-jazz"], {"ET"}),
}

meta = {m["key"]: m for m in json.load(open(R / "real_meta.json"))}
gen = json.load(open(R / "real_genres.json"))

# one row per recording; a recording keeps every region it charted in
rows, order = {}, []
for k, m in meta.items():
    f = R / "emb/real" / f"{k}.npy"
    if not f.exists():
        continue
    fp = str(m.get("deezer_id") or f'{m["artist"]}|{m["title"]}'.lower())
    if fp not in rows:
        v = np.load(f).astype(np.float32)
        rows[fp] = {"vec": v / np.linalg.norm(v), "artist": m["artist"],
                    "title": m["title"], "regions": set(),
                    "genre": (gen.get(k) or {}).get("label")}
        order.append(fp)
    rows[fp]["regions"].add(m["region"])
U = np.stack([rows[f]["vec"] for f in order])
print(f"{len(order)} distinct recordings, {len({r for f in order for r in rows[f]['regions']})} regions\n")

import laion_clap
model = laion_clap.CLAP_Module(enable_fusion=False, amodel="HTSAT-base")
model.load_ckpt(CKPT)

names, T = [], []
for idiom, (phrasings, home) in IDIOMS.items():
    t = np.asarray(model.get_text_embedding(
        [f"this is the sound of {p}" for p in phrasings], use_tensor=False)).mean(axis=0)
    T.append(t / np.linalg.norm(t)); names.append(idiom)
S = U @ np.stack(T).T          # recordings x idioms
np.savez(R / "vernacular_scores.npz", scores=S, idioms=np.array(names),
         keys=np.array(order))
# Hubness: a handful of recordings sit near the centre of the text manifold and
# win every prompt (the same three Indian film tracks topped nine idioms in the
# raw run). Centre each RECORDING across the idioms - "which of these words is
# unusually strong for this track" - instead of reading raw cosines.
Sc = (S - S.mean(axis=1, keepdims=True)) / (S.std(axis=1, keepdims=True) + 1e-9)

print(f"{'idiom':18s} {'home':14s} {'base':>5s} {'raw':>5s} {'centred':>8s} {'lift':>5s}   top 3, centred")
for ci, (idiom, (phrasings, home)) in enumerate(IDIOMS.items()):
    s = Sc[:, ci]
    s_raw = S[:, ci]
    top = np.argsort(-s)[:10]
    top_raw = np.argsort(-s_raw)[:10]
    base = np.mean([bool(rows[f]["regions"] & home) for f in order])
    hit = np.mean([bool(rows[order[i]]["regions"] & home) for i in top])
    hit_raw = np.mean([bool(rows[order[i]]["regions"] & home) for i in top_raw])
    lift = hit / base if base else float("nan")
    ex = "; ".join(f"{rows[order[i]]['artist'][:18]} - {rows[order[i]]['title'][:20]}"
                   f" [{'/'.join(sorted(rows[order[i]]['regions']))[:8]}]" for i in top[:3])
    print(f"{idiom:18s} {'/'.join(sorted(home)):14s} {base:5.2f} {hit_raw:5.2f} {hit:8.2f} {lift:5.1f}   {ex}")
