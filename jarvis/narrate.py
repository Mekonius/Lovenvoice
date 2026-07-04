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
    """Synthesise ``script`` to audio near ``output_path``. Returns the path.

    Provider selection follows ``TTS_PROVIDER``:

    - ``elevenlabs`` — paid, highest quality (needs a key + voice id).
    - ``edge``       — free Microsoft Edge neural voices, no key. Cloud-friendly
                       (works on Linux/GitHub Actions). Writes ``.mp3``.
    - ``say``        — macOS ``say`` (offline, Mac only). Writes ``.m4a``.
    - ``auto`` (default) — try elevenlabs → edge → say, first available wins.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    choice = settings.tts_provider.lower()

    if choice in ("elevenlabs", "auto") and settings.elevenlabs_api_key:
        if not settings.elevenlabs_voice_id:
            raise NarrationError("ELEVENLABS_API_KEY set but ELEVENLABS_VOICE_ID is missing.")
        log.info("Narrating via ElevenLabs (voice=%s)", settings.elevenlabs_voice_id)
        return _narrate_elevenlabs(script, output_path)

    if choice == "elevenlabs":
        raise NarrationError("TTS_PROVIDER=elevenlabs but ELEVENLABS_API_KEY is not set.")

    if choice in ("edge", "auto"):
        log.info("Narrating via edge-tts (voice=%s)", settings.edge_tts_voice)
        return _narrate_edge_tts(script, output_path)

    if choice == "say":
        log.info("Narrating via macOS `say`")
        return _narrate_macos_say(script, output_path)

    raise NarrationError(
        f"Unknown TTS_PROVIDER {settings.tts_provider!r} "
        "(expected 'auto', 'elevenlabs', 'edge', or 'say')."
    )


def _narrate_edge_tts(script: str, output_path: Path) -> Path:
    """Free neural TTS via Microsoft Edge voices. No API key; writes .mp3."""
    try:
        import asyncio

        import edge_tts
    except ImportError as exc:  # pragma: no cover - install guard
        raise NarrationError("edge-tts not installed. Run: pip install edge-tts") from exc

    mp3_path = output_path.with_suffix(".mp3")

    async def _run() -> None:
        communicate = edge_tts.Communicate(script, settings.edge_tts_voice)
        await communicate.save(str(mp3_path))

    try:
        asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001 - surface network/voice errors clearly
        raise NarrationError(f"edge-tts synthesis failed: {exc}") from exc

    log.info("Wrote %s via edge-tts", mp3_path)
    return mp3_path


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
