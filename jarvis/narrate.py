"""Stage 4 — Narrate.

Send the narration script to ElevenLabs and save a dated MP3. If no ElevenLabs
key is configured, fall back to the macOS ``say`` command so the pipeline still
produces audio on a Mac.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests

from .config import settings

log = logging.getLogger(__name__)

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
_TIMEOUT_SECONDS = 300


class NarrationError(RuntimeError):
    """Raised when audio synthesis fails."""


def narrate(script: str, output_path: Path) -> Path:
    """Synthesise ``script`` to ``output_path`` (an .mp3). Returns the path.

    Uses ElevenLabs when a key is set; otherwise falls back to macOS ``say``.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if settings.elevenlabs_api_key:
        if not settings.elevenlabs_voice_id:
            raise NarrationError("ELEVENLABS_API_KEY set but ELEVENLABS_VOICE_ID is missing.")
        log.info("Narrating via ElevenLabs (voice=%s)", settings.elevenlabs_voice_id)
        return _narrate_elevenlabs(script, output_path)

    log.info("No ElevenLabs key; falling back to macOS `say`")
    return _narrate_macos_say(script, output_path)


def _narrate_elevenlabs(script: str, output_path: Path) -> Path:
    url = ELEVENLABS_TTS_URL.format(voice_id=settings.elevenlabs_voice_id)
    headers = {
        "xi-api-key": settings.elevenlabs_api_key,
        "accept": "audio/mpeg",
        "content-type": "application/json",
    }
    payload = {
        "text": script,
        "model_id": settings.elevenlabs_model_id,
        # Calm, steady delivery: high stability, moderate similarity.
        "voice_settings": {"stability": 0.55, "similarity_boost": 0.75, "style": 0.0},
    }
    params = {"output_format": settings.elevenlabs_output_format}

    resp = requests.post(url, headers=headers, json=payload, params=params, timeout=_TIMEOUT_SECONDS)
    if resp.status_code != 200:
        raise NarrationError(f"ElevenLabs API error {resp.status_code}: {resp.text[:500]}")

    output_path.write_bytes(resp.content)
    log.info("Wrote %s (%d bytes)", output_path, output_path.stat().st_size)
    return output_path


def _narrate_macos_say(script: str, output_path: Path) -> Path:
    """Fallback TTS via macOS `say` → AIFF → `afconvert` → MP3."""
    if not shutil.which("say"):
        raise NarrationError(
            "No ElevenLabs key and macOS `say` is unavailable. Set ELEVENLABS_API_KEY "
            "or run on macOS. Use --dry-run to skip narration entirely."
        )

    with tempfile.TemporaryDirectory() as tmp:
        aiff = Path(tmp) / "briefing.aiff"
        # "Daniel" is a calm British male voice — a reasonable JARVIS stand-in.
        subprocess.run(
            ["say", "-v", "Daniel", "-o", str(aiff), script],
            check=True,
        )
        if shutil.which("afconvert"):
            subprocess.run(
                ["afconvert", str(aiff), str(output_path), "-f", "mp4f", "-d", "aac"],
                check=True,
            )
        else:
            # No afconvert: keep the AIFF alongside the intended path.
            fallback = output_path.with_suffix(".aiff")
            shutil.copy(aiff, fallback)
            log.warning("afconvert missing; wrote %s instead of MP3", fallback)
            return fallback

    log.info("Wrote %s via macOS say", output_path)
    return output_path
