"""Fictional, region-flavoured artist + track names.

Same shape as the hand-authored radio/build_public/names_public.json (place or
person word + a collective noun; a title in the region's language). Those 56
names were written by an LLM pass; this module makes the weekly run
reproducible without one: a per-region lexicon (carried from that set's own
vocabulary and Kalam's sign-off), combined deterministically from a seed of
week + region + slot, then filtered through the same real-name rule
radio/check_names.py enforces, re-drawing until nothing overlaps this week's
chart. If every draw collides the run FAILS rather than shipping a near-miss.

Nothing here is a real artist or title; the collision filter is what proves it.
"""
from __future__ import annotations

import random, re, unicodedata

COLLECTIVE = [
    "Sound", "Tape Club", "Night Bus", "Collective", "Radio", "Union",
    "Society", "Sessions", "Band", "Choir", "Set", "Institute", "Circuit",
    "Cassette", "Skyline", "Yard Sessions", "Trio", "Lamplight", "Rooftop Crew",
]

# place words (fictional-safe: neighbourhoods and landmarks, never artists)
PLACES = {
    "KE": ["Kesho Matatu", "Mwangaza", "Ngong Road", "Boda Sunrise", "Kilimani",
           "Uhuru Park", "Riverside Stage", "Jioni"],
    "AE": ["Nakheel", "Bahr Al Fajr", "Marina Kamanjah", "Al Manara", "Deira Corniche",
           "Jumeirah Dusk", "Qamar Lane", "Khor Dubai"],
    "TZ": ["Kigamboni", "Zuhura Beach", "Mzee Ferry", "Salamu Coastline", "Msasani",
           "Pwani Yangu", "Bahari Kuu", "Kariakoo"],
    "NG": ["Ikoyi Lamplight", "Adaeze Night Market", "Third Mainland", "Bariga Palmwine",
           "Yaba Sunrise", "Lekki Tollgate", "Surulere", "Harmattan"],
    "GH": ["Osu Beach", "Adjoa Highlife", "Labadi", "Kokrobite", "Jamestown",
           "Chalewote", "Trotro Weekend", "Accra Newtown"],
    "UG": ["Kabalagala", "Nakasero", "Ggaba Lakeside", "Bodaboda Skyline", "Kololo",
           "Entebbe Road", "Munange", "Nakawa"],
    "ZA": ["Maboneng", "Soweto Piano", "Thandeka Yard", "Kasi Midnight", "Braamfontein",
           "Yeoville Rooftop", "Alex Corner", "Vilakazi"],
    "GB": ["Peckham Neon", "Silvertown Disco", "Camberwell", "Hackney Sunrise",
           "New Cross", "Deptford Bridge", "Tottenham Marshes", "Elephant Arcade"],
    "BR": ["Beira do Rio", "Sertao Neon", "Vila Madalena", "Faroleiros",
           "Praia Grande", "Estrada Velha", "Poeira Azul", "Boiadeiro"],
    "KR": ["Mapo Night", "Hongdae Glass", "Seorae Pixel", "Han River Youth",
           "Euljiro Basement", "Sinchon Arcade", "Yeonnam", "Neon Sonyeo"],
    "MX": ["Los Faroles de Tepito", "Cielo Chilango", "Xochimilco Requinto",
           "Hermanas Tolvanera", "Coyoacan", "Metrobus Nocturno", "Tianguis", "Iztapalapa"],
    "US": ["Ridgeline Highway", "Palmdale Pickup", "Marisol Canyon", "Eastside Porchlight",
           "Two Lane", "Tailgate County", "Sunset Truckstop", "Dustbowl Avenue"],
    "IN": ["Bandra Filmi", "Andheri Rickshaw", "Juhu Monsoon", "Colaba Dhol",
           "Dadar Terminus", "Marine Drive", "Chhat Pe", "Worli Seaface"],
    "ID": ["Blok M Senja", "Kembang Api", "Ancol Beach Pop", "Sari Gudang",
           "Bundaran Malam", "Kota Tua", "Angkot Sore", "Menteng Hujan"],
    "PT": ["Alfama", "Bairro Alto", "Cais do Sodré", "Tejo", "Graça", "Mouraria", "Belém", "Miradouro"],
    "EG": ["Zamalek", "Nile Corniche", "Heliopolis", "Mokattam", "Maadi", "Khan Sunset", "Dokki", "Garden City"],
    "AR": ["Palermo", "La Boca", "Costanera", "San Telmo", "Villa Crespo", "Río Plateado", "Chacarita", "Recoleta"],
    "CO": ["Chapinero", "La Candelaria", "Usaquén", "Monserrate", "Teusaquillo", "Cerros", "Sabana", "Zona Rosa"],
    "PH": ["Malate", "Intramuros", "Roxas Boulevard", "Quiapo", "Poblacion", "Baywalk", "Cubao", "Marikina"],
    "AU": ["Newtown", "Bondi Dusk", "Surry Hills", "Harbour Line", "Marrickville", "Coogee", "Redfern", "Parramatta"],
    "NZ": ["Ponsonby", "Karangahape", "Waiheke", "Grey Lynn", "Piha", "Mt Eden", "Harbour Bridge", "Kingsland"],
    "CV": ["Praia Sunset", "Plateau", "Tarrafal", "Mindelo", "Sal Rei", "Ribeira Grande", "Achada", "Cidade Velha"],
}

