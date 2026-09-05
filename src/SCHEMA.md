# World Sound Radio — library contract (both the builder and the page read this)

`radio/library.json` — written by the library builder, read by `radio/index.html`. Audio lives in `radio/audio/` (gitignored; on the Space it ships as static files).

```json
{
  "generated_at": "2026-09-04T15:00:00Z",
  "chart_week": "2026-08-24",
  "regions": {
    "KE": {
      "city": "Nairobi", "country": "Kenya", "tz": "Africa/Nairobi",
      "readout": {"bpm": 95, "mode": "minor", "lufs": -13.4, "instruments": ["bass","keyboard","drums"], "moods": ["love","happy","deep"]},
      "genre_family": "Afro-Pop / Dance / Pop",
      "sa3_prompt": "...", "suno_prompt": "..."
    }
  },
  "tracks": [
    {
      "id": "KE-01",
      "region": "KE",
      "file": "audio/KE-01.mp3",
      "duration_s": 118.4,
      "title": "Lantern Season",            // fictional, never a real title or near-miss
      "artist": "Wanjiru & the Late Bus",   // fictional, never a real artist or near-miss
      "mirrors_rank": 3,                    // chart position of the seed track; the page shows "mirrors this week's Nairobi #3", never the real title
      "seed_mode": "vocals_kept" | "vocals_removed",
      "seed_source": "recording" | "synthetic",   // recording = a chart preview was the init (PRIVATE ONLY); synthetic = two-stage, SA3's own text gen was the init (public)
      "vibe": 0.42,
      "chunks": 4, "seeds": [11, 12, 13, 14],
      "lufs": -14.0
    }
  ]
}
```

Rules
- Every track is medium SA3, seeded from a chart track (ranks 1–5), 4 × 30 s chunks crossfaded → ~1:50–2:00, loudnormed to −14 LUFS-I. `vocals_kept` → vibe 0.42; `vocals_removed` (demucs stem) → vibe 0.7.
- Regions: KE Nairobi, AE Dubai, TZ Dar es Salaam, NG Lagos, GH Accra, UG Kampala, ZA Johannesburg, GB London, BR São Paulo, KR Seoul.
- The page never shows real artist or track names. Real titles stay in `radio/library.private.json` (gitignored) for Kalam only.
- `library.dev.json` is a stand-in with today's 30 s a2a gens (KE/AE/TZ) so the page can be built before the library exists; same shape.
