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

All backends sit behind one thin wrapper, `jarvis/llm.py`, exposing a single
`call(provider, model, system, prompt) -> str`. Models and providers are
swappable per stage via `.env` — no code changes needed. Supported providers:

- **`gemini`** — free cloud tier. Best when there's no always-on machine (e.g.
  running on GitHub Actions). Key from Google AI Studio, no credit card.
  **This is the default in `.env.example`.**
- **`ollama`** — free, local, offline. Runs a model on your own machine, no key,
  no bill — but needs a computer that's on when the job fires.
- **`anthropic`** — best quality, ~a few dollars/month on prepaid API credits.
- **`openai`** — optional swap; needs its own API credits.

Text-to-speech is likewise swappable via `TTS_PROVIDER`: **`edge`** (free
Microsoft Edge neural voices, no key, works in the cloud), **`say`** (macOS,
offline), or **`elevenlabs`** (paid, highest quality). `auto` picks the best
available.

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
| `CURATE_PROVIDER` / `WRITE_PROVIDER` | No | `gemini` (default, free cloud), `ollama` (free local), `anthropic`, or `openai`. |
| `CURATE_MODEL` / `WRITE_MODEL` | No | Model id per stage. Defaults: `gemini-2.0-flash`. |
| `GEMINI_API_KEY` | If provider is `gemini` | Free key from https://aistudio.google.com/apikey. |
| `OLLAMA_BASE_URL` | No | Local Ollama address. Default `http://localhost:11434`. |
| `ANTHROPIC_API_KEY` | Only if provider is `anthropic` | Curation + writing via the Anthropic API. |
| `OPENAI_API_KEY` | Only if provider is `openai` | Curation + writing via the OpenAI API. |
| `TTS_PROVIDER` | No | `auto` (default), `edge` (free cloud), `say` (macOS), or `elevenlabs`. |
| `EDGE_TTS_VOICE` | No | edge-tts voice. Default `en-GB-RyanNeural` (calm British male). |
| `ELEVENLABS_API_KEY` | No | If unset (and not using edge), narration falls back to macOS `say`. |
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

## Deploy free to the cloud (GitHub Actions + Gemini + Cloudflare R2)

**No always-on computer required.** GitHub Actions is the scheduler — it wakes
up once a day, runs the pipeline on GitHub's machines, and stops. Nothing of
yours runs 24/7. For a public repo, Actions minutes are free and unlimited, so
this whole path costs **$0**: Gemini (free LLM tier), edge-tts (free voice), and
Cloudflare R2 (free 10 GB) to host the MP3 for your phone.

The workflow lives at `.github/workflows/briefing.yml`. One-time setup:

**1. Get a free Gemini API key** — https://aistudio.google.com/apikey (sign in
with Google, "Create API key"; no credit card).

**2. Create a Cloudflare R2 bucket + API token**
- Cloudflare dashboard → **R2** → *Create bucket* (e.g. `jarvis-briefing`).
- R2 → *Manage API Tokens* → *Create API Token* with **Object Read & Write** on
  that bucket. Note the **Access Key ID**, **Secret Access Key**, and your
  **Account ID** (shown in the R2 endpoint `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`).

**3. Add the secrets to GitHub** — repo → *Settings* → *Secrets and variables* →
*Actions* → *New repository secret*:

| Secret | Value |
|--------|-------|
| `GEMINI_API_KEY` | your Gemini key |
| `R2_ACCOUNT_ID` | Cloudflare account id |
| `R2_ACCESS_KEY_ID` | R2 token access key id |
| `R2_SECRET_ACCESS_KEY` | R2 token secret |
| `R2_BUCKET` | bucket name (e.g. `jarvis-briefing`) |

**4. Run it** — *Actions* tab → *Jarvis Briefing* → *Run workflow* to test
immediately, or wait for the daily schedule. Each run uploads a dated
`briefing_YYYY-MM-DD.mp3` **and** overwrites a stable `latest.mp3` in the bucket.

**Schedule / timezone:** the cron is `45 5 * * *` **UTC** = 06:45 CET (winter) /
07:45 CEST (summer) — GitHub cron can't follow DST. Edit the `cron:` line in the
workflow to taste. (Note: GitHub auto-disables scheduled workflows after 60 days
of repo inactivity; a push or a manual run re-arms it.)

### Getting the MP3 to your iPhone (iOS Shortcut)

Point a Shortcut at your bucket's stable `latest.mp3` URL:

1. Make the object reachable — either enable a public **r2.dev** URL / custom
   domain on the bucket, or generate the URL as needed. Your daily file is at
   `https://<your-r2-public-domain>/latest.mp3`.
2. **Shortcuts app** → new shortcut → **Get Contents of URL** (that URL) →
   **Play Sound** (or **Save File**).
3. **Automation** tab → *Personal Automation* → *Time of Day* 6:45am → run the
   shortcut. You wake up, it fetches and plays the morning briefing.

---

## Scheduling a 6:45am run locally (alternative to the cloud)

Use this only if you'd rather run on your own always-on Mac/Linux box instead of
GitHub Actions.

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
