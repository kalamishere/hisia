# hisia · World Sound

**[hisia.live](https://hisia.live)** is a radio station that follows the sun. It plays city evenings — Nairobi, then Dubai, then Mumbai as the earth turns; 54 cities, refreshed every week. Every track is an AI-generated variation on what that city is dancing to this week, read from its chart. No real recording goes into the model. Artist and track names are fictional.

The long version, with what it can and can't do, is in [docs/HOW_ITS_MADE.md](docs/HOW_ITS_MADE.md) and on [Decimal Points](https://decimalpoints.substack.com/).

## The recipe

- **Chart → measurements.** Each city's trending tracks are measured: tempo, key and loudness with librosa, and a vocal line taken from Demucs stems through pyin — median pitch, range, onset rate. Genre comes from Apple's and Deezer's own labels, because audio classifiers can't tell afrobeats from reggaeton and kept hearing K-pop in Tanzanian records. A track charting in four or more cities is dropped from that city's reading: a global hit carries no regional information.
- **Measurements → one prompt per city.** *East African afro-pop instrumental, 94 BPM, minor key, live log-drum and shaker percussion, warm sliding bass…* The card on the page shows it, with a copy button. Each track stores the prompt it was generated from, so the card shows that rather than this week's.
- **Prompt → track.** `stabilityai/stable-audio-3-medium` on a Hugging Face Space, 8 steps. Stage one is text-to-audio. Stage two seeds from stage one's own output at 0.42 — the setting my ear kept picking — and makes one 36-second chunk. Text-only generations sound like advertising jingles; the seeded pass is what sounds like radio.
- **One chunk → two minutes.** A single inpaint call grows that chunk into a continuous ~120 seconds. A second inpaint writes a 15-second intro, kept only when its first five seconds sit at least 8 dB under the body. The stitch keeps the generation's own ending, trims trailing silence, fades 1.5 s and normalises to −14 LUFS. The model seeds from its own output, never from a recording.
- **A hit in fifteen cities.** Charts repeat. A city's sound is read from the hits that are its own; where a whole top five is the world chart the card says so.
- **Page.** One HTML file, no build. Follows the sun by local hour; "drift" mode instead orders play by sound, each next track the closest by CLAP embedding. Sun and moon are drawn at their real positions over the playing city, the moon with its true phase, and the sky colour comes from the sun's elevation.
- **Stream.** The same page in headless Chrome plus a node player, through ffmpeg to Twitch. It runs from a small always-free ARM box. It cannot run from a Hugging Face Space — the platforms do not accept a live stream from that egress, which took a night to isolate.

Cost: about 22 GPU-seconds per two-minute track, so a weekly refresh sits inside one day of the 40 GPU-min included on a PRO Hugging Face account. The site is static and free to serve.

## What the recipe got wrong first

Kept here because the mistakes were worth more than the things that worked.

- **Fewer joins beat better joins.** Two versions went on making the seams between four parallel 30-second chunks less audible. The fix was to stop having seams — grow one generation instead.
- **A workaround outlived its problem.** Every prompt for every city used to end with "high energy, driving dancefloor groove … bright, loud and punchy", written to restore punch lost across the old four-chunk recipe. The recipe changed and the clause stayed. Measured across eight tracks it was the brightest arm in seven and the thinnest under 200 Hz in six, and it was telling a 71 BPM Hong Kong chart to be a dancefloor. Dropped.
- **Gates need a floor as well as a ceiling.** The intro gate asked whether the lead-in was quieter than the body. Five seconds of digital silence passed it with an 86 dB margin.

## What the numbers will not support

"This sounds like Nairobi." With CLAP embeddings, two tracks from the same city sit at 0.78 cosine and two from different cities at 0.58 (160 tracks, measured 2026-09-06). That is enough to order playback by sound, which is what drift mode does. It is not enough to certify a region, so the card says "a variation on this week's Nairobi chart, after #3" and stops there.

## What's here

| path | what |
|---|---|
| `index.html`, `library.json`, `audio/` | the live site (GitHub Pages) |
| `src/refresh.sh`, `src/refresh/` | the weekly pipeline, steps 1–8: harvest → analysis → genre → readout → generations → stitch → library → append |
| `src/publish.sh`, `src/check_names.py` | publish guards: refuses real artist/title names, refuses any track not seeded synthetically, refuses a page whose script doesn't parse |
| `src/stream/` | player, capture and console for the 24/7 stream |
| `src/research/` | zero-shot instrument tagging with CLAP — what it finds and where it's wrong |
| `src/SCHEMA.md` | the library format |
| `docs/HOW_ITS_MADE.md` | the post |

The pipeline's harvest and analysis steps call into two private projects on my machine (a chart database and an audio-analysis service), so `refresh.sh` won't run as-is elsewhere. The recipe, the prompts, the guards and the page are all readable and reusable.

## What I'd ask friends in industry

The most direct way to make something generated sound like a region is to seed the model from that region's recordings. Licensing treats that as remixing, so experimenters route around catalogue: synthetic seeds, no influence trail, no one paid. An early stream seeded from real chart number ones collected four Content ID claims naming exactly those recordings — audio-to-audio at 0.42 from a commercial recording is close enough to fingerprint. Everything since is synthetic-only. Anyone can do this. Imagine a way to use it that pays artists.

Powered by Stability AI. Built by Kalam Ali with Claude and agentic friends.

## Licence

Code is MIT. The audio, library, prompts and notes are CC BY 4.0. See [LICENSE.md](LICENSE.md).
