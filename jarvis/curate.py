"""Stage 2 — Curate.

Send the candidate stories to Claude with the verbatim editorial system prompt
and get back exactly 10 selected stories as strict JSON. Validate hard: on
malformed output retry once, then fail loudly.
"""

from __future__ import annotations

import json
import logging
import re

from . import llm
from .config import settings
from .prompts import CURATE_SCHEMA_INSTRUCTION, CURATE_SYSTEM

log = logging.getLogger(__name__)

REQUIRED_KEYS = {"headline", "countries", "category", "label", "source_link", "why_selected"}
VALID_LABELS = {"Good News", "Progress", "Hopeful"}
EXPECTED_COUNT = 10

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class CurationError(RuntimeError):
    """Raised when the model cannot produce valid curation JSON."""


def _build_prompt(candidates: list[dict], count: int) -> str:
    """Render the candidate list into the user prompt for curation."""
    lines = ["Here are today's candidate stories as a JSON array:", ""]
    lines.append(json.dumps(candidates, ensure_ascii=False, indent=2))
    lines.append("")
    lines.append(CURATE_SCHEMA_INSTRUCTION.format(count=count))
    return "\n".join(lines)


def _extract_json(raw: str) -> str:
    """Pull the JSON array out of a model response, tolerating code fences."""
    fenced = _JSON_FENCE_RE.search(raw)
    if fenced:
        return fenced.group(1).strip()
    # Otherwise, slice from the first '[' to the last ']'.
    start, end = raw.find("["), raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        return raw[start : end + 1]
    return raw.strip()


def _validate(raw: str, count: int) -> list[dict]:
    """Parse and structurally validate the model output. Raises CurationError."""
    try:
        data = json.loads(_extract_json(raw))
    except json.JSONDecodeError as exc:
        raise CurationError(f"Output was not valid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise CurationError(f"Expected a JSON array, got {type(data).__name__}")
    if len(data) != count:
        raise CurationError(f"Expected exactly {count} stories, got {len(data)}")

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise CurationError(f"Story {i} is not an object")
        missing = REQUIRED_KEYS - item.keys()
        if missing:
            raise CurationError(f"Story {i} missing keys: {sorted(missing)}")
        if not isinstance(item["countries"], list):
            raise CurationError(f"Story {i}: 'countries' must be an array")
        if item["label"] not in VALID_LABELS:
            raise CurationError(f"Story {i}: invalid label {item['label']!r}")
    return data


def curate(candidates: list[dict]) -> tuple[list[dict], str]:
    """Select up to 10 stories from ``candidates`` (fewer on a slow news day).

    Returns ``(stories, raw_response)`` — the validated selection and the raw
    model text (for run logging). Retries once on malformed output, then fails
    loudly with :class:`CurationError`.
    """
    if not candidates:
        raise CurationError("No candidate stories to curate.")

    # Normally 10, but never ask for more stories than we have candidates.
    target = min(EXPECTED_COUNT, len(candidates))
    prompt = _build_prompt(candidates, target)
    last_error: Exception | None = None
    last_raw = ""

    for attempt in (1, 2):
        log.info("Curation attempt %d — selecting %d of %d (provider=%s model=%s)",
                 attempt, target, len(candidates),
                 settings.curate_provider, settings.curate_model)
        last_raw = llm.call(
            provider=settings.curate_provider,
            model=settings.curate_model,
            system=CURATE_SYSTEM,
            prompt=prompt,
        )
        try:
            stories = _validate(last_raw, target)
            log.info("Curation succeeded on attempt %d", attempt)
            return stories, last_raw
        except CurationError as exc:
            last_error = exc
            log.warning("Curation attempt %d failed: %s", attempt, exc)

    raise CurationError(f"Curation failed after 2 attempts: {last_error}\n\nLast output:\n{last_raw}")
