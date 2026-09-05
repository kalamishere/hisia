# Local zero-shot tagging (LAION-CLAP, 2026-09-05)

## Method (5 lines)

Embedded all 76 published tracks in `radio/audio/` with the LAION-CLAP music checkpoint
(HTSAT-base, `music_audioset_epoch_15_esc_90.14.pt` — same checkpoint as
`audio-brief/clap_worker.py`), middle 10s window, one sequential batch, model loaded once.
Embedded ~80 world-instrument / voice / feel concepts, each written 3 ways, and averaged the
three text vectors per concept (81 concepts / 243 prompts in this run — the script's fixed
vocabulary, unchanged). Scored every (track, concept) pair by cosine, then corpus-centered
each concept (subtract its mean over the 76 tracks, divide by its std) to remove the
per-prompt prior and rank what's unusually strong for *this* track versus the batch.
"Current library tags" for a published track do not exist per-track (these are SA3
generations, not analyzed individually) — the closest analog is the per-region Essentia
readout baked into `library.json` at generation time (`regions.<CC>.readout.instruments` /
`.moods`), shown here once per region.

Full run: `radio/research/zeroshot_tags.py --source published`, 76 tracks, wall time 48s
(32s CPU) on the 8GB machine with `sa3_mlx` idle. A second pass over 27 chart previews
(`--source charts`) ran in 38s and is saved separately as
`radio/research/zeroshot_tags_results_charts.json` for comparison, but is not the priority.

## Per-track comparison

