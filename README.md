# Jarvis Briefing

A personal morning news briefing. It fetches current world news on a schedule,
uses Claude to curate and write a calm spoken-word briefing, converts it to
audio with a JARVIS-like voice, and drops a dated MP3 you can play from your
phone.

The editorial bar is deliberately high: consequential, verifiable progress
across science, medicine, space, technology, environment, wildlife,
humanitarian and education — not clickbait, not manufactured positivity.

---

## How it works

One orchestrator, `briefing.py`, runs four stages:

| Stage | Module | What it does |
|-------|--------|--------------|
| 1. Fetch | `jarvis/fetch.py` | Read RSS feeds from `feeds.yaml`, keep the last 24h, dedupe by title similarity → ~40 candidates. |
| 2. Curate | `jarvis/curate.py` | Claude selects **exactly 10** stories and returns strict JSON. Malformed output retries once, then fails loudly. |
| 3. Write | `jarvis/write.py` | Claude writes an intro, 2–3 spoken paragraphs per story, and a closing *Bigger Picture* — one plain-text narration script. |
| 4. Narrate | `jarvis/narrate.py` | ElevenLabs synthesises `output/briefing_YYYY-MM-DD.mp3`. Falls back to macOS `say` (→ `.m4a`, iPhone-native) if no key. |

Both LLM SDKs sit behind one thin wrapper, `jarvis/llm.py`, exposing a single
`call(provider, model, system, prompt) -> str`. Models and providers are
swappable per stage via `.env` — no code changes needed.

Every stage's raw output is written to `runs/YYYY-MM-DD/` so you can always see
what got fetched, what got selected, and why.

---

## Setup

Requires **Python 3.11+**.

```bash
git clone <your-repo-url> Lovenvoice
cd Lovenvoice

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # then fill in your keys
```

Run it:

```bash
python briefing.py --dry-run   # prints the script, no audio — great for testing
python briefing.py             # full run, writes output/briefing_YYYY-MM-DD.mp3
```

---

## Configuration (`.env`)

Copy `.env.example` to `.env`. Keys are never hardcoded and `.env` is
git-ignored.

| Key | Required | Purpose |
|-----|----------|---------|
| `ANTHROPIC_API_KEY` | **Yes** | Curation + writing (default provider). |
| `OPENAI_API_KEY` | No | Only if you swap a stage to OpenAI. |
| `CURATE_PROVIDER` / `WRITE_PROVIDER` | No | `anthropic` (default) or `openai`. |
| `CURATE_MODEL` / `WRITE_MODEL` | No | Model id per stage. Defaults: `claude-sonnet-5`. |
| `ELEVENLABS_API_KEY` | No | If unset, narration falls back to macOS `say`. |
| `ELEVENLABS_VOICE_ID` | If using ElevenLabs | Voice for the narrator (find IDs in the ElevenLabs app). |
| `ELEVENLABS_MODEL_ID` | No | Default `eleven_multilingual_v2`. |
| `ELEVENLABS_OUTPUT_FORMAT` | No | Default `mp3_44100_128`. |
| `LISTENER_NAME` | No | Used in the intro ("Good morning, …"). Default `Kenneth`. |
| `BRIEFING_TIMEZONE` | No | IANA tz for the intro time + filenames. Default `Europe/Copenhagen`. |

### Anthropic by default, OpenAI as an optional swap

The default path is Anthropic-only. To try OpenAI for a stage, set e.g.
`CURATE_PROVIDER=openai` and `CURATE_MODEL=gpt-4o`, and add `OPENAI_API_KEY`.
The `openai` SDK is only imported when actually selected.

---

## Adding or changing feeds

Edit `feeds.yaml` — no code changes needed:

```yaml
feeds:
  - name: Nature News
    url: https://www.nature.com/nature.rss
  - name: Your New Source
    url: https://example.org/rss
```

`name` becomes the `source` on every story. A feed that fails to load is logged
and skipped — one bad URL won't break the run. The seed list leans
science/health/climate/tech (Nature, ESA, NASA, WHO, IEA, MIT News, university
press rooms, Mongabay, and more).

---

## Scheduling a 6:45am run

### macOS — launchd (recommended on a Mac)

Create `~/Library/LaunchAgents/com.jarvis.briefing.plist` (adjust the paths to
your checkout and virtualenv):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>            <string>com.jarvis.briefing</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/kenneth/Lovenvoice/.venv/bin/python</string>
    <string>/Users/kenneth/Lovenvoice/briefing.py</string>
  </array>
  <key>WorkingDirectory</key> <string>/Users/kenneth/Lovenvoice</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>   <integer>6</integer>
    <key>Minute</key> <integer>45</integer>
  </dict>
  <key>StandardOutPath</key>  <string>/Users/kenneth/Lovenvoice/runs/launchd.out.log</string>
  <key>StandardErrorPath</key><string>/Users/kenneth/Lovenvoice/runs/launchd.err.log</string>
</dict>
</plist>
```

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.jarvis.briefing.plist
```

### Linux — cron

Run `crontab -e` and add (adjust paths):

```cron
45 6 * * * cd /home/kenneth/Lovenvoice && /home/kenneth/Lovenvoice/.venv/bin/python briefing.py >> runs/cron.log 2>&1
```

Then sync `output/briefing_YYYY-MM-DD.mp3` to your iPhone however you prefer
(iCloud Drive, a synced folder, an Apple Shortcut, etc.).

---

## Debugging a run

Look in `runs/YYYY-MM-DD/`:

- `01_candidates.json` — everything Stage 1 fetched.
- `02_curated_raw.txt` — Claude's raw curation response.
- `02_curated.json` — the validated 10 stories (with `why_selected`).
- `03_script.txt` — the final narration script.

---

## Where the OpenAI triage layer would slot in

The spec originally imagined an OpenAI pre-triage pass to thin the candidate
list before curation. At ~40 items/day that isn't worth the extra call or cost,
so it's intentionally **omitted**.

If volume grows (say you add many high-traffic feeds and Stage 1 starts
returning hundreds of candidates), the natural place for a cheap triage layer is
**between Stage 1 and Stage 2** — a new `jarvis/triage.py` that takes
`fetch_candidates()` output, asks a small/cheap model (e.g. `gpt-4o-mini` via the
existing `llm.call`) to score or filter down to the strongest ~40, and hands
those to `curate()`. Because everything already goes through the one `llm.py`
wrapper, adding it is a single new module and one line in `briefing.py`.
