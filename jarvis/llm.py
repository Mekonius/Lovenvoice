"""Thin LLM wrapper.

Exposes a single entry point::

    call(provider, model, system, prompt) -> str

so both SDKs sit behind one interface and models are swappable via ``.env``.
Anthropic is the default and always-available path; OpenAI is an optional swap
that is only imported when actually selected.
"""

from __future__ import annotations

from .config import settings

# Shared generation defaults. Kept conservative — briefings are short.
_MAX_TOKENS = 4096
_TEMPERATURE = 0.4


def call(provider: str, model: str, system: str, prompt: str) -> str:
    """Send one system+user turn to ``provider``/``model`` and return the text.

    Args:
        provider: ``"anthropic"`` (default) or ``"openai"``.
        model:    Model id, e.g. ``claude-sonnet-5`` or ``gpt-4o``.
        system:   System prompt.
        prompt:   User prompt.

    Returns:
        The model's text response, stripped.

    Raises:
        ValueError: Unknown provider or missing API key.
        RuntimeError: The provider SDK is not installed.
    """
    provider = (provider or "anthropic").lower()
    if provider == "anthropic":
        return _call_anthropic(model, system, prompt)
    if provider == "openai":
        return _call_openai(model, system, prompt)
    raise ValueError(f"Unknown LLM provider: {provider!r} (expected 'anthropic' or 'openai')")


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
