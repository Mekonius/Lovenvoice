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


def _is_danish(language: str) -> bool:
    return language.strip().lower().startswith("dan")


def _time_phrase() -> str:
    """A clean clock string for the intro, e.g. '6:45 AM' (or 24-hour for Danish)."""
    try:
        now = datetime.now(ZoneInfo(settings.timezone))
    except Exception:  # noqa: BLE001 - bad tz string shouldn't crash the run
        log.warning("Unknown timezone %r; falling back to local time", settings.timezone)
        now = datetime.now()
    if _is_danish(settings.briefing_language):
        return now.strftime("%H.%M")  # Danish 24-hour, e.g. "07.45"
    # e.g. "6:45 AM"; strip a leading zero from the hour for natural speech.
    return now.strftime("%-I:%M %p")


def _write_segment(system: str, prompt: str) -> str:
    return llm.call(
        provider=settings.write_provider,
        model=settings.write_model,
        system=system,
        prompt=prompt,
    ).strip()


def _system_for(language: str) -> str:
    """WRITE_SYSTEM plus a hard directive to write in the target language."""
    if language.strip().lower() in ("", "english", "en"):
        return WRITE_SYSTEM
    return (
        f"{WRITE_SYSTEM}\n\nWrite the entire briefing in {language}. Every spoken "
        f"word — intro, stories, and closing — must be natural, fluent {language}. "
        "The source material may be in another language; render it into idiomatic "
        f"{language}, never a word-for-word translation."
    )


def write_script(stories: list[dict]) -> str:
    """Assemble the full spoken narration script from the curated stories."""
    language = settings.briefing_language
    system = _system_for(language)
    time_phrase = _time_phrase()

    log.info("Writing intro (language=%s)", language)
    intro = _write_segment(
        system, intro_prompt(settings.listener_name, time_phrase, stories, language)
    )

    segments: list[str] = [intro]
    for i, story in enumerate(stories, start=1):
        log.info("Writing story %d/%d: %s", i, len(stories), story["headline"])
        segments.append(_write_segment(system, story_prompt(story)))

    log.info("Writing closing 'Bigger Picture'")
    segments.append(_write_segment(system, closing_prompt(stories)))

    script = SEGMENT_SEPARATOR.join(seg for seg in segments if seg)
    log.info("Assembled narration script: %d characters", len(script))
    return script