# title halves in the region's own language / register
TITLE_A = {
    "KE": ["Barabara ya", "Usiku wa", "Taa za", "Moyo", "Safari ya", "Wimbo wa"],
    "AE": ["Layali", "Ghiyab Al", "Sahra", "Nujoom", "Hawa Al", "Tariq Al"],
    "TZ": ["Pwani", "Kimya Cha", "Densi la", "Rangi za", "Upepo wa", "Bahari ya"],
    "NG": ["Slow Motion", "Owambe", "Sunlight for", "Carry Me", "Palmwine", "Lagos"],
    "GH": ["Trotro", "Chalewote", "Gari and", "Nsuo", "Highlife", "Sunshine"],
    "UG": ["Munange", "Emmwanyi", "Tuli Wamu", "Omukwano", "Ekyalo", "Lubwa"],
    "ZA": ["Sunday", "Amanzi", "Groove Ya", "Phola", "Izolo", "Umoya"],
    "GB": ["Nightbus", "Glass", "Two Left", "Static in the", "Late", "Corner Shop"],
    "BR": ["Saudade de", "Poeira e", "Moda de", "Chorando na", "Beira da", "Festa no"],
    "KR": ["Neon", "Danger Signal", "Bballi Bballi", "Frozen Peach", "Midnight", "Paper"],
    "MX": ["Corazon de", "Noche de", "Ya No Me", "Cumbia del", "Carretera de", "Luna de"],
    "US": ["Dust on the", "Cheap Beer", "Two Lane", "Runnin' Late", "Back Road", "Porch Light"],
    "IN": ["Chhat Pe", "Dil Ka", "Sapne Wali", "Roshni Ki", "Baarish Mein", "Raat Ka"],
    "ID": ["Malam Jakarta", "Rindu", "Sore di", "Terang Sekali", "Hujan di", "Langit"],
    "PT": ["Noite de", "Luz do", "Rua da", "Maré", "Verão em", "Coração de"],
    "EG": ["Leil El", "Nour El", "Shari' El", "Qamar", "Seif Fi", "Alb El"],
    "AR": ["Noche de", "Luz de", "Calle", "Verano en", "Corazón de", "Baile en"],
    "CO": ["Noche en", "Luz de", "Calle", "Tarde en", "Corazón", "Sabor de"],
    "PH": ["Gabi ng", "Liwanag ng", "Kanto ng", "Tag-init sa", "Puso ng", "Sayaw sa"],
    "AU": ["Night on", "Light off", "Down the", "Summer at", "Heart of", "Dancing at"],
    "NZ": ["Night at", "Light on", "Along the", "Summer in", "Heart of", "Dance at"],
    "CV": ["Noti di", "Lus di", "Rua di", "Verão na", "Korason di", "Baile na"],
}
TITLE_B = {
    "KE": ["Jioni", "Bati", "Ngong", "Mzito", "Asubuhi", "Mvua"],
    "AE": ["Zarqa", "Qamar", "Tawila", "Sagheera", "Bahriya", "Hadi"],
    "TZ": ["Yangu Tulivu", "Bahari", "Mchana", "za Asubuhi", "wa Kusini", "Tamu"],
    "NG": ["Harmattan", "Blue", "Two", "Softly", "Weekend", "Sunrise"],
    "GH": ["Weekend", "Rhythm", "Sunshine", "Ba", "Morning", "Corner"],
    "UG": ["Twala", "Sunrise", "Leero", "Gwaffe", "Ekiro", "Wange"],
    "ZA": ["Yanos", "Amnandi", "Sekusile", "Nathi", "Kwedini", "Wethu"],
    "GB": ["Chorus", "Arcade", "Trainers", "Rain", "Again", "Blues"],
    "BR": ["Segunda", "Cerveja", "Viola Nova", "Estrada", "Manha", "Interior"],
    "KR": ["Sonyeo", "Blue", "Heart", "Soda", "Arcade", "Letter"],
    "MX": ["Tianguis", "Neon Azul", "Buscas", "Metrobus", "Noche", "Barrio"],
    "US": ["Tailgate", "Sunrise", "Sunday", "Again", "Home", "County Line"],
    "IN": ["Chandni", "Mausam", "Gaadi", "Raat", "Sapna", "Sadak"],
    "ID": ["Biru", "Angkot", "Bundaran", "Hatiku", "Kota", "Senja"],
    "PT": ["Tejo", "Alfama", "Azul", "Cheia", "Lisboa", "Sal"],
    "EG": ["Nil", "Madina", "Azraq", "Sahra", "Masr", "Hawa"],
    "AR": ["Palermo", "Río", "Azul", "Barrio", "Enero", "Sur"],
    "CO": ["Bogotá", "Sabana", "Azul", "Barrio", "Oro", "Andes"],
    "PH": ["Maynila", "Dagat", "Asul", "Bayan", "Araw", "Ulan"],
    "AU": ["the Harbour", "Bondi", "Blue", "King Street", "January", "the Coast"],
    "NZ": ["the Harbour", "Piha", "Blue", "K Road", "January", "the Gulf"],
    "CV": ["Praia", "Mar", "Azul", "Bairro", "Sol", "Ilha"],
}

