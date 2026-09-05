# radio/stream — the World Sound broadcast leg (laptop)

The streaming half of hisia.live. It plays the library on the same
follow-the-sun rule the page uses, renders the page itself as the picture, and
pushes one encoded stream to Twitch and/or YouTube. Plain node, no build step,
no dependencies outside ffmpeg and Chrome.

```
library.json ──▶ player.js ──▶ 48k stereo PCM ──┐
                    │  (playlist brain, 2 s      │
                    │   equal-power crossfade)   │
                    ▼                            ▼
              server.js :4700 ────────────▶  ffmpeg ──▶ tee ──▶ Twitch
                    │  /now.json                ▲              ├─▶ YouTube
                    ▼                           │              └─▶ ~/Movies/hisia
        radio/index.html?stream=1  ──▶ headless Chrome ──▶ JPEG pull ──▶ fifo
                (puppet mode: displays what the backend plays)
```

## Run it

```bash
node radio/stream/server.js          # port 4700; the radio is on air immediately
open http://127.0.0.1:4700/stream/console
```

| surface | what it is |
| --- | --- |
| `GET /radio/index.html` | the page (served from `../`, so its `library.json` and `audio/` resolve) |
| `GET /now.json` | `{track, region, city, startedAt, durationS, elapsedS, next}` |
| `POST /skip` | crossfade to the next track now (0.5 s instead of 2 s) |
| `POST /broadcast` | `{action:"start"\|"stop", targets:["twitch","youtube","file"]}` |
| `GET /status.json` | live, legs, distinct fps, max inter-frame gap, dropped, uptimes, now |
| `GET /pcm` | the raw 48 kHz stereo s16le radio feed (ffmpeg's audio input, and the tap for testing) |
| `GET /stream/console` | the operator page |

`RECORD=1 node radio/stream/server.js` adds a local mp4 to every broadcast.
`targets:["file"]` broadcasts to nothing but that mp4 — the way to rehearse
without stream keys.

## Env

Copy `.env.example` to `radio/stream/.env` (gitignored):

```
TWITCH_STREAM_KEY=…
YOUTUBE_STREAM_KEY=…
YOUTUBE_INGEST=rtmp://a.rtmp.youtube.com/live2   # optional
```

Keys are read only by `server.js`, handed to `capture.js` through its
environment as complete RTMP urls, and never logged, never in `/status.json`,
never served (a request for `.env` gets a 403).

## The parts

**player.js** — the same picker as the page: score every region by distance
from local 20:00, round to the half hour so near-ties are equal, break ties at
random, hold out the last three regions, one track per pick, no repeat inside a
region until its pool is spent. Each track is decoded once by ffmpeg into
memory as 48 kHz stereo PCM and mixed into one never-ending stream on a
drift-corrected wallclock, with a 2 s equal-power crossfade at every boundary.
Sinks attach and detach (ffmpeg, the `/pcm` tap); the clock never stops, so
starting or stopping a broadcast does not disturb the radio.

**capture.js** — headless Chrome on `?stream=1`, viewport pinned to 1920×1080
with CDP `Emulation.setDeviceMetricsOverride` (the `--window-size` flags are
ignored in `headless=new` — pj-battle measured a cropped frame that way), frames
**pulled** with `Page.captureScreenshot` on a drift-corrected clock at ~26/s,
and a CFR pump writing exactly 20 of them a second into a fifo, newest wins.
x264 veryfast 4500 kbps + AAC 160 kbps, teed to Twitch (leg 0, the only one that
can fail the run) and YouTube/file with `onfail=ignore`. It verifies the first
JPEG really is 1920×1080 and says so. **Audio never comes from the browser** —
Chrome runs `--mute-audio` and the sound is player.js's PCM over `/pcm`.

Two timestamp traps cost most of the build time here, both measured on this
machine and both written up in the file:

- `-use_wallclock_as_timestamps 1` on the video (pj-battle's write-through
  recipe) puts it ~1.8e9 s ahead of a PCM input whose clock starts at zero.
  ffmpeg then reads the fifo in dribbles: a standing 4 MB backlog and about
  15 of every 20 captured frames thrown away, while the encoder still reported
  `speed=0.999x` and a clean 20 fps output — of duplicates.
- Putting the audio on wallclock too balances the reads and destroys the AAC
  track (raw PCM arrives in big chunks, so its timestamps stop advancing by
  sample count — the recorded audio came out 0.12 s long). `-copyts
  -start_at_zero`, an `asetpts` filter, and `-itsoffset` each fail differently.

So both inputs keep their natural clocks — the demuxer's `-framerate 20` for
the video, the sample count for the audio — and the pump makes the first of
those true. The pump also keeps the fifo nearly empty and rebases its own clock
whenever it is not: a bounded-but-full queue is a permanent delay (the picture
ran ~5 s behind the sound), and skipping a slot without rebasing repays it as a
burst of the same frame.

**Generation guard** — every `start()` mints a generation, `stop()` invalidates
it first; a stale child's exit handler can never null the generation that
replaced it. That is the pj-battle bug that orphaned ffmpeg and Chrome.

**Puppet mode** — `radio/index.html?puppet=1` (implied by `?stream=1`) polls
`/now.json` every 2 s and displays the backend's track: city, clock, card, sun
for that city, strip and next-up, with the progress bar driven by
`startedAt + durationS`. It decodes no audio. Without the flag the page is
exactly what it was — its own player.

## One-hour test

1. `node radio/stream/server.js`, open the console, watch `/now.json` change
   city roughly every two minutes and `underrun blocks` stay at 0.
2. Tap the audio and look for gaps:
   `curl -s --max-time 150 http://127.0.0.1:4700/pcm -o tap.raw` then check for
   silent runs (`node -e` over the s16le, or
   `ffmpeg -f s16le -ar 48000 -ac 2 -i tap.raw -af silencedetect=n=-60dB:d=0.05 -f null -`).
   Track boundaries should show as an overlap, never a hole.
3. Rehearse the picture with no keys:
   `curl -XPOST -d '{"action":"start","targets":["file"]}' localhost:4700/broadcast`.
   Watch `/status.json` → `capture.freshFps` (target ≥ 19 of `cfrFps` 20),
   `distinctFps` (the sampler, ~26), `maxInterFrameGapMs`, `dropped` (should
   stop climbing after startup) and `frameSize` = `1920x1080`. Then
   `ffprobe -count_frames` the mp4: frames ÷ duration must be 20.0, and
   decoding the audio track must give a length within ~2 s of the video.
4. For a real hour: start with `targets:["twitch"]`, then check every 15 min
   that `broadcastUptimeS` is still climbing, `freshFps` has not fallen
   below ~18, and Chrome + ffmpeg are still exactly one process each
   (`pgrep -fl 'capture.js|hisia-capture-'`).
5. Stop, and confirm no Chrome or ffmpeg survives.

## Known limits

- **Not verified against a real ingest.** With no stream keys on this machine
  the RTMP legs, the tee's `onfail=ignore` behaviour on a dead secondary, and
  Twitch's reconnect handling are untested here.
- **8 GB laptop.** Measured while capturing: 0.85 of one core (11% of the M3's
  eight) and ~620 MB resident across ffmpeg, Chrome, the pump and the server.
  It is Chrome's screenshot latency, not the encoder, that gives way first —
  under other load the sampler saw inter-frame gaps of 1–2 s, which show up as
  a few repeated frames a second. Running SA3 or Magenta alongside will do
  that; drop to 1280×720 if the box has to do anything else.
- **Recordings are fragmented mp4** (`+frag_keyframe+empty_moov`) so a killed
  run still leaves a playable file. `+faststart` does not survive a SIGTERM.
- **No fallback visual.** If Chrome dies, capture.js exits and the broadcast
  ends. pj-battle fell back to a synthesised visualiser; there is no equivalent
  here yet — the server just reports `live:false`.
- **The radio never restarts itself.** A library edit needs a server restart.
- **Skips are backend-only.** Chat control, fresh generation, and the region
  commands from the handoff are not wired in.
- **Clock assumptions.** Puppet progress assumes the browser and the server
  share a clock (they do — same machine).
