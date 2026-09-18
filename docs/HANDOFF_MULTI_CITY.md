# More than one city per country — simplest path first

Brief written 2026-09-18 from the ideas session. Kalam's calls are recorded below; do not relitigate them.

## Why
India is currently one region keyed `IN`, labelled "Mumbai", fed by YouTube's **national** India chart. A probe on 2026-09-18 (`marathon/design/LOCATION_CHARTS_INDIA.md`, uncommitted, with fixtures) measured 20-entry chart overlap:

| Pair | Shared of 20 |
|---|---|
| Accra vs Ghana (control, reproduces the Aug study) | 19 |
| Mumbai vs India national | 10 |
| Chennai vs India national | 4 |
| Chandigarh vs India national | 4 |
| Indian metro vs metro, mean of 55 pairs | 4.8 |

In Ghana the city *is* the country. In India, the national chart matches no city, **including Mumbai**. So today's card shows a city name over an aggregate nobody listens to. Language tracks the gaps: Chennai is Tamil, Chandigarh Punjabi, Bengaluru Kannada and Telugu, Mumbai the Hindi core.

11 of 12 metros resolve in the location index. **Kochi does not** — the name returns Kochi, Japan; Kochi, Kerala is absent. Malayalam has no city available. Do not spend time on it.

## Kalam's decisions
1. **Order by longitude. Keep same-country cities adjacent.** No country-spacing rule. Four Indian cities playing back to back is fine and honest, since it really is evening across India at that moment.
2. **Simplest way first.** Longitude only. Latitude is not needed: it was only proposed to break ties, and clustered cities are now the desired outcome, not a problem to solve.

## The change, minimally
**The picker currently uses clock time, not geography.** `index.html` scores regions with `eveningness(tz, d)`, which is `localHour(tz)` against `EVENING = 19.5`. Every Indian city shares `Asia/Kolkata`, so they are indistinguishable to it.

India's single timezone is a political convention. The cities span 72.9°E to 88.4°E, over fifteen degrees, which is more than an hour of real solar time. Kolkata's sunset genuinely precedes Mumbai's by about an hour.

So: **score by mean solar time from longitude instead of by the clock.** Local solar hour is `(utcHours + lon/15) mod 24`. One small function; the rest of `eveningness` is unchanged. This spreads the Indian cities by about an hour on its own, needs no latitude, and makes the sun conceit more truthful everywhere, not only in India.

`COORDS` in `index.html` (~line 726) already holds `[lat, lon]` per region and is already used for real sunrise, sunset and moon position. Longitude is there; the picker simply never reads it. New cities need a `COORDS` entry.

## Do one city first
Add **Chennai** only, and ship it. It is the most distinct from the national chart (4/20) and proves every piece of the path with one new idiom to write instead of four: a second region inside one country, a region key that is not an ISO code, a chart pulled via the location route, a new hand-authored idiom, and solar ordering. Once it is live and sounds right, Chandigarh, then one of Bengaluru or Hyderabad (they share 10/20 with each other, so take one, not both), then Kolkata.

## Implementation notes
- **Region keys stop being ISO codes.** Nothing parses the first two characters — checked. Track ids are just `f"{region}-0{k}"` in `step7_library.py`, so any hyphen-free key works. Suggestion: leave Mumbai as `IN` so the existing 8 tracks need no migration, and add new cities as `IN` plus the airport code, e.g. `INMAA` for Chennai, `INIXC` Chandigarh, `INBLR` Bengaluru, `INCCU` Kolkata. Track id reads `INMAA-04`.
- **Touch these in `src/refresh/`:** `config.py` (`CITY`, `PRIORS`, and `LOCATION_REGIONS` — Chennai comes through the location route, the same one Ghana and Cape Verde already use), and `prompts.py` (`IDIOM`).
- **The idiom is human work, not a code change.** Each region carries a hand-authored style head, instrumentation, swing and mix line that Kalam signs off by ear. Write a Tamil film-pop idiom for Chennai and get it signed off before generating a week with it.
- **Location route reference:** `marathon/design/LOCATION_CHARTS.md` has the request shape; `locationParams.region` is `CITY` here. The probe script and fixtures from 18 Sep are in the session scratch directory named in `LOCATION_CHARTS_INDIA.md`.

## Sequencing — read before starting
`index.html` is contended. A thumb-FX session and a phone-playback-bug session are both working in it. **Do the `src/refresh/` side first** (config, idiom, harvest, a generated week for Chennai), which touches none of their files. Take the picker change in `index.html` only once those have landed, and rebase rather than working in parallel on it.

## Generalises
The August "a city is its own country" finding holds where one metro dominates and fails where several do. Indonesia, Brazil and the United States are the same shape as India and are untested. Do not act on that here; note it and move on.
