# Jarvis Briefing (Lovenvoice)

A personal, hands-off **morning news briefing**. Every morning a GitHub Actions
job fetches good-news/progress stories from RSS feeds, uses an LLM to curate and
write a calm spoken script, narrates it with a natural neural voice, and uploads
an MP3 to Cloudflare R2. An iOS Shortcut (triggered by Siri) plays it from the
phone.

Nothing of the owner's runs 24/7 — GitHub is the scheduler, and the whole thing
runs within free (or effectively free) tiers.

> **New here? Read [How it actually runs today](#how-it-actually-runs-today) first.**
> The code supports several LLM/TTS providers, but production uses a specific
> combination for cost/quota reasons. Don't assume the defaults in the code are
> what's deployed — the GitHub workflow overrides them.

---

## How it actually runs today

This is the **live production configuration** (set in `.github/workflows/briefing.yml`),
not the code defaults:

| Concern | Production choice | Why |
|---|---|---|
| **Scheduler** | GitHub Actions, `cron: "45 5 * * *"` (UTC) + manual dispatch | No always-on machine needed; free on a public repo. 05:45 UTC = 06:45 CET / 07:45 CEST. |
| **LLM (curate + write)** | **Groq** `llama-3.1-8b-instant` | Free, fast, no card. Gemini's free tier returns **0 quota** on most projects, so it's only a fallback. |
| **LLM fallback** | Gemini `gemini-2.0-flash` | Fires only if Groq fails. |
| **TTS** | **Google Cloud TTS**, voice `en-GB-Chirp3-HD-Aoede` (British female) | Most natural voice that stays free within Google's monthly character allowance. |
| **TTS fallback** | edge-tts `en-GB-SoniaNeural` (only if you flip `TTS_PROVIDER=edge`) | Free, no key, but flatter. |
| **Delivery** | Cloudflare R2 via **boto3** (`scripts/r2_upload.py`) → `latest.mp3` | The `aws` CLI does **not** work with R2 (see gotchas). |
| **Playback** | iOS Shortcut named for a Siri phrase, fetches `latest.mp3` | Hands-free from the phone. |

A typical run: ~4–5 min (mostly Groq rate-limit backoff during the write stage)
and produces a ~2 MB MP3 (~10 short stories).

---

## Pipeline

One orchestrator, `briefing.py`, runs four stages. Each stage's raw output is
written to `runs/YYYY-MM-DD/` for debugging.

| Stage | Module | What it does |
|-------|--------|--------------|
| 1. Fetch | `jarvis/fetch.py` | Read RSS feeds from `feeds.yaml`, keep last 24 h, dedupe by title similarity → up to `MAX_CANDIDATES` (18) candidates. Fetches with a browser User-Agent (many feeds 403 the default one). |
| 2. Curate | `jarvis/curate.py` | LLM selects **10** stories (or fewer on a slow day) with an enforced theme + geographic spread, returns strict JSON. Malformed output retries once, then fails loudly. |
| 3. Write | `jarvis/write.py` | LLM writes an intro, **one tight paragraph per story**, and a short "Bigger Picture" closing — one plain-text narration script. Only the intro greets the listener. |
| 4. Narrate | `jarvis/narrate.py` | Synthesises `output/briefing_YYYY-MM-DD.mp3`. Google TTS chunks the script under the 5000-byte limit and stitches the MP3 segments. |

All LLM calls go through one wrapper, `jarvis/llm.py`:
`call(provider, model, system, prompt) -> str`. It handles provider routing,
retry-with-backoff on rate limits (HTTP 429) and transient network errors, and a
single automatic fallback to `FALLBACK_PROVIDER`/`FALLBACK_MODEL`.

Editorial voice and all prompts live in `jarvis/prompts.py`. Central config is
`jarvis/config.py` (a frozen `Settings` dataclass loaded from env/`.env`).

---

## Repository layout

```
briefing.py                     # orchestrator; `python briefing.py [--dry-run]`
feeds.yaml                      # editable RSS source list
requirements.txt
.env.example                    # copy to .env for local runs
scripts/
  r2_upload.py                  # boto3 uploader for Cloudflare R2 (NOT aws CLI)
jarvis/
  config.py                     # Settings dataclass (all env vars live here)
  fetch.py                      # Stage 1
  curate.py                     # Stage 2
  write.py                      # Stage 3
  narrate.py                    # Stage 4 (google / elevenlabs / edge / say)
  llm.py                        # provider wrapper + retry/fallback
  prompts.py                    # editorial + writing prompts
.github/workflows/
  briefing.yml                  # the daily job (this is what runs in production)
  r2-test.yml                   # ~20s manual R2 credential check
  da-voice-test.yml             # manual voice auditioning (edge + Google samples)
runs/YYYY-MM-DD/                # per-run debug artefacts (git-ignored)
output/                         # generated MP3s (git-ignored)
```

---

## GitHub Actions setup (production path)

Scheduled/manual workflows only run from the **default branch (`main`)**, so
changes to a workflow must be merged to `main` before they take effect.

### Required repository secrets

Repo → *Settings* → *Secrets and variables* → *Actions*:

| Secret | Used for |
|--------|----------|
| `GROQ_API_KEY` | Primary LLM (curate + write). Free: https://console.groq.com/keys |
| `GEMINI_API_KEY` | LLM fallback. Free: https://aistudio.google.com/apikey |
| `GOOGLE_TTS_API_KEY` | Google Cloud TTS. Needs billing enabled (see gotchas). https://console.cloud.google.com/apis/credentials |
| `R2_BUCKET` | R2 bucket name (e.g. `jarvis-briefing`) |
| `R2_ACCESS_KEY_ID` | R2 API token Access Key ID (32 hex chars) |
| `R2_SECRET_ACCESS_KEY` | R2 API token Secret Access Key (64 hex chars) |

**Note:** `R2_ACCOUNT_ID` is **hardcoded** in the workflows (it's not a secret —
it's in every R2 endpoint URL). If the account changes, edit the
`R2_ACCOUNT_ID:` line in `briefing.yml`, `r2-test.yml`, and `da-voice-test.yml`.

### Running / verifying

- **Full briefing:** *Actions* → *Jarvis Briefing* → *Run workflow*. Every run
  also attaches the MP3 as a `briefing-audio` artifact (works even with no R2).
- **R2 credentials only** (~20 s): *Actions* → *R2 Test* → *Run workflow*.
- **Audition voices:** *Actions* → *Danish Voice Test* → *Run workflow*. Uploads
  samples to R2 (`da-google-hd.mp3`, `en-google-hd-gb.mp3`, etc.) so you can play
  them from the bucket's public URL.

---

## Delivery + iOS Shortcut

Each successful run uploads two objects to R2: a dated archive
`briefing_YYYY-MM-DD.mp3` and a stable **`latest.mp3`** (with `Cache-Control:
no-cache`). The bucket has a public **r2.dev** development URL enabled, so the
file is reachable at:

```
https://pub-<hash>.r2.dev/latest.mp3
```

The iOS Shortcut (the name **is** the Siri trigger phrase, e.g. "Godmorgen Jarvis"):

1. **Get Contents of URL** → the `latest.mp3` URL above
2. **Play Sound**
3. Optionally, a *Time of Day* Automation to run it each morning.

Danish Siri phrases need Siri's language set to Danish, and the phrase must be
distinctive (avoid generic words like "news"/"nyheder", which Siri hijacks).

---

## Local development

Requires **Python 3.11+**.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in keys

python briefing.py --dry-run   # runs fetch→curate→write, prints script, NO audio/TTS
python briefing.py             # full run → output/briefing_YYYY-MM-DD.mp3
```

`--dry-run` is the fast loop for editing prompts/curation without spending TTS
quota. To mirror production locally, set in `.env`:

```
CURATE_PROVIDER=groq
WRITE_PROVIDER=groq
CURATE_MODEL=llama-3.1-8b-instant
WRITE_MODEL=llama-3.1-8b-instant
GROQ_API_KEY=...
TTS_PROVIDER=google
GOOGLE_TTS_VOICE=en-GB-Chirp3-HD-Aoede
GOOGLE_TTS_API_KEY=...
```

> **Sandbox note:** edge-tts and some outbound hosts may be blocked behind a
> proxy in restricted environments — TTS that works in GitHub Actions can fail
> locally. Prefer verifying TTS changes via the `da-voice-test.yml` workflow.

---

## Configuration reference (`jarvis/config.py` / `.env`)

| Env var | Default | Purpose |
|---|---|---|
| `CURATE_PROVIDER` / `WRITE_PROVIDER` | `anthropic` (code) / `groq` (prod) | `groq`, `gemini`, `anthropic`, `openai`, `ollama`. |
| `CURATE_MODEL` / `WRITE_MODEL` | `claude-sonnet-5` (code) | Model id per stage. |
| `GROQ_API_KEY` | — | Groq key (primary LLM in prod). |
| `GEMINI_API_KEY` | — | Gemini key (fallback in prod). |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | — | Only if that provider is selected. |
| `FALLBACK_PROVIDER` / `FALLBACK_MODEL` | `groq` / `llama-3.3-70b-versatile` | One-shot retry target; only fires if its key is present. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama (keyless, offline). |
| `TTS_PROVIDER` | `auto` (code) / `google` (prod) | `google`, `elevenlabs`, `edge`, `say`, or `auto` (elevenlabs→edge→say). |
| `GOOGLE_TTS_API_KEY` | — | Google Cloud TTS key (billing must be enabled). |
| `GOOGLE_TTS_VOICE` | `en-GB-Chirp3-HD-Aoede` | Any Google voice id. Swap for `en-US-Chirp3-HD-Aoede`, `da-DK-Chirp3-HD-Aoede`, etc. |
| `EDGE_TTS_VOICE` | `en-GB-RyanNeural` | edge-tts voice (fallback). |
| `ELEVENLABS_*` | — | Optional paid TTS (`_API_KEY`, `_VOICE_ID`, `_MODEL_ID`, `_OUTPUT_FORMAT`). |
| `LISTENER_NAME` | `Kenneth` | Used in the intro greeting. |
| `BRIEFING_TIMEZONE` | `Europe/Copenhagen` | IANA tz for the intro time + filenames. |

The LLM wrapper imports SDKs lazily — `anthropic`/`openai` are only imported when
selected; `groq`/`gemini`/`ollama` use plain `requests`.

---

## Feeds

Edit `feeds.yaml` — no code changes needed. `name` becomes each story's
`source`. A feed that fails to load is logged and skipped (one bad URL won't
break the run). Leans science / health / climate / tech / space plus
solutions-journalism desks.

```yaml
feeds:
  - name: Nature News
    url: https://www.nature.com/nature.rss
```

---

## Gotchas & lessons learned

Read these before changing the delivery or TTS paths — each cost real debugging
time.

- **Cloudflare R2 hates the aws CLI.** `aws s3 cp` fails against R2 with
  `SignatureDoesNotMatch` (aws-cli v2 adds flexible-checksum trailers R2 doesn't
  fold into its SigV4 signature). **Always use `scripts/r2_upload.py`** (boto3
  with `request/response_checksum_calculation=when_required`). Verify creds fast
  with the `r2-test.yml` workflow.
- **`SignatureDoesNotMatch` can also be a mismatched key pair.** R2 shows the
  secret only once at token-creation. If access-key and secret come from
  different tokens, you get the same error — recreate the token and copy both
  from the same screen.
- **Google Cloud TTS requires billing enabled**, even for the free tier — a card
  must be on file (unlike Gemini/AI-Studio keys). Symptom: `403 "This API method
  requires billing to be enabled."` Enable billing on the *exact project the key
  belongs to*, and make sure the billing account status is **Active** (not
  Closed/pending). Usage stays $0 within the monthly character allowance; set a
  budget alert / quota cap to be safe.
- **Google TTS has a 5000-byte per-request limit.** A full briefing is longer,
  so `narrate.py` chunks on sentence boundaries and concatenates the MP3s. Keep
  `_GOOGLE_MAX_BYTES` well under 5000.
- **Groq free tier has three separate limits:** ~6k tokens/**minute** (TPM),
  a per-**day** cap (much larger on 8B than 70B), and a per-**request** size
  cap (413 if a single request is too big). Mitigations already in place: 8B for
  both stages, `MAX_CANDIDATES=18`, trimmed summaries, `_MAX_TOKENS=2048`, and
  retry-with-backoff. Expect the write stage to pause on 429s — that's normal.
- **Gemini free tier is often 0-quota** (`limit: 0`) — usable only as a fallback.
- **`continue-on-error` masks failures.** An earlier R2 step used it and reported
  green while the upload actually failed (the phone got a 404). Prefer failing
  loudly; the boto3 uploader now does.
- **Stanford News feed 403s** even with a browser UA — it's logged and skipped.
  Fine to leave or remove from `feeds.yaml`.
- **Near-duplicate stories** can slip past dedup (same event, different titles —
  e.g. two Tianwen-2 framings). Dedup is title-similarity only; tightening it to
  match on shared key terms is an open improvement.
- **Long tool outputs / artifacts** from GitHub in a sandbox: the log-artifact
  download URLs (Azure blob) may be proxy-blocked. Use `get_job_logs` (tail) to
  inspect runs instead of downloading `run-logs`.

---

## Debugging a run

Look in `runs/YYYY-MM-DD/` (also uploaded as the `run-logs` artifact):

- `01_candidates.json` — everything Stage 1 fetched.
- `02_curated_raw.txt` — the model's raw curation response.
- `02_curated.json` — the validated stories (with `why_selected`).
- `03_script.txt` — the final narration script.

The `Generate briefing` step log shows the per-story progress, the assembled
character count, and the TTS provider/chunk count.

---

## Ideas / open work

- Tighten dedup to catch near-duplicate *events*, not just similar titles.
- Optional full **Danish** briefing (translate the writer prompts; switch voice
  to `da-DK-Chirp3-HD-Aoede`). Today the voice can speak Danish but the content
  is written in English.
- An OpenAI/cheap-model **triage** layer between Stage 1 and Stage 2 if feed
  volume ever grows to hundreds of candidates (add `jarvis/triage.py`, one line
  in `briefing.py`).
