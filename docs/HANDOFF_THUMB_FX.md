# Thumb FX — one-handed effects mode for the phone player

Brief written 2026-09-17 from the ideas session. Design settled enough to build; every number below is checked against the repo or a cited app. Uncommitted on purpose — commit with your first change.

## The ask
An effects mode on the phone that needs only a thumb. Reverb, delay, filter. Kalam's reference was the Curate alpha app associated with Melo-X, plus "these kinds of effects are in a few DJ apps too".

## What the research found
- **The Curate decks do not contain this design.** Both PDFs in the personal Drive (`My Drive/Next /CURATE/`, 9pp and 10pp, Apr 2019) are a Splice-style sample browser: a rotating octahedron, four one-shots and four loops per face, a face that lights when played. No effects, no gesture-to-parameter mapping, no momentary-vs-latch. Melo-X appears only as sample filename prefixes (`MELOX_`, `MELOXTRA_`). Do not go looking again; it is not there.
- **The DJ app survey is the usable reference.** Recurring patterns, ranked for a thumb on a phone held one-handed (reach is an arc at the bottom of the screen):
  1. Single-axis vertical drag in the bottom arc (Koala's filter strip: up = highpass, down = lowpass from centre; Figure's play pad). Best fit, and structurally cannot collide with a horizontal skip swipe.
  2. Hold-in-place (Kaoss Pad HOLD, Instant FX). Unambiguous, needs no direction.
  3. XY pad in a corner (Kaoss, djay, Cross DJ). Expressive, but the far corner sits outside comfortable thumb reach.
  4. Full horizontal drag. Worst fit here: it is exactly the existing skip gesture.
- **Musical safety, as the apps do it.** Traktor's filter passes the whole band at centre so it never fully kills the signal, and its Peak Filter brickwalls boost at 0 dB. Kaoss FX RELEASE lets a tempo-synced delay tail decay instead of hard-cutting. Cross DJ's "free" mode auto-returns to neutral on release; its "locked" mode latches at the release position.

## What the code already gives us
- **A real Web Audio graph exists.** `index.html` ~1045–1060: `createMediaElementSource(el)` → per-track `gain` → `master` → `destination`. Effect nodes insert between the track gain and master with no re-architecture.
- **A fallback path has no graph.** `if (PLAIN) return {el:el, track:null}` returns early. Thumb FX must degrade to a clean "not available" state there, never throw.
- **The existing gesture, `index.html:1560–1570`.** Swipe left = next: `dx < -60 && Math.abs(dy) < 50 && Date.now() - t0 < 700`. The comment already notes a scroll inside the prompt box is not a swipe. Whatever is built must keep that true.
- **Every track carries BPM and mode.** `library.json` `readout: {bpm, mode, instruments, moods}`, present on all 328 tracks. This is the advantage no DJ app has by default: delay times can snap to the grid of the track actually playing, with no live analysis.

## The design to build
**Press and hold to engage, then the thumb is in effects mode.** A hold of ~180 ms in the bottom arc engages. This is structurally different from a swipe, so a fast horizontal skip can never be read as an effect and no velocity threshold has to be tuned to tell them apart. Engaging is the only ambiguous moment, and a hold resolves it.

Once engaged:
- **Vertical position drives the primary parameter.** Centre is neutral. Up and down are the two directions of one effect.
- **Release springs back to neutral** over a short glide (~120 ms) so there is no click. Momentary, not latching, for v1. Latch is a later option, not a v1 decision.
- **Horizontal movement is only read after engagement**, if a second parameter is wanted at all. Leave it out of v1.

**The three effects, in order of how forgiving they are:**
| Effect | Node | Thumb drives | Safety rule |
|---|---|---|---|
| Filter sweep | `BiquadFilterNode` | `frequency` | Clamp the range so it never reaches silence. Centre passes the whole band. Cannot sound wrong, only darker or brighter. |
| Synced echo | `DelayNode` + feedback `GainNode` | wet amount; `delayTime` quantised to 1/4, 1/8, 1/16 of the playing track's BPM | Snap to note divisions from `readout.bpm`. Cap feedback below self-oscillation. Let the tail decay on release rather than cutting. |
| Reverb wash | `ConvolverNode` on a send | send `GainNode` | Amount is rarely wrong, only more or less space. Generate the impulse response in code; do not ship an audio file. |

Distortion via `WaveShaperNode` is the easiest to make ugly. Keep it out of v1.

**Feedback while the thumb is down.** The scene already responds to time of day through CSS variables (`--sun-op`, `--sodium-op`, `--star-op`, `--moon-op`). Bend the same variables rather than drawing a new control surface: a lowpass sweep dims and warms the scene, an echo ripples it. That keeps the player looking like itself and needs no new UI furniture. Show the neutral centre line only while engaged.

## Milestones
- **M1.** Filter only, hold-to-engage, vertical drag, spring back on release. Prove no collision with skip on a real phone. Ship behind a flag.
- **M2.** Add synced echo using `readout.bpm`, then the reverb send.
- **M3.** Visual coupling to the existing scene variables.

## Rules
- **Sequence.** There is an open phone playback bug: the player periodically stops and returns to the intro screen with the screen unlocked. That is being investigated separately in the site front-end session and touches the same file. Fix or land that first; do not build effects on top of an unstable player.
- **Test on a real phone**, not a desktop emulator. Thumb reach and touch latency are the whole point.
- **Do not break the `PLAIN` path**, and do not regress the skip gesture. Both are quick to verify by hand.
- **Verify before asserting.** "Works in dev" is not done; it has to work on a phone, held one-handed.

## Evidence trail
`index.html:1045-1060` (audio graph) · `index.html:1560-1570` (swipe) · `library.json` readout.bpm · Koala Sampler manual (filter strip) · Traktor Pro effect reference (filter centre, limiter, clock-locked delay) · Korg Kaoss Pad KP3+ (HOLD, FX RELEASE) · Cross DJ (free vs locked) · Propellerhead Figure (momentary pad)
