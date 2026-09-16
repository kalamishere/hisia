# hisia.live — how it's made (Kalam's draft, 2026-09-05)

*Written on 5 September, and kept as it was — the three-step story of how the recipe arrived is the point of it. The numbers below have been corrected where they were wrong, and a postscript at the end says what changed after this was written.*

hisia.live is a radio station that follows the sun. It plays city evenings — Nairobi, then Dubai, then Mumbai as the earth turns; fifty-four cities, one for roughly every hour of the clock. Tracks are generated from an audio-analysis reading of what that city is dancing to this week, based on its charts.

Here's how it works, and what it can't do.

## The chart is the signal → LLM ears

I read YouTube charts for the selected cities — nineteen when this was written, fifty-four now. Trending tracks get measured: tempo, key, loudness, and what an instrument/mood model hears in them. Genre is added from Apple's and Deezer's own labels — audio classifiers can't tell afrobeats from reggaeton from dancehall, and kept hearing "K-pop" in Tanzanian records.

Those measurements are quite detailed. They are converted into text prompts using LLMs to create audio per city. Nairobi this week: *East African afro-pop instrumental, 98 BPM, minor key, log-drum and shaker percussion, warm sliding bass, bright plucked guitar, dancehall-zouk swing, sunny and romantic.*

The LLM gets ears — and it makes a prompt for audio gen. The card on screen shows the prompt, derived from audio analysis: tempo, instrumentation, mode, genre family.

## How the recipe got here

I'm using Stable Audio 3 medium, hosted on Hugging Face, to generate the audio. Three steps, in the order they happened:

1. **Audio to prompt.** Measure a chart's trending audio and write a prompt from the numbers — tempo, key, instruments, mood, genre label — then generate from the text prompt alone. It works, sounds decent, but can sometimes seem like a jingle for ads: you wouldn't dance to it — and it also varied in style from the measured chart.

2. **Seeding.** Give SA3 audio clips to create a vibe instead of only a text prompt. This lets you influence the vibe of generations, which creates a form of consistency. These experiments got interesting. The music had a direction and pulse, and the model's attempts at singing — smeared, weird, voice-shaped almost-words — were the most fun thing. Not for everyone; I loved them — something to explore.

3. **Audio to prompt, then seed from the model's own generation** — what you are hearing. Stage one generates a track from the prompt (with a vocal line and an energy line added by the LLM to make it interesting to listen and dance to). Stage two then takes that generated track as the seed and varies it. This uses audio the model made from a prompt — AI singing shows up occasionally.

There was a small amount of checking outputs by ear; it mostly worked as described above (worth mentioning, the half day of building this for fun was preceded by months of audio-analysis-for-prompt experiments, genre mashing, neural plugin battles and gen-audio consistency tests).

Trends tend to repeat on charts — a track can be number one in fifteen cities. So a city's sound is read from the hits that are its own, and when a city's whole top five is the world chart — Sydney and Auckland this week — the card says: "a hit in 15 cities this week."

## Nerding out — what the numbers say and don't

I tried to measure "does this sound like Nairobi" with audio embeddings (CLAP) and with measured audio-analysis readouts. Both say the same thing: the chart audio of Nairobi, Dubai and Dar es Salaam look like neighbours. Genres and language — music metadata — set them apart. The human stuff. LLMs with ears hear them as sonic neighbours. So under the tracks the site says *a variation on this week's chart, after #3*.

Other things the numbers and I clashed about: similarity metrics preferred tracks that vary more; I preferred the consistent one. In this instance, consistency beat measured variety for a stream (but not for experiments with AI drum n bass!).

## Cost — half a day wondering if this will work

A two-minute track costs about 22 GPU-seconds, so a weekly refresh sits inside a single day's included quota on a PRO Hugging Face account, and it is one command. The site is a static page on GitHub Pages and costs nothing to serve.

The 24/7 stream does **not** run in a Hugging Face container. I tried, and the platforms do not accept a live stream from that egress — Twitch takes the RTMP session and never goes live, YouTube sits on "Preparing stream". Same key, same ffmpeg arguments, fine from a laptop. It took a night to isolate. It runs from a small always-free ARM box instead. (Claude wrote this, obviously.)

## What I'd ask friends in industry

The most direct way to make something generated sound like a region would be to seed the model from that region's recordings.

Licensing treats that as remixing.

So experimenters route around catalogue — synthetic seeds, no influence trail, no one paid, no listener learning where it came from, black boxes.

This stuff is fun. And anyone can do it. Especially fans of an artist.

Imagine figuring out a way to use this to make money for artists. Feels like an obvious win.

## The recipe, for builders and agents (as it stood on 5 September — see the postscript)

- Charts → per-track measurements (tempo, key, loudness, instrument and mood tags; genre from store labels) → one prompt per city
- SA3 medium: stage one text-to-audio (prompt + vocal line + energy line), stage two audio-to-audio from that at 0.42 — the setting my ear kept picking in earlier tests — four 30 s chunks crossfaded, loudnorm −14 LUFS
- Fictional artist and title per track, checked against every real chart artist and title
- Page: one HTML file; picks among cities within 3.5 hours of evening, weighted toward the one with the sun on the horizon; sunset drawn from the playing city's clock
- Stream: the same page in headless Chrome + a node player → ffmpeg → Twitch, from a small always-free ARM box (not a Hugging Face Space — see above)

Powered by Stability AI. A Friday afternoon experiment with Fable and agentic friends.

---

## Postscript, 16 September

The recipe above is not the one running now. What changed, in the order it happened:

**Fewer joins beat better joins.** Two versions went into making the seams between four parallel 30-second chunks less audible. The fix was to stop having seams. A track is now one 36-second seeded chunk grown into a continuous two minutes by a single inpaint call, with a second inpaint writing a 15-second intro — kept only when its first five seconds sit at least 8 dB under the body. The stitch keeps each generation's own ending rather than cutting before it.

**The vocal line is measured, not written.** It comes from Demucs stems through pyin — median pitch, range, onset rate — per city, rather than one hand-written idiom per region.

**The energy line is gone.** Every prompt used to end with "high energy, driving dancefloor groove … bright, loud and punchy". It was written to restore punch lost across the four-chunk recipe, the recipe changed, and the clause stayed. Measured across eight tracks it was the brightest arm in seven and the thinnest under 200 Hz in six — and it was telling a 71 BPM Hong Kong chart to be a dancefloor.

**Nineteen cities became fifty-four**, and the library appends rather than being replaced, so a published set is a mixture of recipe versions and each track says which one it is.

**Each track stores its own prompt.** The card used to show the region's current prompt, which drifted as the chart weeks moved on. It now shows the prompt that track was actually generated from.

The reason any of this is worth writing down: every one of those changes was decided blind, by ear, and the measurements were run afterwards to explain the verdict rather than to reach it.
