# A player at the bottom of cities.html

Brief written 2026-09-20 from the ideas session. Small job. Keep it small.

## The ask
`cities.html` is the directory page: 63 city sections, each with a genre and tempo line, the prompt the music was generated from, and four invented track titles. It describes music you cannot hear. Put a web player at the bottom of it.

## The shape
One `<audio>` element in a bar pinned to the bottom of the page, plus a play control on each city section that points the bar at that city's tracks.

That is the whole feature. Reading about Chennai and pressing play on Chennai is the point.

- **Sticky bar**, always visible while scrolling. Shows the city, the invented track title, a play and pause control, and a link through to the full radio at `/`.
- **Per-section control.** Each `<section id="...">` gets a button that loads that city's four tracks into the bar and starts the first. Playing to the end of a city's four moves to the next city down the page, which is the reading order people are already in.
- **Deep links.** The page already has ids per city (`#INMAA`, `#TZ`). If a URL arrives with one, scroll to it and cue it without autoplaying. Autoplay is blocked on mobile anyway and is rude on a text page.

## Do not rebuild the radio
`index.html` holds the real player: a Web Audio graph, the sun sequencing, drift mode, the visual scene. **None of that belongs here.** Use a plain `<audio>` element with `src` set to the mp3 path. No `AudioContext`, no library-wide sequencing, no scene. If someone wants the radio they click through.

Track file paths come from `library.json`, which carries a `file` per track. The page currently emits no paths at all, so whatever generates it has to start including them.

## Find the generator first
**`cities.html` is not hand-written and is not produced by `src/publish.sh`** — that only rsyncs `index.html` and `library.json`. Nothing in `src/` or `docs/` mentions `cities.html` by name, yet its content tracks the current library, including the Chennai and Chandigarh sections added this week.

So something regenerates it, most likely under `/Users/kalam/ableton-v1` in one of the radio worktrees. **Find that generator and add the player there.** If you edit `cities.html` directly, the next regeneration silently deletes your work. If you genuinely cannot find a generator, say so in your report and only then edit the file, and say clearly in the commit that it may be overwritten.

## Constraints
- **Keep it accessible.** Real `<button>` elements, a visible focus state, and the bar must not cover the last section's text. It is a page people read.
- **Degrade quietly.** No JavaScript or a missing mp3 means the page reads exactly as it does today. The bar should not appear at all rather than appear broken.
- **Mobile.** The bar is the one thing always on screen on a phone, so keep it one line tall and keep the controls inside thumb reach.
- **No new dependencies.** No audio library, no framework.

## Sequencing
`index.html` is contended: a thumb-FX session and a playback-bug session are both in it, and a third is adding Indian cities. **This job must not touch `index.html`.** If you believe it needs to, stop and report instead.
