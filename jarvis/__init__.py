"""Jarvis Briefing — a personal morning news briefing pipeline.

Four stages, orchestrated by ``briefing.py``:

1. Fetch    (:mod:`jarvis.fetch`)   — pull last-24h stories from RSS feeds.
2. Curate   (:mod:`jarvis.curate`)  — Claude selects exactly 10, returns JSON.
3. Write    (:mod:`jarvis.write`)    — Claude writes a spoken narration script.
4. Narrate  (:mod:`jarvis.narrate`)  — ElevenLabs (or macOS `say`) → dated MP3.
"""

__version__ = "1.0.0"
