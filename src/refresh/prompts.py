"""Per-region prompt writing.

The 2026-08-24 prompts in radio/build/prompts.json were hand-authored (an LLM
pass over each region's readout, kept because Kalam signed them off by ear).
There is no script in radio/build that wrote them, so the weekly command cannot
"reuse the step code" here. What it does instead, stated plainly:

  * the REGION IDIOM (style head, instrumentation vocabulary, swing/mix line,
    Suno style + vocal line) is lifted verbatim from those signed-off prompts
    and frozen in IDIOM below - it is the part a week's chart does not change;
  * the MEASURED PART (BPM, mode, mood adjectives, the instruments Essentia
    actually heard, the genre-family line) is rebuilt from this week's readout;
  * `--prompts keep` reuses the previous library's prompt text verbatim, and
    the run prints a diff of the measured part so a human can decide.

So a weekly refresh is honest about numbers without inventing new regional
language on its own. Replacing IDIOM with a fresh LLM pass is a one-file change.
"""
from __future__ import annotations

# style head | instrumentation | swing/mix line | suno style | suno instruments | suno vocal
IDIOM = {
    "KE": ("East African afro-pop instrumental",
           "live log-drum and shaker percussion, warm sliding bass, bright plucked guitar riff, soft synth pads",
           "mid-tempo dancehall-zouk swing",
           "afro-pop, bongo flava, dancehall-zouk swing, tropical house sheen",
           "log drum, shakers, sliding bass, plucked guitar, synth pads",
           "male lead, Swahili hook, call-and-response backing vocals"),
    "AE": ("Mid-tempo Gulf-chart pop instrumental",
           "reggaeton-leaning drum groove, deep sub bass, trap hi-hat rolls, ornamented string and reed melody",
           "cinematic and emotional, glossy modern mix",
           "South-Asian film-pop meets Arabic urban pop, reggaeton/trap drum programming",
           "sub bass, trap hats, percussion, synth, ornamented strings/reeds",
           "melismatic lead with microtonal ornament; a Hindi-pop hook or an Arabic rap verse both fit"),
    "TZ": ("Bongo flava instrumental",
           "driving conga and shaker percussion, punchy kick, melodic sliding bass, bright electric guitar arpeggio, warm keys",
           "loud glossy mix, summer dance groove",
           "bongo flava, afro-pop, zouk-inflected, singeli-adjacent energy",
           "congas, shakers, punchy kick, sliding bass, bright guitar arpeggio, warm keys",
           "duet male/female, Swahili lead, big singalong chorus"),
    "NG": ("Nigerian afrobeats instrumental",
           "loose log-drum and shaker groove, rolling sub bass, muted guitar plucks, soft electric-piano chords, airy synth pads",
           "mid-tempo street-pop swing",
           "afrobeats, Lagos street-pop, afro-fusion",
           "log drum, shakers, sub bass, muted guitar plucks, electric piano, airy pads",
           "male lead, Nigerian-English and pidgin phrasing, relaxed melodic flow, layered ad-libs"),
    "GH": ("Ghanaian afrobeats and rap instrumental",
           "swung kick-and-clap pattern, hand percussion and shaker, deep round bass, bright piano stabs, sparse guitar licks",
           "spacious sunny mix",
           "Ghanaian afrobeats, hiplife-leaning rap, highlife guitar colour",
           "swung kicks and claps, hand percussion, round bass, piano stabs, clean guitar licks",
           "rap verses in Ghanaian English and Twi phrasing over a sung hook, crew backing shouts"),
    "UG": ("Ugandan afro-fusion instrumental",
           "fast hand-drum and shaker patterns, bouncing bass, bright single-coil guitar riff, warm organ keys",
           "up-tempo dance lilt",
           "Ugandan afro-fusion, afro-pop, kadongo-kamu-flavoured dance",
           "hand drums, shakers, bouncing bass, bright guitar riff, organ keys",
           "male lead in Luganda with English lines, call-and-response chorus, crowd shouts"),
    "ZA": ("Amapiano instrumental",
           "deep log-drum bassline, shuffled shaker and rimshot percussion, soft piano chords, wide warm pads",
           "quiet spacious mix with long tails, late-night groove",
           "amapiano, South African dance",
           "log drum, shakers, rimshots, soft piano chords, wide pads",
           "sparse chanted vocal in isiZulu and Sepedi phrasing, half-sung ad-libs"),
    "GB": ("UK chart pop instrumental",
           "four-on-the-floor drums with clap backbeat, driving synth bass, bright supersaw chords, chopped electric guitar",
           "big polished chorus lift",
           "UK chart pop with K-pop crossover sheen, dance-pop",
           "four-on-the-floor kit, claps, synth bass, supersaw chords, chopped electric guitar",
           "group vocal, English hook sung in unison then split into harmony"),
    "BR": ("Brazilian sertanejo and funk instrumental",
           "tight snare and tamborim groove, punchy kick, sliding bass, accordion-coloured keys and steel-string acoustic guitar",
           "festive arena energy",
           "sertanejo universitario meets funk paulista",
           "tamborim and snare, punchy kick, sliding bass, accordion-coloured keys, steel-string acoustic guitar",
           "male duet in Brazilian Portuguese, singalong chorus"),
    "KR": ("K-pop instrumental",
           "hard programmed drums, distorted synth bass, bright arpeggiated synths, crunchy electric guitar stabs",
           "loud glossy mix with a big drop",
           "K-pop, dance-pop with a hip-hop spine",
           "hard programmed drums, distorted synth bass, arpeggiated synths, electric guitar stabs",
           "group vocal, romanised Korean hook with English lines, rap verse into a chanted drop"),
    "MX": ("Mexican regional instrumental, norteno and corridos tumbados",
           "bajo sexto and nylon-string requinto lines, tuba and sousaphone bass walking under the beat, snare and tambora shuffle, accordion swells",
           "close warm mix",
           "musica mexicana - norteno-banda ballad crossed with corridos tumbados",
           "bajo sexto, nylon-string requinto, tuba bass, tambora and snare shuffle, accordion",
           "male lead in Spanish, plain-spoken verse into a wide two-part harmony chorus"),
    "US": ("US chart instrumental, country-pop with a hip-hop backbeat",
           "strummed acoustic guitar and slide electric, upright-feel bass, laid-back kit with rim clicks and finger snaps, warm piano pads",
           "roomy radio mix",
           "contemporary country-pop meeting melodic hip-hop",
           "strummed acoustic guitar, slide electric, warm bass, laid-back kit with snaps, piano pads",
           "mixed male and female lead in English, conversational verse, big singalong chorus"),
    "IN": ("Indian film pop instrumental",
           "dholak and tabla layered under a programmed kit, plucked sitar and santoor figures, sub-heavy synth bass, sweeping string pad",
           "bright cinematic mix",
           "Bollywood film pop with an Indian-pop electronic underlay",
           "dholak and tabla, programmed kit, sitar and santoor plucks, synth bass, string pad",
           "female lead in romanised Hindi with a male answering line, long held notes"),
    "ID": ("Indonesian pop instrumental",
           "clean electric guitar arpeggios, round synth bass, crisp programmed kit with handclaps, glassy keyboard chords, airy pads",
           "bright uncluttered mix",
           "Indonesian pop with a K-pop-leaning gloss",
           "clean electric guitar arpeggios, synth bass, programmed kit with claps, glassy keys, airy pads",
           "soft male lead in Bahasa Indonesia, breathy verse, group-sung chorus"),
    "PT": ("Portuguese pop instrumental",
           "kizomba-leaning drum groove, soft sub bass, nylon-string guitar picking, warm electric piano, light shaker",
           "smooth late-summer sway",
           "Portuguese pop, afro-pop with kizomba swing, Lisbon-Luanda crossover",
           "kizomba drums, sub bass, nylon guitar, electric piano, shaker",
           "male lead in Portuguese, intimate delivery, a gentle sung hook"),
    "EG": ("Egyptian pop instrumental",
           "mahraganat-style drum programming, deep 808 bass, ornamented oud and string lines, hand percussion, bright synth stabs",
           "punchy street-pop energy, glossy mix",
           "Egyptian pop, Arabic urban pop, mahraganat drums, shaabi flavour",
           "808 bass, mahraganat drums, oud, strings, hand percussion, synth stabs",
           "male lead in Egyptian Arabic, melismatic hook, chanted backing"),
    "AR": ("Argentine urban pop instrumental",
           "reggaeton dembow drums, round sub bass, plucked synth melody, soft pad chords, light guitar",
           "mid-tempo urbano sway, warm club mix",
           "urbano latino, Argentine trap-pop, cumbia-tinged reggaeton",
           "dembow drums, sub bass, plucked synth, pads, guitar",
           "male lead in Rioplatense Spanish, melodic flow, sung hook"),
    "CO": ("Colombian pop instrumental",
           "regional-Mexican-influenced groove with tuba-like bass, requinto guitar runs, accordion colour, soft percussion",
           "sentimental mid-tempo sway",
           "musica mexicana as heard in Colombia, pop latino, reggaeton undertow",
           "bass, requinto guitar, accordion, soft percussion, pads",
           "male lead in Spanish, heartfelt delivery, harmonised chorus"),
    "PH": ("Filipino pop instrumental",
           "clean drum kit groove, warm bass, jangly electric guitar, soft piano, wide pads",
           "earnest indie-pop lift, big-chorus dynamics",
           "OPM pop, indie pop, hip-hop-inflected pop ballad",
           "drum kit, bass, jangly guitar, piano, pads",
           "soaring male or female lead in Tagalog and English, anthemic chorus"),
    "AU": ("Australian chart pop instrumental",
           "crisp pop drums, deep bass, bright synth hooks, acoustic guitar strum, country-pop lilt in the verses",
           "sunny festival-pop energy",
           "chart pop, country-pop, K-pop-styled girl-group pop",
           "pop drums, bass, synth hooks, acoustic guitar",
           "confident female lead, big harmonised chorus"),
    "NZ": ("New Zealand chart pop instrumental",
           "crisp pop drums, deep bass, bright synth hooks, acoustic guitar strum, a touch of country-pop swing",
           "open-air summer-pop energy",
           "chart pop, country-pop, girl-group pop, hip-hop crossover",
           "pop drums, bass, synth hooks, acoustic guitar",
           "warm lead vocal, layered harmonies, singalong chorus"),
    "CV": ("Cape Verdean dance instrumental",
           "funana-style accordion riffs, fast ferro-scraper percussion, bouncing bass, kizomba-zouk drum groove, bright guitar",
           "joyful island dance energy",
           "funana, kizomba, zouk, Cape Verdean dance-pop",
           "accordion, ferro scraper, bass, zouk drums, guitar",
           "male lead in Kriolu, call-and-response chorus"),
}

