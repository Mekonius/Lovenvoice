"""Thin LLM wrapper.

Exposes a single entry point::

    call(provider, model, system, prompt) -> str

so both SDKs sit behind one interface and models are swappable via ``.env``.
Anthropic is the default and always-available path; OpenAI is an optional swap
that is only imported when actually selected.
"""

from __future__ import annotations

import requests

from .config import settings

# Shared generation defaults. Kept conservative — briefings are short.
_MAX_TOKENS = 4096
_TEMPERATURE = 0.4


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
        RuntimeError: The provider SDK is not installed, or a local call failed.
    """
    provider = (provider or "anthropic").lower()
    if provider == "anthropic":
        return _call_anthropic(model, system, prompt)
    if provider == "openai":
        return _call_openai(model, system, prompt)
    if provider == "gemini":
        return _call_gemini(model, system, prompt)
    if provider == "ollama":
        return _call_ollama(model, system, prompt)
    raise ValueError(
        f"Unknown LLM provider: {provider!r} "
        "(expected 'gemini', 'anthropic', 'openai', or 'ollama')"
    )


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