| Track | Region | Current library tags (region readout) | Top-3 centered zero-shot |
|---|---|---|---|
| KE-01 | KE | bass, keyboard, drums; love, happy, deep | defiant swagger (2.05), santoor (1.75), tuba bass (1.73) |
| KE-02 | KE | bass, keyboard, drums; love, happy, deep | santoor (1.41), oud (1.27), ney flute (1.17) |
| KE-03 | KE | bass, keyboard, drums; love, happy, deep | highlife guitar (2.14), mbira thumb piano (2.1), sitar (1.85) |
| KE-04 | KE | bass, keyboard, drums; love, happy, deep | mbira thumb piano (2.0), defiant swagger (1.86), highlife guitar (1.84) |
| AE-01 | AE | bass, drums, percussion; love, deep, energetic | sensual slow groove (1.82), handclaps (1.27), instrumental, no vocals (1.13) |
| AE-02 | AE | bass, drums, percussion; love, deep, energetic | log drum (2.26), sensual slow groove (2.05), 808 sub bass (2.01) |
| AE-03 | AE | bass, drums, percussion; love, deep, energetic | wedding celebration (2.51), string section (2.14), gamelan (2.1) |
| AE-04 | AE | bass, drums, percussion; love, deep, energetic | string section (2.11), cinematic drama (1.65), defiant swagger (1.6) |
| TZ-01 | TZ | percussion, keyboard, bass; love, summer, happy | tuba bass (2.4), log drum (2.03), street party (1.82) |
| TZ-02 | TZ | percussion, keyboard, bass; love, summer, happy | highlife guitar (0.4), tabla (0.09), mariachi trumpet (0.02) |
| TZ-03 | TZ | percussion, keyboard, bass; love, summer, happy | riq tambourine (1.63), afrobeats log-drum kit (1.59), bajo sexto (1.32) |
| TZ-04 | TZ | percussion, keyboard, bass; love, summer, happy | bansuri flute (1.66), mariachi trumpet (1.64), ney flute (1.58) |
| NG-01 | NG | bass, drums, percussion; deep, love, summer | 808 sub bass (1.15), drum machine (0.74), mariachi trumpet (0.55) |
| NG-02 | NG | bass, drums, percussion; deep, love, summer | mariachi trumpet (1.43), live crowd recording (1.32), drum machine (1.23) |
| NG-03 | NG | bass, drums, percussion; deep, love, summer | sitar (1.72), highlife guitar (1.61), funeral / mourning (1.55) |
| NG-04 | NG | bass, drums, percussion; deep, love, summer | steel pan (2.29), mbira thumb piano (2.17), beach and sunshine (2.0) |
| GH-01 | GH | bass, drums, percussion; deep, summer, happy | funk carioca beat (2.5), rapped verse (1.75), conga (1.16) |
| GH-02 | GH | bass, drums, percussion; deep, summer, happy | rapped verse (3.8), oud (3.07), funk carioca beat (2.76) |
| GH-03 | GH | bass, drums, percussion; deep, summer, happy | rapped verse (3.18), funk carioca beat (1.65), dhol (1.29) |
| GH-04 | GH | bass, drums, percussion; deep, summer, happy | funk carioca beat (2.19), rapped verse (2.14), defiant swagger (1.48) |
| UG-01 | UG | percussion, bass, keyboard; love, deep, happy | funk carioca beat (1.15), male lead vocal (0.68), tuba bass (0.6) |
| UG-02 | UG | percussion, bass, keyboard; love, deep, happy | funk carioca beat (1.51), veena (1.51), mridangam (1.38) |
| UG-03 | UG | percussion, bass, keyboard; love, deep, happy | funk carioca beat (0.33), reggaeton dembow (0.15), tuba bass (-0.01) |
| UG-04 | UG | percussion, bass, keyboard; love, deep, happy | rapped verse (1.18), funk carioca beat (0.49), male lead vocal (0.11) |
| ZA-01 | ZA | synthesizer, drums, bass; deep, happy, summer | 808 sub bass (1.54), live crowd recording (1.53), sensual slow groove (1.44) |
| ZA-02 | ZA | synthesizer, drums, bass; deep, happy, summer | sensual slow groove (1.73), drum machine (1.63), afrobeats log-drum kit (1.58) |
| ZA-03 | ZA | synthesizer, drums, bass; deep, happy, summer | handclaps (1.84), santoor (1.64), 808 sub bass (1.61) |
| ZA-04 | ZA | synthesizer, drums, bass; deep, happy, summer | sensual slow groove (1.84), afrobeats log-drum kit (1.72), log drum (1.57) |
| GB-01 | GB | drums, bass, synthesizer; energetic, love, happy | mariachi trumpet (0.73), brass section (0.64), piano (0.61) |
| GB-02 | GB | drums, bass, synthesizer; energetic, love, happy | mariachi trumpet (0.34), brass section (0.31), synthesizer (0.3) |
| GB-03 | GB | drums, bass, synthesizer; energetic, love, happy | piano (1.08), mariachi trumpet (1.05), electric guitar (1.04) |
| GB-04 | GB | drums, bass, synthesizer; energetic, love, happy | electric guitar (1.07), rapped verse (0.79), nostalgic retro (0.73) |
| BR-01 | BR | drums, bass, synthesizer; love, energetic, happy | brass section (2.5), timbales (2.4), bajo sexto (2.34) |
| BR-02 | BR | drums, bass, synthesizer; love, energetic, happy | angklung (2.98), riq tambourine (2.49), marimba loop (2.36) |
| BR-03 | BR | drums, bass, synthesizer; love, energetic, happy | cavaquinho (2.51), requinto guitar (2.13), riq tambourine (2.1) |
| BR-04 | BR | drums, bass, synthesizer; love, energetic, happy | accordion (2.83), harmonium (2.53), timbales (2.28) |
| KR-01 | KR | synthesizer, bass, drums; energetic, happy, love | handclaps (1.79), electric guitar (1.66), group chant (1.5) |
| KR-02 | KR | synthesizer, bass, drums; energetic, happy, love | synthesizer (2.71), talking drum (2.33), steel pan (2.09) |
| KR-03 | KR | synthesizer, bass, drums; energetic, happy, love | synthesizer (2.6), group chant (2.47), electric guitar (2.33) |
| KR-04 | KR | synthesizer, bass, drums; energetic, happy, love | synthesizer (2.51), electric guitar (2.4), spoken adlib (1.86) |
| MX-01 | MX | drums, bass, electricguitar; love, happy, deep | conga (2.13), shekere (1.95), timbales (1.9) |
| MX-02 | MX | drums, bass, electricguitar; love, happy, deep | cuatro (2.76), bajo sexto (2.74), requinto guitar (2.11) |
| MX-03 | MX | drums, bass, electricguitar; love, happy, deep | cuatro (1.45), bajo sexto (1.28), timbales (1.26) |
| MX-04 | MX | drums, bass, electricguitar; love, happy, deep | cavaquinho (2.26), conga (2.23), cuatro (2.14) |
| US-01 | US | guitar, piano, drums; love, happy, energetic | highlife guitar (1.87), marimba loop (1.36), mbira thumb piano (1.34) |
| US-02 | US | guitar, piano, drums; love, happy, energetic | heartbreak lament (1.07), funeral / mourning (0.62), highlife guitar (0.52) |
| US-03 | US | guitar, piano, drums; love, happy, energetic | highlife guitar (0.93), acoustic guitar (0.73), requinto guitar (0.5) |
| US-04 | US | guitar, piano, drums; love, happy, energetic | mbira thumb piano (1.42), highlife guitar (1.35), acoustic guitar (1.21) |
| IN-01 | IN | synthesizer, bass, drums; love, energetic, happy | funeral / mourning (2.16), heartbreak lament (1.98), devotional (1.57) |
| IN-02 | IN | synthesizer, bass, drums; love, energetic, happy | mridangam (3.23), playback vocal (3.07), sarangi (2.82) |
| IN-03 | IN | synthesizer, bass, drums; love, energetic, happy | veena (3.32), playback vocal (2.66), mridangam (2.4) |
| IN-04 | IN | synthesizer, bass, drums; love, energetic, happy | veena (3.33), mridangam (2.99), playback vocal (2.6) |
| ID-01 | ID | drums, synthesizer, bass; love, happy, energetic | ney flute (2.49), bansuri flute (2.09), female lead vocal (1.77) |
| ID-02 | ID | drums, synthesizer, bass; love, happy, energetic | female lead vocal (1.93), angklung (1.92), melisma (1.42) |
| ID-03 | ID | drums, synthesizer, bass; love, happy, energetic | electric guitar (2.51), steel pan (2.4), male lead vocal (2.31) |
| ID-04 | ID | drums, synthesizer, bass; love, happy, energetic | nostalgic retro (1.4), female lead vocal (1.24), ney flute (1.03) |
| CO-01 | CO | drums, bass, synthesizer; love, happy, energetic | tuba bass (1.74), surdo drum (0.68), 808 sub bass (0.48) |
| CO-02 | CO | drums, bass, synthesizer; love, happy, energetic | funeral / mourning (2.04), heartbreak lament (1.77), rural working song (1.21) |
| CO-03 | CO | drums, bass, synthesizer; love, happy, energetic | harmonium (1.34), accordion (0.98), cavaquinho (0.8) |
| CO-04 | CO | drums, bass, synthesizer; love, happy, energetic | conga (0.93), mridangam (0.66), funk carioca beat (0.61) |
| PH-01 | PH | drums, bass, synthesizer; love, energetic, happy | heartbreak lament (2.43), piano (2.42), funeral / mourning (1.99) |
| PH-02 | PH | drums, bass, synthesizer; love, energetic, happy | heartbreak lament (1.84), protest and struggle (1.78), melisma (1.28) |
| PH-03 | PH | drums, bass, synthesizer; love, energetic, happy | devotional (2.94), heartbreak lament (2.58), melisma (2.56) |
| PH-04 | PH | drums, bass, synthesizer; love, energetic, happy | female lead vocal (1.92), protest and struggle (1.8), heartbreak lament (1.65) |
| AU-01 | AU | drums, bass, synthesizer; happy, energetic, love | mariachi trumpet (1.59), bansuri flute (1.32), synthesizer (1.18) |
| AU-02 | AU | drums, bass, synthesizer; happy, energetic, love | string section (1.04), synthesizer (1.02), mariachi trumpet (0.87) |
| AU-03 | AU | drums, bass, synthesizer; happy, energetic, love | synthesizer (1.35), string section (1.3), acoustic guitar (1.2) |
| AU-04 | AU | drums, bass, synthesizer; happy, energetic, love | duet (1.82), children's playful (1.71), male lead vocal (1.71) |
| NZ-01 | NZ | drums, bass, keyboard; happy, energetic, love | piano (1.05), brass section (0.91), saxophone (0.83) |
| NZ-02 | NZ | drums, bass, keyboard; happy, energetic, love | mariachi trumpet (1.08), piano (0.85), harmonium (0.79) |
| NZ-03 | NZ | drums, bass, keyboard; happy, energetic, love | male lead vocal (1.67), call-and-response chorus (1.44), duet (1.4) |
| NZ-04 | NZ | drums, bass, keyboard; happy, energetic, love | children's playful (2.02), ney flute (1.39), saxophone (1.26) |
| CV-01 | CV | percussion, bass, drums; love, deep, summer | dholak (1.69), tabla (1.54), pandeiro (1.41) |
| CV-02 | CV | percussion, bass, drums; love, deep, summer | cuatro (1.78), dholak (1.38), duet (1.27) |
| CV-03 | CV | percussion, bass, drums; love, deep, summer | rural working song (2.04), cuatro (1.88), male lead vocal (1.73) |
| CV-04 | CV | percussion, bass, drums; love, deep, summer | saxophone (2.81), harmonium (2.59), brass section (2.56) |