# Essentia mood-theme tags -> prompt adjectives
MOOD_WORD = {
    "love": "romantic", "happy": "joyful", "deep": "deep", "summer": "sunny",
    "energetic": "energetic", "sad": "wistful", "film": "cinematic",
    "relaxing": "easy", "dark": "dark", "party": "festive", "epic": "big",
    "meditative": "hypnotic", "cool": "cool", "motivational": "driving",
    "dream": "dreamy", "funny": "playful", "holiday": "sunlit",
    "groovy": "groovy", "advertising": "bright", "ballad": "tender",
    "background": "spacious", "calm": "calm", "children": "playful",
    "christmas": "festive", "corporate": "clean", "documentary": "plain",
    "drama": "dramatic", "emotional": "emotional", "melodic": "melodic",
    "powerful": "powerful", "retro": "retro", "sexy": "sultry", "slow": "slow",
    "soft": "soft", "space": "wide", "sport": "driving", "travel": "wide-open",
    "upbeat": "upbeat", "hopeful": "hopeful", "inspiring": "uplifting",
}
# Essentia instrument tags -> a phrase that reads as a music prompt
INSTR_WORD = {
    "bass": "bass well forward", "drums": "a prominent kit",
    "percussion": "layered hand percussion", "keyboard": "keyboard chords",
    "synthesizer": "synth-led textures", "piano": "piano",
    "guitar": "acoustic guitar", "electricguitar": "electric guitar",
    "acousticguitar": "acoustic guitar", "voice": "vocal-shaped lead lines",
    "strings": "strings", "violin": "strings", "flute": "flute",
    "trumpet": "brass", "saxophone": "saxophone", "organ": "organ",
    "computer": "programmed production", "brass": "brass",
    "harmonica": "harmonica", "cello": "cello", "clarinet": "reeds",
    "doublebass": "upright bass", "horn": "horns", "pipeorgan": "organ",
    "trombone": "brass", "viola": "strings", "bell": "bells",
    "orchestra": "orchestral bed", "drummachine": "drum machine",
}


