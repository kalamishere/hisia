"""Shared coarse genre-family mapping for both sides of the test.

The library side is read from the SA3 prompt the track was generated from;
the real side from Apple's label. Apple's taxonomy is coarse ("Pop",
"Worldwide"), which caps the resolution of any test built on it.
"""
import re

# --- coarse families ------------------------------------------------------
# Both sides get mapped into one vocabulary. The library side is read from the
# prompt it was generated from; the real side from the Apple label. Apple's
# taxonomy is coarse ("Pop", "Worldwide"), which caps how much resolution this
# test can have - noted in the writeup, not papered over.
LIB_RULES = [
    ("afro",          r"amapiano|log-?drum|afro-?beats|afro-?pop|afro-?fusion|highlife|bongo|mbalax|gqom"),
    ("latin",         r"reggaeton|dembow|latin urban|urbano|corrido|banda|mariachi|norteñ|norten|bajo sexto|cumbia|salsa|bachata|funk carioca|sertanej|pagode|forr|baile"),
    ("east-asian-pop", r"k-?pop|j-?pop|mandopop|cantopop|city pop"),
    ("indian",        r"bollywood|filmi|desi|punjabi|bhangra|tamil|telugu"),
    ("arabic",        r"khaleeji|arabic|mahraganat|shaabi|oud "),
    ("dance",         r"house|techno|edm|dance-?pop|club|tech-?house|drum and bass"),
    ("hiphop",        r"hip-?hop|rap|trap|drill|grime"),
    ("reggae",        r"reggae|dancehall"),
    ("rnb",           r"r&b|rnb|soul|neo-?soul"),
    ("country",       r"country|nashville"),
    ("rock",          r"rock|indie|guitar band|punk"),
    ("pop",           r"pop"),
]
APPLE_MAP = {
    # Apple's labels as they actually come back for these charts, collapsed into
    # families a listener would name. Every label observed in the 2026-09-07
    # harvest is covered; anything new falls through to "other" and is excluded
    # from scoring rather than silently counted wrong.
    "Pop": "pop", "Indie Pop": "pop", "Alternative": "pop", "Europe": "pop",
    "Worldwide": "other", "Soundtrack": "other", "Folk": "other",
    "Christian": "other", "Praise & Worship": "other",
    "Afrobeats": "afro", "Afro-Pop": "afro", "Afro-Beat": "afro",
    "Afro-fusion": "afro", "African": "afro", "African Dancehall": "afro",
    "Mbalax": "afro", "Maskandi": "afro", "Amapiano": "afro",
    "Hip-Hop/Rap": "hiphop", "Rap": "hiphop", "Underground Rap": "hiphop",
    "South African Hip-Hop": "hiphop", "Egyptian Hip-Hop": "hiphop",
    "K-Pop": "east-asian-pop", "J-Pop": "east-asian-pop",
    "Mandopop": "east-asian-pop", "Cantopop/HK-Pop": "east-asian-pop",
    "Urbano latino": "latin", "Latin": "latin", "Pop Latino": "latin",
    "Música tropical": "latin", "Música Mexicana": "latin", "Forró": "latin",
    "Arabic Pop": "arabic", "Arabic": "arabic", "Egyptian Pop": "arabic",
    "North African": "arabic",
    "Tamil": "indian", "Telugu": "indian", "Bollywood": "indian",
    "Dance": "dance", "Electronic": "dance", "House": "dance",
    "Reggae": "reggae", "Modern Dancehall": "reggae",
    "R&B/Soul": "rnb", "Rock": "rock", "Hard Rock": "rock",
    "Country": "country",
}

def lib_family(prompt):
    p = prompt.lower()
    for name, rx in LIB_RULES:
        if re.search(rx, p):
            return name
    return "other"

def real_family(label):
    if label is None:
        return None
    return APPLE_MAP.get(label, "other")