## Assessment (10 lines, honest)

The centered ranking does surface words the Essentia heads structurally cannot: dholak,
tabla, mridangam, sarangi, veena, sitar, oud, qanun, kora, mbira, cuatro, bajo sexto, cavaquinho
— all real 80-concept vocabulary entries this stack has zero labels for today. The IN region is
the strongest evidence it's finding something real: all 4 India tracks land on a tight,
internally consistent South Asian cluster (veena/mridangam/sarangi/tabla/sitar) with no BR/MX/AR
noise leaking in — that's a genuine signal Essentia's 40-label instrument model cannot produce.
MX is similarly coherent (cuatro, bajo sexto, requinto guitar, timbales, cavaquinho across all
4 tracks). Those two regions look right and are worth trusting.

Elsewhere it looks wrong more often than right. Three labels — "mariachi trumpet" (13/76),
"funk carioca beat" (11/76), "tuba bass" (10/76) — dominate the centered top-5 across regions
that have nothing to do with mariachi or Brazilian funk (KE, GH, UG, AE, AU, GB all pull one of
these), which reads as generic "syncopated brass/bass" attractors surviving the centering rather
than real detections — these three should probably be dropped or down-weighted. KE-01 pairing
Kenyan afro-pop with santoor+oud+tuba-bass is a clear miss; CV (Cape Verde, morna/cavaquinho
country) scatters across dholak/tabla/cuatro/saxophone/harmonium with no coherent theme, which is
suspicious given how small and specific Cape Verdean instrumentation actually is. My working read:
trust the centered list only when 3-4 tracks from the same region converge on the same instrument
family (IN, MX are the clean cases); treat a single-track, single-concept spike as noise until a
person confirms it by ear — this needs a human listening pass before any tag gets written back to
`library.json`.
