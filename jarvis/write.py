"""Stage 3 — Write.

Turn the 10 curated stories into a single plain-text narration script: an
intro, one 2–3 paragraph segment per story, and a closing "Bigger Picture."
The output must read aloud naturally — no markdown, no headers, no labels.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from . import llm
from .config import settings
from .prompts import WRITE_SYSTEM, closing_prompt, intro_prompt, story_prompt

log = logging.getLogger(__name__)

# Blank line between spoken segments so TTS engines pause naturally.
SEGMENT_SEPARATOR = "\n\n"


def _time_phrase() -> str:
    """A spoken time-of-day phrase like 'just past six forty-five in the morning'.

    Kept simple and TTS-friendly: the model is given a clean 'H:MM AM/PM' string
    and asked to open with it verbatim, so we hand it a natural-sounding value.
    """
    try:
        now = datetime.now(ZoneInfo(settings.timezone))
    except Exception:  # noqa: BLE001 - bad tz string shouldn't crash the run
        log.warning("Unknown timezone %r; falling back to local time", settings.timezone)
        now = datetime.now()
    # e.g. "6:45 AM"; strip a leading zero from the hour for natural speech.
    return now.strftime("%-I:%M %p") if hasattr(now, "strftime") else "morning"


def _write_segment(system: str, prompt: str) -> str:
    return llm.call(
        provider=settings.write_provider,
        model=settings.write_model,
        system=system,
        prompt=prompt,
    ).strip()


def write_script(stories: list[dict]) -> str:
    """Assemble the full spoken narration script from the curated stories."""
    time_phrase = _time_phrase()

    log.info("Writing intro")
    intro = _write_segment(WRITE_SYSTEM, intro_prompt(settings.listener_name, time_phrase, stories))

    segments: list[str] = [intro]
    for i, story in enumerate(stories, start=1):
        log.info("Writing story %d/%d: %s", i, len(stories), story["headline"])
        segments.append(_write_segment(WRITE_SYSTEM, story_prompt(story)))

    log.info("Writing closing 'Bigger Picture'")
    segments.append(_write_segment(WRITE_SYSTEM, closing_prompt(stories)))

    script = SEGMENT_SEPARATOR.join(seg for seg in segments if seg)
    log.info("Assembled narration script: %d characters", len(script))
    return script
