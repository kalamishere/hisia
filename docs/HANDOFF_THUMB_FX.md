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

## Changed on contact with a phone (2026-09-17, M1)
- **The hold starts in the sky, not the bottom arc.** The arc came from one-thumb reach, and on a real phone that reasoning does not survive: the bottom half is card text and controls with barely a gap to press, Kalam's phone is small, and people reach in with an index finger rather than the holding thumb. `&zone=sky|arc|all` switches it while that is being felt out; sky is the default and the switch goes once it is settled. Hold-to-engage itself is unaffected — it was never about reach, it was about not being a swipe.
- **The card is in bounds.** Excluding it left a 55px sliver between the honest line and the controls that nobody could find.
- **Safari's press-to-select is off under the flag.** A 180ms press on text starts a selection and callout, which cancels the pointer stream mid-hold. The prompt box keeps its selection.

## The diamond (Kalam, 2026-09-17) — supersedes the single axis
Four effects at the corners of a diamond, each reaching 100% at its corner and blending between corners; the centre is dry. Kalam's design, after trying M1 on the phone.

- **Geometry.** Clamp the thumb's offset from the anchor to `|x| + |y| <= 1` (scale both by `1/(|x|+|y|)` outside it). Each corner's amount is then just its side of the axis: `up = max(0, y)`, `down = max(0, -y)`, and the same for left/right. A corner gives one effect at 100%, an edge gives two summing to 100%, the centre gives none. Left and right are mutually exclusive by construction, and so are up and down — that is what "transitions between each corner" means.
- **What Curate actually has (screenshot from Kalam, 2026-09-17).** Six knobs: Volume, Low/High Pass, Time Stretch (pinch), Reverb (stretch), Roll (two finger up/down), Echo. Plus `LOCK: OFF` and `RESET`. So the "glitch that sounded like it was slowing down and repeating" is two controls, Time Stretch and Roll, and Echo is its own. This is the app, not the decks — the research finding that the **decks** do not contain this design still stands.
- **Corners.** N highpass, S lowpass, E reverb wash, W echo travelling into roll. The filter's two directions are already opposites, so they want to be one axis, and this uses exactly the three effects in the table below with no fourth. Distortion stays out for the reason given there.
- **Reach.** An XY pad was ranked third in the survey on thumb reach. That objection is gone: see the note above on the index finger.
- **Built 2026-09-17, behind `?fx=1`.** Geometry, gesture and all four corners are wired: `BiquadFilter` pair in line for N/S, a `DelayNode` with capped feedback on a wet send for W, a `ConvolverNode` with an impulse generated in code for E. Echo snaps to an eighth note of the playing track's `readout.bpm` (present on all 340). The shape and the readout can be judged on the phone; the sound only on a desktop, until PLAIN is settled.
- **Six knobs into four corners.** Low/High Pass is already one bipolar knob and maps onto N/S exactly. Reverb takes E. Volume the player already has. That leaves Echo and Roll wanting the same corner, so the corner travels through one into the other: an echo behind the music for the first third of the way, then it collapses into a roll — slice shortening onto the grid, feedback winding up, dry ducking away, tape slowing under it. Nothing is dropped.
- **The surface is a tesseract, and it turns (Kalam, 2026-09-17).** He sent a picture of one held in two hands — nested, translucent — and said "it moved with your thumb". So: an outer cell that never moves, because it is the clamp and the four effects sit on its vertices, and an inner cell that leans the way you push, twists as it leans and falls away in perspective, with struts following it out to the vertices. The inner cell also earns its keep functionally: inside it everything is dry, and the ramp starts from its edge, so dry is somewhere you can rest instead of a single point you cannot hold still on.
- **`preservesPitch` has to be off, or the slowing is not slowing.** It defaults to true, so `playbackRate < 1` time-stretches to hold the pitch instead of slowing the tape, and that algorithm granulates. On the phone, where the slowing is all the west corner does, Kalam heard it as stuttering and asked what it was mixing with — nothing; it was the browser's own time-stretcher. Turn off `preservesPitch` / `webkitPreservesPitch` and it becomes a tape stop.
- **A roll has to close its input.** The first version kept feeding the delay while the feedback climbed, which layers echoes rather than looping a slice — mush, not a roll. The delay now has an input gain that ducks to 15% as the roll deepens, so it closes its mouth on what it has and circles it.
- **The three things on the west corner are staged, not piled.** Echo to 35% of the travel, roll from there to 80%, and the tape only gives way over the last fifth. Kalam on desktop: "west is creating stutters as an effect which doesn't always sound nice — is it mixing with something else". It was: delay, feedback, dry duck and tape slow all rose together. Curate keeps Roll and Time Stretch on separate knobs; this keeps them on one corner but not at the same moment.
- **Latch is now a real question, not a later one.** Curate ships `LOCK: OFF`, so latching is a mode that app thought worth having. v1 is still momentary; this is the first evidence for the other side.
- **Curate uses a gesture per parameter** (pinch, stretch, two-finger) rather than one pad. The diamond is a different answer to the same problem, not a copy of theirs.
- **Blocked on PLAIN.** A four-corner blend is nothing but sound, and there is no audio graph on an iPhone to make it with. `src/probes/ios-audio.html` measures whether that is still true before anything is rebuilt around it.

## PLAIN can go (Kalam's ear, 2026-09-17, `src/probes/ios-audio.html`)
Measured on Kalam's iPhone, by ear with the screen off:
- **B — a Web Audio graph does not survive the screen lock.** It goes silent while locked and the music comes back on unlock, on its own. No `resume()` needed, so test D never applied.
- **C — the handoff does survive.** Handing playback to a second bare `<audio>` at the same position on the way into the lock, and back to the graph on the way out, **kept playing through the lock**.

So the sentence at `index.html:1012` that took iPhones off the graph entirely is true only of the locked state, and the locked state is exactly when nobody is touching an effect. The shape that follows: **graph while `visibilityState` is visible, plain element while hidden.** Two elements per player instead of one, four in all, with a swap at every visibility change.

- **A — `el.volume` does nothing on iOS.** Kalam's ear: no change across a 1 → 0.15 → 1 ramp. The 7 Sep comment was right, `rampVolume` is a no-op on the phone, and nothing on the plain side can fade. `muted` is a separate flag and does work, which is what the twin below leans on.
- **C dips at both handovers.** It seeks a cold element and starts it, then pauses the live one before the cold one is making sound — a gap by construction. Test **E** replaces it: the second element plays the whole time, muted and kept in step, so the handover is a mute toggle with nothing to start. Test **CTL** is the control that has to run first — if a bare element dips at the lock too, the dip is iOS and the handoff is innocent.

Not yet known: the first log came back with the media clock frozen at 18.0s for five minutes while the element reported not-paused — a stall, not playback — and the head that would have said which test it belonged to had scrolled off a 300-line cap. So no numbers from that run are usable. The probe now tags every line with the test and the element, says STALLED out loud, collapses repeats and keeps 2000 lines. One thing that run did show and nothing yet explains: the page went hidden and visible in pairs every ~6 seconds, unprompted, for four minutes. Worth handing to whoever has the restart bug.

**Sequencing.** This is surgery on the playback core while the restart bug is still unexplained, and it adds a second way for playback to stop. The bug lands first.

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
