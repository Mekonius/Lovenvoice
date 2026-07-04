"""Central configuration, loaded once from the environment / ``.env``.

Every tunable lives here so the rest of the code never touches ``os.environ``
directly. Import :data:`settings` and read attributes off it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (parent of this package) if present.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _env(key: str, default: str = "") -> str:
    """Return an env var, treating whitespace-only values as unset."""
    value = os.getenv(key, default)
    return value.strip() if value else default


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of runtime configuration."""

    # ── Paths ──
    project_root: Path = PROJECT_ROOT
    feeds_file: Path = PROJECT_ROOT / "feeds.yaml"
    output_dir: Path = PROJECT_ROOT / "output"
    runs_dir: Path = PROJECT_ROOT / "runs"

    # ── LLM providers / models (per stage, swappable via .env) ──
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))

    curate_provider: str = field(default_factory=lambda: _env("CURATE_PROVIDER", "anthropic"))
    write_provider: str = field(default_factory=lambda: _env("WRITE_PROVIDER", "anthropic"))
    curate_model: str = field(default_factory=lambda: _env("CURATE_MODEL", "claude-sonnet-5"))
    write_model: str = field(default_factory=lambda: _env("WRITE_MODEL", "claude-sonnet-5"))

    # Local Ollama server (free, offline). Used when a provider is "ollama".
    ollama_base_url: str = field(
        default_factory=lambda: _env("OLLAMA_BASE_URL", "http://localhost:11434")
    )

    # ── ElevenLabs TTS ──
    elevenlabs_api_key: str = field(default_factory=lambda: _env("ELEVENLABS_API_KEY"))
    elevenlabs_voice_id: str = field(default_factory=lambda: _env("ELEVENLABS_VOICE_ID"))
    elevenlabs_model_id: str = field(
        default_factory=lambda: _env("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
    )
    elevenlabs_output_format: str = field(
        default_factory=lambda: _env("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128")
    )

    # ── Personalisation ──
    listener_name: str = field(default_factory=lambda: _env("LISTENER_NAME", "Kenneth"))
    timezone: str = field(default_factory=lambda: _env("BRIEFING_TIMEZONE", "Europe/Copenhagen"))

    def provider_key(self, provider: str) -> str:
        """API key for a provider name, or empty string if unconfigured."""
        return {
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
        }.get(provider, "")


settings = Settings()
