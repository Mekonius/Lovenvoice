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
| 2. Curate | `jarvis/curate.py` | The model selects **exactly 10** stories and returns strict JSON. Malformed output retries once, then fails loudly. |
| 3. Write | `jarvis/write.py` | The model writes an intro, 2–3 spoken paragraphs per story, and a closing *Bigger Picture* — one plain-text narration script. |
| 4. Narrate | `jarvis/narrate.py` | ElevenLabs synthesises `output/briefing_YYYY-MM-DD.mp3`. Falls back to macOS `say` (→ `.m4a`, iPhone-native) if no key. |

All three backends sit behind one thin wrapper, `jarvis/llm.py`, exposing a
single `call(provider, model, system, prompt) -> str`. Models and providers are
swappable per stage via `.env` — no code changes needed. Supported providers:

- **`ollama`** — free, local, offline. Runs a model on your own machine, no API
  key, no bill. **This is the default in `.env.example`** — the whole pipeline
  can run at $0.
- **`anthropic`** — best quality, ~a few dollars/month on prepaid API credits.
- **`openai`** — optional swap; needs its own API credits.

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
python briefing.py             # full run, writes output/briefing_YYYY-MM-DD.(mp3|m4a)
```

### Free, zero-cost setup (Ollama + macOS `say`)

Run the entire pipeline for **$0** — no API keys, nothing leaves your machine:

```bash
# 1. Install Ollama (macOS)
brew install ollama
ollama serve            # starts the local server (leave running; or use the app)

# 2. Pull a model (one-time download)
ollama pull llama3.1    # ~5 GB, needs ~8 GB RAM. Low on RAM? use llama3.2 (3B)

# 3. Point Jarvis at it — in .env:
#    CURATE_PROVIDER=ollama
#    WRITE_PROVIDER=ollama
#    CURATE_MODEL=llama3.1
#    WRITE_MODEL=llama3.1
#    (leave ANTHROPIC_API_KEY / OPENAI_API_KEY blank)

python briefing.py      # narrates via macOS `say` when no ElevenLabs key → .m4a
```

`.env.example` already ships with these Ollama defaults, so a fresh `cp
.env.example .env` is ready to run free out of the box. Model sizing rule of
thumb: `llama3.2` (3B) for ≤8 GB RAM, `llama3.1` (8B) for 16 GB, `qwen2.5:14b`
or larger if you have the headroom and want sharper curation.

---

## Configuration (`.env`)

Copy `.env.example` to `.env`. Keys are never hardcoded and `.env` is
git-ignored.

| Key | Required | Purpose |
|-----|----------|---------|
| `CURATE_PROVIDER` / `WRITE_PROVIDER` | No | `ollama` (default, free/local), `anthropic`, or `openai`. |
| `CURATE_MODEL` / `WRITE_MODEL` | No | Model id per stage. Defaults: `llama3.1`. |
| `OLLAMA_BASE_URL` | No | Local Ollama address. Default `http://localhost:11434`. |
| `ANTHROPIC_API_KEY` | Only if provider is `anthropic` | Curation + writing via the Anthropic API. |
| `OPENAI_API_KEY` | Only if provider is `openai` | Curation + writing via the OpenAI API. |
| `ELEVENLABS_API_KEY` | No | If unset, narration falls back to macOS `say` (→ `.m4a`). |
| `ELEVENLABS_VOICE_ID` | If using ElevenLabs | Voice for the narrator (find IDs in the ElevenLabs app). |
| `ELEVENLABS_MODEL_ID` | No | Default `eleven_multilingual_v2`. |
| `ELEVENLABS_OUTPUT_FORMAT` | No | Default `mp3_44100_128`. |
| `LISTENER_NAME` | No | Used in the intro ("Good morning, …"). Default `Kenneth`. |
| `BRIEFING_TIMEZONE` | No | IANA tz for the intro time + filenames. Default `Europe/Copenhagen`. |

### Swapping providers

The wrapper picks the SDK lazily — the `anthropic` / `openai` packages are only
imported when a stage actually selects them, and `ollama` uses plain HTTP.

- **Free/local (default):** `CURATE_PROVIDER=ollama`, `WRITE_PROVIDER=ollama`.
- **Anthropic:** set the providers to `anthropic`, models to `claude-sonnet-5`,
  and add `ANTHROPIC_API_KEY`.
- **OpenAI:** set the providers to `openai`, models to e.g. `gpt-4o`, and add
  `OPENAI_API_KEY`.

You can mix — e.g. curate locally with Ollama and write with Anthropic — since
provider and model are set per stage.

---

## Billing: this is the API, not your Pro/Plus subscription

**A Claude Pro or ChatGPT Plus subscription does not power this app.** Those are
the consumer chat apps (claude.ai, chatgpt.com), billed separately from the
developer **API** that `anthropic`/`openai` providers use. There is no
supported way to drive your Pro/Plus subscription from code.

- **`ollama` (default): $0.** Runs locally, no account, no key, no bill. This is
  the recommended path if cost matters — the pipeline is fully automated and
  free.
- **`anthropic`/`openai`:** metered pay-per-token via **prepaid credits** at
  `console.anthropic.com` / `platform.openai.com` — a *separate* wallet from any
  subscription. At ~13 small calls per daily run, expect only a few dollars a
  month, but it is not free. Credits are prepaid: when they run out, calls fail
  (the run errors and logs it) rather than running up a surprise bill. Set a
  spend cap + low-balance alert in the console to be safe.

TTS billing is independent: ElevenLabs is paid; the macOS `say` fallback is free.

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
