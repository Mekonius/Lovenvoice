"""Thin LLM wrapper.

Exposes a single entry point::

    call(provider, model, system, prompt) -> str

so both SDKs sit behind one interface and models are swappable via ``.env``.
Anthropic is the default and always-available path; OpenAI is an optional swap
that is only imported when actually selected.
"""

from __future__ import annotations

import logging
import re
import time

import requests

from .config import settings

log = logging.getLogger(__name__)

# Shared generation defaults. Kept small so a whole request (input + this
# output reservation) fits Groq's free-tier 8B per-minute budget (6k tokens).
# Curate needs ~850 output for 10 JSON objects; write segments ~600 — 2048 is
# ample for both.
_MAX_TOKENS = 2048
_TEMPERATURE = 0.4

# Retry a rate-limited (429) provider this many times before giving up on it.
_RETRY_MAX = 5
_RETRY_CAP_SECONDS = 30.0


class RateLimitError(RuntimeError):
    """A provider returned HTTP 429. ``retry_after`` is seconds to wait, if known."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def call(provider: str, model: str, system: str, prompt: str) -> str:
    """Send one system+user turn to ``provider``/``model`` and return the text.

    Args:
        provider: ``"gemini"`` (free cloud tier), ``"anthropic"``, ``"openai"``,
                  or ``"ollama"`` (free, local, no API key).
        model:    Model id, e.g. ``gemini-2.0-flash``, ``claude-sonnet-5``,
                  ``gpt-4o``, or ``llama3.1``.
        system:   System prompt.
        prompt:   User prompt.

    Returns:
        The model's text response, stripped.

    Raises:
        ValueError: Unknown provider or missing API key.
        RuntimeError: The provider SDK is not installed, or a call failed.

    Free-tier rate limits (HTTP 429) on the primary are retried with backoff
    (honouring the provider's suggested wait). If the primary still fails and a
    ready fallback provider is configured (``FALLBACK_PROVIDER`` /
    ``FALLBACK_MODEL``), the request is retried once there.
    """
    primary = provider or "anthropic"
    try:
        return _dispatch_retrying(primary, model, system, prompt)
    except Exception as primary_exc:  # noqa: BLE001 - fall back on any provider failure
        fb_provider = (settings.fallback_provider or "").lower()
        fb_model = settings.fallback_model
        if fb_provider and fb_provider != primary.lower() and _provider_ready(fb_provider):
            log.warning(
                "Primary LLM %s/%s failed (%s); falling back to %s/%s",
                primary, model, primary_exc, fb_provider, fb_model,
            )
            try:
                return _dispatch(fb_provider, fb_model, system, prompt)
            except Exception as fb_exc:  # noqa: BLE001 - report both failures
                raise RuntimeError(
                    f"Both primary ({primary}/{model}) and fallback "
                    f"({fb_provider}/{fb_model}) LLM calls failed. "
                    f"Primary error: {primary_exc}. Fallback error: {fb_exc}"
                ) from fb_exc
        raise


def _dispatch_retrying(provider: str, model: str, system: str, prompt: str) -> str:
    """Dispatch, retrying on rate-limit (429) with the provider's suggested wait."""
    for attempt in range(_RETRY_MAX + 1):
        try:
            return _dispatch(provider, model, system, prompt)
        except RateLimitError as exc:
            if attempt >= _RETRY_MAX:
                raise
            wait = min(exc.retry_after or 5.0, _RETRY_CAP_SECONDS) + 0.5
            log.warning(
                "Rate limited by %s/%s (attempt %d/%d); waiting %.1fs then retrying",
                provider, model, attempt + 1, _RETRY_MAX, wait,
            )
            time.sleep(wait)
    raise RuntimeError("unreachable")  # pragma: no cover


def _retry_after_seconds(resp: requests.Response) -> float | None:
    """Best-effort extraction of how long to wait from a 429 response."""
    header = resp.headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    # Groq: "...Please try again in 6.305s." ; Gemini: "retryDelay": "5s"
    for pattern in (r"try again in ([\d.]+)s", r'"retryDelay":\s*"([\d.]+)s"'):
        match = re.search(pattern, resp.text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
    return None


def _dispatch(provider: str, model: str, system: str, prompt: str) -> str:
    """Route one call to a single provider (no fallback)."""
    provider = provider.lower()
    if provider == "anthropic":
        return _call_anthropic(model, system, prompt)
    if provider == "openai":
        return _call_openai(model, system, prompt)
    if provider == "gemini":
        return _call_gemini(model, system, prompt)
    if provider == "groq":
        return _call_groq(model, system, prompt)
    if provider == "ollama":
        return _call_ollama(model, system, prompt)
    raise ValueError(
        f"Unknown LLM provider: {provider!r} "
        "(expected 'gemini', 'groq', 'anthropic', 'openai', or 'ollama')"
    )


def _provider_ready(provider: str) -> bool:
    """True if ``provider`` has what it needs to run (key present, or keyless)."""
    provider = provider.lower()
    if provider == "ollama":
        return True  # local, no key
    return bool(settings.provider_key(provider))


def _call_anthropic(model: str, system: str, prompt: str) -> str:
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set (see .env.example).")
    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover - install guard
        raise RuntimeError("anthropic SDK not installed. Run: pip install anthropic") from exc

    client = Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        temperature=_TEMPERATURE,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    # Concatenate any text blocks in the response.
    parts = [block.text for block in message.content if getattr(block, "type", None) == "text"]
    return "".join(parts).strip()


def _call_openai(model: str, system: str, prompt: str) -> str:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set but a stage is using provider 'openai'.")
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - install guard
        raise RuntimeError("openai SDK not installed. Run: pip install openai") from exc

    client = OpenAI(api_key=settings.openai_api_key)
    completion = client.chat.completions.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        temperature=_TEMPERATURE,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return (completion.choices[0].message.content or "").strip()


_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def _call_groq(model: str, system: str, prompt: str) -> str:
    """Call Groq's free, fast, OpenAI-compatible API (only needs ``requests``).

    Get a key at https://console.groq.com/keys (no credit card).
    """
    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY is not set but a stage is using provider 'groq'.")
    resp = requests.post(
        _GROQ_URL,
        headers={
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": _TEMPERATURE,
            "max_tokens": _MAX_TOKENS,
        },
        timeout=120,
    )
    if resp.status_code == 429:
        raise RateLimitError(f"Groq error 429: {resp.text[:300]}", _retry_after_seconds(resp))
    if resp.status_code != 200:
        raise RuntimeError(f"Groq error {resp.status_code}: {resp.text[:400]}")
    return (resp.json()["choices"][0]["message"]["content"] or "").strip()


_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _call_gemini(model: str, system: str, prompt: str) -> str:
    """Call the Google Gemini API — free tier, no credit card.

    Uses the native ``generateContent`` REST endpoint (only needs ``requests``).
    Get a key at https://aistudio.google.com/apikey.
    """
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not set but a stage is using provider 'gemini'.")
    url = f"{_GEMINI_BASE}/models/{model}:generateContent"
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": _TEMPERATURE, "maxOutputTokens": _MAX_TOKENS},
    }
    resp = requests.post(
        url, params={"key": settings.gemini_api_key}, json=payload, timeout=120
    )
    if resp.status_code == 429:
        raise RateLimitError(f"Gemini error 429: {resp.text[:300]}", _retry_after_seconds(resp))
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini error {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError) as exc:
        # Empty candidates usually means a safety block or bad model id.
        raise RuntimeError(f"Unexpected Gemini response: {str(data)[:400]}") from exc
    return "".join(p.get("text", "") for p in parts).strip()


# Local generation can be slow on modest hardware; give it room.
_OLLAMA_TIMEOUT = 600


def _call_ollama(model: str, system: str, prompt: str) -> str:
    """Call a local Ollama server — free, offline, no API key.

    Talks to Ollama's native chat endpoint (``/api/chat``) over HTTP. Requires
    a running ``ollama serve`` with the model pulled (``ollama pull <model>``).
    """
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": _TEMPERATURE},
    }
    try:
        resp = requests.post(url, json=payload, timeout=_OLLAMA_TIMEOUT)
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            f"Could not reach Ollama at {settings.ollama_base_url}. "
            "Is it running? Start it with `ollama serve` and pull the model "
            f"with `ollama pull {model}`."
        ) from exc
    if resp.status_code != 200:
        raise RuntimeError(f"Ollama error {resp.status_code}: {resp.text[:300]}")
    return (resp.json().get("message", {}).get("content") or "").strip()
