# Music reasoning v0 — can closeness to a library tell you what a track is?

**Ran 2026-09-16.** All local, no paid compute. 636 CLAP embeddings (~35 min),
296 iTunes genre lookups, everything reproducible from this folder.

## Setup

| | |
|---|---|
| query set | 296 real Deezer chart previews, week 2026-09-07, 22 regions (`marathon/fixtures/regional-previews-2026-09-07`) — 194 distinct recordings |
| truth | region from the chart; genre from Apple via iTunes Search (the pipeline's own step 3), 290/296 labelled, collapsed into 12 families in `families.py` |
| index A | the 340 published hisia tracks — synthetic, each with the prompt it was generated from |
| index B | the real previews themselves, leave-one-out, cross-region duplicates masked (860 pairs) |
| embedder | `audio-brief/clap_worker.py`, music checkpoint, tiled 10 s windows. Selftest passed: `repeat@30s = 1.0` |

## Result

Baseline = always answer "pop" (41.4% of these charts): **acc 0.414, macro-recall 0.083**.

| route | acc | top-3 | macro-recall |
|---|---|---|---|
| 1. kNN over the hisia library | 0.268 | — | 0.134 |
| 2. kNN over real chart previews | 0.436 | 0.596 | 0.225 |
| 3. CLAP text zero-shot ("this is the sound of amapiano") | 0.143 | 0.486 | 0.271 |
| 4. routes 2 + 3 summed | 0.421 | 0.632 | 0.251 |

Region, route 2: **acc 0.149 over 60 region classes** (chance 0.017), macro-recall 0.151.

Nothing here beats "say pop" on raw accuracy, and top-3 (0.63) does not beat naming
the three commonest families (0.68). What does move is macro-recall — 0.22–0.27
against 0.083 — so the embedding **can** separate families; it just can't beat a
prior that is itself mostly right.

Per class, route 2:

    afro   0.74 (43)   latin 0.56 (32)   pop   0.48 (116)   east-asian-pop 0.39 (23)
    reggae 0.33 (9)    hiphop 0.18 (22)  arabic dance country rock indian rnb: 0.00

The families that are regionally marked work. The ones that are production styles,
or that have under ~10 examples in the index, do not.

## The load-bearing finding

**The synthetic library is the wrong index.** Real↔library cosine averages **0.383**,
against 0.567 real↔real and 0.632 library↔library. Generated tracks sit in their own
corner of CLAP space; querying them with a real recording lands in a thin region where
ranking is close to arbitrary. Route 1 scores below the "pop" baseline.

So the honest form of the idea is: **index the real chart previews, not the hisia
tracks.** The library's prompts are still the best source of *words* for a description
— they were written to be read — but the retrieval should happen over real audio.

## The single track (held out, real upload)

`Joshua Baraka - YoYo MAIN.mp3`, 3:21. It is itself in the UG chart set; the
self-match is excluded (`query_track.py` drops a neighbour whose artist/title is in
the filename, or any cosine > 0.93).

    0.835  ZW  Shinsoman, Kae Chaps — Always in My Mind   African Dancehall
    0.833  TZ  Harmonize, Jay melody — Imeshindikana      Afrobeats
    0.832  TZ  Harmonize, Marioo — Tangazo                Afrobeats
    0.829  KE  Mbosso — Ozalima                           Afro-Pop
    0.826  UG  King Saha — WEWE                           Afro-Beat

Six of six neighbours are East/Southern African afro-pop; family vote `afro` at 1.00
of the weight. Region vote is TZ (0.34) for a Ugandan record — the right
*neighbourhood*, the wrong country, which is exactly the bound the README already puts
on this. librosa reads 117.5 BPM, E major, −11.2 dB RMS (tempo unverified against the
actual record — librosa halves and doubles).

This is a good case, not a typical one: `afro` is the best-performing class.

## What to try next, cheapest first

1. **Bigger real index.** Weeks 08-24, 08-31 and 09-07 are all on disk → ~900
   previews, 3× the thin classes. The zero classes above are mostly an index-size
   problem. Same code, one more embed run.
2. **Drop "pop" as an answer.** Apple labels 40% of charts Pop; it is the noise class.
   Scoring on non-pop only says what the method knows when the label means something.
3. **Describe, don't classify.** The usable output is not a genre word, it is
   "nearest to X, Y, Z; bpm 118; E major; the prompts those neighbours came from say
   log-drum, sliding bass, sunny". That composition is what `query_track.py` already
   returns and it does not depend on winning a 12-way classification.
4. Only then: a seeded-listening check, and whether an LLM pass over
   (features + neighbours + neighbour prompts) reads as true to the ear.

## Files

    query_track.py     any audio file -> features, neighbours, votes (the demo)
    eval_retrieval.py  routes 1 and 2, region + family, with the duplicate mask
    metrics.py         macro-recall, top-3, fusion, per-class tables
    zeroshot_genre.py  CLAP text side, 12 families x 3 phrasings
    families.py        the Apple-label -> family mapping, shared by both sides
    fetch_genres.py    iTunes Search lookups (cached in real_genres.json)
    emb/lib, emb/real  636 L2-normalised 512-d vectors


---

# Round 2 — three weeks, and the question asked properly

**Ran 2026-09-16.** Weeks 08-24, 08-31 and 09-07 embedded: 881 chart slots,
**283 distinct recordings** (the charts repeat heavily week to week and city to
city), 851 slots labelled by Apple.

The right test for "if we have 12 tracks labelled amapiano, will it recognise an
amapiano track" is detection, not 12-way classification: average the N labelled
vectors into a prototype, rank every recording by cosine to it, score ROC AUC.
Chance = 0.500, and a "pop"-heavy label distribution can't flatter it.
`prototype_eval.py`.

## Prototypes from real tracks (held out: prototype tracks excluded from scoring)

| family | n_proto | n_query+ | AUC | prec@N |
|---|---|---|---|---|
| regional-mex | 3 | 3 | **0.980** | 0.33 |
| kpop | 5 | 5 | **0.931** | 0.20 |
| indian | 3 | 4 | **0.875** | 0.25 |
| dancehall | 2 | 3 | 0.862 | 0.33 |
| afrobeats | 20 | 20 | **0.858** | 0.50 |
| reggaeton | 5 | 5 | 0.840 | 0.00 |
| reggae | 2 | 3 | 0.753 | 0.00 |
| pop | 25 | 26 | 0.614 | 0.23 |
| hiphop | 13 | 14 | 0.606 | 0.07 |
| rnb | 2 | 2 | 0.502 | 0.00 |
| dance | 6 | 7 | 0.459 | 0.00 |
| rock | 3 | 4 | 0.355 | 0.00 |
| arabic | 5 | 5 | 0.312 | 0.00 |

**The class decides, not the count.** The learning curve says the same: afrobeats
is already 0.730 from a *single* labelled track, 0.821 at N=5, 0.833 at N=12 —
while dance sits at 0.54 for N=1 and 0.48 at N=12. More labels do not rescue a
family the embedding doesn't hear as one thing. Below-chance AUCs (arabic, rock)
are label noise as much as audio: "Arabic Pop" is pinned on productions with
nothing in common.

## Prototypes from the generated hisia tracks — the answer is no

| family | n_proto (generated) | n_query+ | AUC |
|---|---|---|---|
| afro | 100 | 54 | 0.733 |
| country | 12 | 3 | 0.624 |
| rock | 8 | 7 | 0.602 |
| pop | 56 | 57 | 0.598 |
| east-asian-pop | 52 | 16 | 0.573 |
| arabic | 8 | 11 | 0.536 |
| latin | 52 | 28 | 0.485 |
| hiphop | 44 | 28 | 0.460 |
| reggae | 8 | 9 | 0.433 |

Fifty-two generated latin tracks make a prototype that ranks real latin music at
0.485 — chance. Only `afro` carries, and at 0.733 against 0.858 for the real
prototype. Consistent with the 0.383 cross-domain cosine: the generated corpus
has its own accent, and genre identity does not survive the crossing.

## Words alone get most of the way

Text prototype ("this is the sound of amapiano"), no labelled tracks at all,
against the in-sample audio prototype as a ceiling:

    afrobeats  text 0.804 / audio 0.854      indian  text 0.940 / audio 0.984
    kpop       text 0.866 / audio 0.967      reggaeton text 0.738 / audio 0.849
    dancehall  text 0.394 / audio 0.942      regional-mex text 0.799 / audio 0.996

So a labelled set is worth having where the word is ambiguous to CLAP
(dancehall, regional-mex, reggae) and close to redundant where it isn't.

## Amapiano specifically: not answerable from these labels

Apple calls **2 of 283** distinct recordings "Amapiano" — the label is used for
the sub-genre almost never, and amapiano records get filed under Afrobeats,
Afro-Pop or Pop. To answer the question as asked, the 12 tracks have to be
hand-labelled: shortlist candidates with the amapiano text prototype across the
African charts, listen blind, keep the ones that are actually amapiano, then run
the same detection test. That is the next run, and it needs an ear, not a GPU.

---

# Round 3 — the real charts scored against hisia's own genres

Same question, no new machinery: the 283 distinct YouTube-trending recordings
matched to Deezer previews, each with its Apple genre, ranked against the 340
generated hisia tracks. `route1_eval.py`.

The hisia side is labelled two independent ways, because "the genre of a
generated track" isn't a given:

- **prompt** — read out of the SA3 prompt it was generated from (regex)
- **chart** — the modal Apple genre of that region's own chart, i.e. the genre of
  the material the prompt was written from, no regex in the loop

They agree on only **60%** of the library. Chart labels score better, so the rest
uses both.

    baseline: always "pop"              acc 0.241   macro-recall 0.083
    kNN over hisia, prompt labels       acc 0.316   macro-recall 0.147
    kNN over hisia, chart labels        acc 0.367   macro-recall 0.160

Detection, real tracks ranked by cosine to each hisia genre prototype:

| family | hisia n | real n | AUC-prompt | AUC-chart |
|---|---|---|---|---|
| afro | 100 | 54 | 0.733 | 0.735 |
| country | 12 | 3 | 0.624 | — |
| rock | 8 | 7 | 0.602 | — |
| pop | 56 | 57 | 0.598 | 0.627 |
| east-asian-pop | 52 | 16 | 0.573 | 0.517 |
| hiphop | 44 | 28 | 0.460 | 0.572 |
| arabic | 8 | 11 | 0.536 | 0.536 |
| latin | 52 | 28 | 0.485 | 0.491 |
| reggae | 8 | 9 | 0.433 | 0.446 |
| indian | 0 | 7 | — | 0.711 |
| dance | 0 | 13 | — | — |
| rnb | 0 | 4 | — | — |

Two limits, both structural:

1. **Coverage.** The library is organised by city, not genre. It has no dance,
   no rnb and (by prompt) no indian at all, so 24 of the 237 labelled queries
   have nothing they could match.
2. **Only afro clears.** 0.735 from a hundred generated tracks, against 0.858
   from twenty real ones. Latin, reggae and hiphop sit at chance with fifty-two,
   eight and forty-four prototypes respectively — the count isn't the problem.

So the hisia set works as a genre reference only for the family it was mostly
built from, and even there it is worse than a handful of real recordings.

---

# Round 4 — the vernacular words themselves

The taxonomies we're missing are the local ones: amapiano, bongo flava, mbalax,
coupe-decale, dangdut, mahraganat, corridos tumbados. Apple has no label for
them (it files them under Pop or Afrobeats) and Essentia has no word for them at
all — `src/research/LOCAL_TAGS.md` measured that: 40 instrument labels, none
non-Western.

With no labels for these idioms, the chart is the check. Each idiom's home
regions are declared up front and the score is enrichment: how much of its top
10 charted there against how much of the corpus does. `vernacular_probe.py`,
283 distinct recordings, 60 regions, 21 idiom prompts.

First run was hub-dominated — the same three Indian film tracks topped nine
different idioms, because some audio vectors sit near the centre of the text
manifold and win every prompt. Scores are centred per recording across the 21
idioms ("which of these words is unusually strong for this track"), which is the
same trick LOCAL_TAGS.md used, applied on the other axis.

| idiom | home | base | top-10 in home | lift |
|---|---|---|---|---|
| mbalax | SN | 0.03 | 0.30 | **9.4** |
| dembow | DO/PR | 0.03 | 0.20 | **6.3** |
| khaleeji | AE/SA | 0.04 | 0.20 | **5.1** |
| luk thung | TH | 0.02 | 0.10 | 4.7 |
| corridos tumbados | MX/US | 0.05 | 0.20 | **4.0** |
| amapiano | ZA/ZW/MZ | 0.07 | 0.20 | 2.8 |
| afrobeats | NG/GH | 0.06 | 0.10 | 1.6 |
| bachata | DO/CO/ES | 0.07 | 0.10 | 1.4 |
| gqom, bongo flava, coupe-decale, kuduro, sertanejo, funk carioca, dangdut, mahraganat, rai, arabesk, v-pop, dancehall, ethio-pop | | | 0.00 | **0.0** |

**CLAP knows the sounds, not the vernacular words.** The clearest case is
afrobeats: the word scores a lift of 1.6, while twenty labelled afrobeats tracks
give AUC 0.858. Same music, same embedding — the failure is the caption
vocabulary the model was trained on, which has "k-pop" and "country" in it many
thousands of times and "bongo flava" almost never.

This reverses round 2's "words get most of the way": that held for genres with
global marketing behind them (kpop 0.866, indian 0.940, country), i.e. exactly
the ones already in every commercial tagger. For the local taxonomies — the ones
nothing else names — **labelled examples are not redundant, they are the only
route**.

Enrichment is a weak proxy in one direction only: a Senegalese chart is not all
mbalax, so no lift is not proof a word failed. Lift is evidence a word worked.