STOP = {"feat", "remix", "live", "with", "the", "and", "love", "you", "song",
        "music", "version", "from"}


def _norm(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def real_words(manifest: dict) -> set:
    """The same distinctive-word set radio/check_names.py builds."""
    return {w.lower() for r in manifest.values() for t in r
            for s in (t["artist"], t["title"])
            for w in re.findall(r"[A-Za-z']{4,}", s)} - STOP


def _collides(text: str, bad: set) -> bool:
    return any(w.lower() in bad for w in re.findall(r"[A-Za-z']{4,}", _norm(text)))


def build(week: str, regions, manifest: dict, tracks_per_region: int = 4) -> dict:
    bad = real_words(manifest)
    out = {}
    for r in regions:
        used = set()
        for k in range(1, tracks_per_region + 1):
            rng = random.Random(f"{week}|{r}|{k}")
            for attempt in range(200):
                artist = f"{rng.choice(PLACES[r])} {rng.choice(COLLECTIVE)}"
                title = f"{rng.choice(TITLE_A[r])} {rng.choice(TITLE_B[r])}"
                if (artist, title) in used or _collides(artist, bad) or _collides(title, bad):
                    continue
                used.add((artist, title))
                out[f"{r}-0{k}"] = {"artist": artist, "title": title}
                break
            else:
                raise SystemExit(
                    f"{r}-0{k}: no fictional name survived the real-name filter "
                    f"in 200 draws - widen the lexicon rather than shipping a near-miss")
    return out
