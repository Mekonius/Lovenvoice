"""Stage 4 — Narrate.

Send the narration script to ElevenLabs and save a dated MP3. If no ElevenLabs
key is configured, fall back to the macOS ``say`` command so the pipeline still
produces audio on a Mac — as a `.m4a` (AAC), since macOS cannot encode MP3.
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
    """Fallback TTS via macOS `say`, producing an iPhone-native AAC `.m4a`.

    macOS cannot encode MP3, so the fallback writes `.m4a` (AAC in an MP4
    container) instead — iPhones play it natively and the extension is honest.
    The returned path therefore differs from the ElevenLabs `.mp3` path.
    """
    if not shutil.which("say"):
        raise NarrationError(
            "No ElevenLabs key and macOS `say` is unavailable. Set ELEVENLABS_API_KEY "
            "or run on macOS. Use --dry-run to skip narration entirely."
        )

    m4a_path = output_path.with_suffix(".m4a")
    with tempfile.TemporaryDirectory() as tmp:
        # Read the script from a file so long briefings never hit argv limits.
        script_file = Path(tmp) / "script.txt"
        script_file.write_text(script, encoding="utf-8")
        # "Daniel" is a calm British male voice — a reasonable JARVIS stand-in.
        subprocess.run(
            ["say", "-v", "Daniel", "--data-format=aac", "-f", str(script_file), "-o", str(m4a_path)],
            check=True,
        )

    log.info("Wrote %s via macOS say", m4a_path)
    return m4a_path