def _moods(readout, n=3):
    tags = list(readout.get("mean_mood_vector", {}))[:n]
    return [MOOD_WORD.get(t, t) for t in tags]


def _instruments(readout, n=3):
    tags = list(readout.get("mean_instrument_vector", {}))[:n]
    return [INSTR_WORD.get(t, t) for t in tags]


def build(region: str, readout: dict, genre_family: str) -> dict:
    head, instr, swing, s_style, s_instr, s_vocal = IDIOM[region]
    bpm = int(round(readout["bpm_median"]))
    mode = readout["dominant_mode"]
    moods = _moods(readout)
    heard = _instruments(readout)
    mood_line = ", ".join(moods[:-1]) + (" and " + moods[-1] if len(moods) > 1 else "")
    heard_line = ", ".join(heard[:-1]) + (" and " + heard[-1] if len(heard) > 1 else "")
    sa3 = (f"{head}, {bpm} BPM, {mode} key, {instr}, {swing}, "
           f"{heard_line} carrying the arrangement, {mood_line}")
    suno = (f"[style: {s_style}] [tempo: {bpm} BPM] [mood: {', '.join(moods)}] "
            f"[instruments: {s_instr}] [vocal: {s_vocal}]")
    return {"sa3_prompt": sa3, "suno_prompt": suno,
            "_measured": {"bpm": bpm, "mode": mode, "moods": moods,
                          "instruments": heard, "genre_family": genre_family}}
