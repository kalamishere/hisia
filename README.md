# hisia · World Sound

**[hisia.live](https://hisia.live)** is a radio station that follows the sun. It plays city evenings — Nairobi, then Dubai, then Mumbai as the earth turns; nineteen cities, roughly one for every hour of the clock. Every track is an AI-generated variation on what that city is dancing to this week, read from its chart. No real recording goes into the model. Artist and track names are fictional.

The long version, with what it can and can't do, is in [docs/HOW_ITS_MADE.md](docs/HOW_ITS_MADE.md) and on [Decimal Points](https://decimalpoints.substack.com/).

## The recipe

- **Chart → measurements.** Each city's trending tracks are measured: tempo, key, loudness, and what an instrument/mood model hears. Genre comes from Apple's and Deezer's own labels, because audio classifiers can't tell afrobeats from reggaeton and kept hearing K-pop in Tanzanian records.
- **Measurements → one prompt per city.** *East African afro-pop instrumental, 98 BPM, minor key, log-drum and shaker percussion, warm sliding bass…* The card on the page shows it.
- **Prompt → track.** Stable Audio 3 medium on Hugging Face. Stage one is text-to-audio (prompt + a vocal line + an energy line). Stage two seeds four 30 s chunks from that generation at 0.42 — the setting my ear kept picking — crossfaded and normalised to −14 LUFS. The model seeds from its own output, never from a recording.
- **A hit in fifteen cities.** Charts repeat. A city's sound is read from the hits that are its own; where a whole top five is the world chart the card says so.
- **Page.** One HTML file, no build. Picks among cities within 3.5 hours of evening, weighted toward the one with the sun on the horizon. The sunset is drawn from the playing city's clock.
- **Stream.** The same page in headless Chrome plus a node player, through ffmpeg to Twitch and YouTube. Runs from a laptop or a small VPS; it cannot run from a Hugging Face Space (egress).

Cost for a week: 76 two-minute tracks ≈ 28 GPU-minutes, inside one day of a PRO Hugging Face quota. The site is static and free to serve.

## What's here

| path | what |
|---|---|
| `index.html`, `library.json`, `audio/` | the live site (GitHub Pages) |
| `src/refresh.sh`, `src/refresh/` | the weekly pipeline, steps 1–8: harvest → analysis → genre → readout → generations → stitch → library → swap |
| `src/publish.sh`, `src/check_names.py` | publish guards: refuses real artist/title names, refuses any track not seeded synthetically, refuses a page whose script doesn't parse |
| `src/stream/` | player, capture and console for the 24/7 stream |
| `src/research/` | zero-shot instrument tagging with CLAP — what it finds and where it's wrong |
| `src/SCHEMA.md` | the library format |
| `docs/HOW_ITS_MADE.md` | the post |

The pipeline's harvest and analysis steps call into two private projects on my machine (a chart database and an audio-analysis service), so `refresh.sh` won't run as-is elsewhere. The recipe, the prompts, the guards and the page are all readable and reusable.

## What I'd ask friends in industry

The most direct way to make something generated sound like a region is to seed the model from that region's recordings. Licensing treats that as remixing, so experimenters route around catalogue: synthetic seeds, no influence trail, no one paid. Anyone can do this. Imagine a way to use it that pays artists.

Powered by Stability AI. Built by Kalam Ali with Claude and agentic friends.
