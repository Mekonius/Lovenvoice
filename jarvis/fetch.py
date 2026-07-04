"""Stage 1 — Fetch.

Read RSS/Atom feeds from ``feeds.yaml``, keep entries from the last 24 hours,
dedupe by title similarity, and return ~40 candidate stories as dicts of
``{title, summary, source, link, published}``.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

import feedparser
import yaml

from .config import settings

log = logging.getLogger(__name__)

# Tunables for candidate collection.
LOOKBACK_HOURS = 24
MAX_CANDIDATES = 40
TITLE_SIMILARITY_THRESHOLD = 0.85  # entries above this are treated as duplicates
_TAG_RE = re.compile(r"<[^>]+>")


def _load_feeds(feeds_file: Path) -> list[dict]:
    """Parse ``feeds.yaml`` into a list of ``{name, url}`` dicts."""
    with open(feeds_file, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    feeds = data.get("feeds", [])
    if not feeds:
        raise ValueError(f"No feeds defined in {feeds_file}")
    return feeds


def _clean(text: str) -> str:
    """Strip HTML tags/entities and collapse whitespace from feed text."""
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _entry_published(entry) -> datetime | None:
    """Best-effort published/updated timestamp as an aware UTC datetime."""
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
    return None


def _normalize_title(title: str) -> str:
    """Lowercase, alphanumeric-only key used for similarity comparison."""
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def _is_duplicate(title: str, seen: list[str]) -> bool:
    """True if ``title`` is near-identical to something already collected."""
    norm = _normalize_title(title)
    if not norm:
        return True
    for other in seen:
        if SequenceMatcher(None, norm, other).ratio() >= TITLE_SIMILARITY_THRESHOLD:
            return True
    return False


def fetch_candidates(
    feeds_file: Path | None = None,
    lookback_hours: int = LOOKBACK_HOURS,
    max_candidates: int = MAX_CANDIDATES,
) -> list[dict]:
    """Collect recent, deduped candidate stories from all configured feeds.

    A single unreachable or malformed feed is logged and skipped — it never
    aborts the run. Candidates are returned newest-first.
    """
    feeds_file = feeds_file or settings.feeds_file
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    collected: list[dict] = []
    seen_titles: list[str] = []

    for feed in _load_feeds(feeds_file):
        name, url = feed.get("name", "Unknown"), feed.get("url", "")
        if not url:
            continue
        try:
            parsed = feedparser.parse(url)
        except Exception as exc:  # noqa: BLE001 - one bad feed must not kill the run
            log.warning("Failed to fetch feed %s (%s): %s", name, url, exc)
            continue
        if parsed.bozo and not parsed.entries:
            log.warning("Feed %s returned no usable entries: %s", name, parsed.get("bozo_exception"))
            continue

        for entry in parsed.entries:
            title = _clean(entry.get("title", ""))
            if not title:
                continue
            published = _entry_published(entry)
            # Keep entries within the lookback window. Entries with no date are
            # kept but sorted last (treated as older than any dated entry).
            if published is not None and published < cutoff:
                continue
            if _is_duplicate(title, seen_titles):
                continue

            seen_titles.append(_normalize_title(title))
            collected.append(
                {
                    "title": title,
                    "summary": _clean(entry.get("summary", entry.get("description", ""))),
                    "source": name,
                    "link": entry.get("link", ""),
                    "published": published.isoformat() if published else "",
                }
            )

    # Newest first; undated entries (empty string) sort to the end.
    collected.sort(key=lambda c: c["published"] or "", reverse=True)
    log.info("Fetched %d candidate stories (capped at %d)", len(collected), max_candidates)
    return collected[:max_candidates]
