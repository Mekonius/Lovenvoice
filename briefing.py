#!/usr/bin/env python3
"""Jarvis Briefing — orchestrator.

Runs the four-stage pipeline and produces a dated MP3 morning briefing:

    Stage 1  Fetch    RSS feeds → ~40 candidate stories
    Stage 2  Curate   Claude selects exactly 10 (strict JSON)
    Stage 3  Write    Claude writes a spoken narration script
    Stage 4  Narrate  ElevenLabs (or macOS say) → output/briefing_YYYY-MM-DD.mp3

Every stage's raw output is logged to runs/YYYY-MM-DD/ for debugging.

Usage:
    python briefing.py            # full run, produces an MP3
    python briefing.py --dry-run  # prints the script, skips TTS
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from jarvis import curate as curate_stage
from jarvis import fetch as fetch_stage
from jarvis import narrate as narrate_stage
from jarvis import write as write_stage
from jarvis.config import settings

log = logging.getLogger("jarvis.briefing")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _run_dir(date_str: str) -> Path:
    """Create and return runs/<date>/ for this run's debug artefacts."""
    run_dir = settings.runs_dir / date_str
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _dump(run_dir: Path, name: str, content: str) -> None:
    """Write a raw stage artefact to the run directory."""
    (run_dir / name).write_text(content, encoding="utf-8")
    log.info("Logged %s", run_dir / name)


def run(dry_run: bool = False) -> Path | None:
    """Execute the full pipeline. Returns the MP3 path, or None on --dry-run."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    run_dir = _run_dir(date_str)

    # ── Stage 1: Fetch ──
    log.info("=== Stage 1: Fetch ===")
    candidates = fetch_stage.fetch_candidates()
    if not candidates:
        log.error("No candidate stories fetched — check feeds.yaml and connectivity.")
        raise SystemExit(1)
    _dump(run_dir, "01_candidates.json", json.dumps(candidates, ensure_ascii=False, indent=2))

    # ── Stage 2: Curate ──
    log.info("=== Stage 2: Curate ===")
    stories, curate_raw = curate_stage.curate(candidates)
    _dump(run_dir, "02_curated_raw.txt", curate_raw)
    _dump(run_dir, "02_curated.json", json.dumps(stories, ensure_ascii=False, indent=2))

    # ── Stage 3: Write ──
    log.info("=== Stage 3: Write ===")
    script = write_stage.write_script(stories)
    _dump(run_dir, "03_script.txt", script)

    if dry_run:
        print("\n" + "=" * 72)
        print(f"JARVIS BRIEFING — {date_str}  (dry run, no audio)")
        print("=" * 72 + "\n")
        print(script)
        print("\n" + "=" * 72)
        log.info("Dry run complete. Script logged to %s", run_dir / "03_script.txt")
        return None

    # ── Stage 4: Narrate ──
    log.info("=== Stage 4: Narrate ===")
    mp3_path = settings.output_dir / f"briefing_{date_str}.mp3"
    result = narrate_stage.narrate(script, mp3_path)
    log.info("Briefing ready: %s", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the Jarvis morning briefing.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the narration script and skip text-to-speech.",
    )
    args = parser.parse_args(argv)

    _setup_logging()
    try:
        run(dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001 - top-level: log and fail loudly
        log.error("Briefing failed: %s", exc, exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
