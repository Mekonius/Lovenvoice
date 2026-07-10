# Design doc: Interactive "Jarvis" (conversational briefing)

**Status:** proposal / scoping — no code yet.
**Author:** design notes for whoever builds this next.
**Date:** 2026-07.

---

## 1. The problem

Today's system is a **one-way broadcast**:

```
fetch → curate → write → render fixed MP3 → play via iOS Shortcut
```

The desired experience is a **two-way conversation** — "the Jarvis feel":

> Jarvis reads the morning briefing. Mid-sentence I say *"wait, tell me more
> about that asteroid mission."* He stops, answers, I say *"ok, continue,"* and
> he picks up where he left off. I can also just ask him things.

A pre-rendered MP3 **cannot** be interrupted or answer questions. So the
interactive layer is a genuine redesign — but the existing pipeline is **not
wasted**: it becomes the *content/knowledge* Jarvis speaks from.

---

## 2. What "the Jarvis feel" actually requires

| Capability | Notes |
|---|---|
| **Speak the briefing** | Already solved (curation + writing + TTS). |
| **Barge-in / interrupt** | Detect the user talking over Jarvis and stop playback immediately. This is the single hardest UX bit. |
| **Understand the question** | Speech-to-text on the user's turn. |
| **Answer in context** | The LLM must have *today's stories* (and ideally the source articles) as context, plus general knowledge, to answer follow-ups. |
| **Resume** | Track "where we were" in the briefing and continue on command. |
| **Low latency** | Sub-second response or it feels broken. Rules out slow batch calls. |
| **A place to run in real time** | During a conversation something must hold the session. It does **not** need to be 24/7 — just on-demand when a session starts. |
| **A client on the iPhone** | Mic access + audio playback + interrupt. Ideally no App Store. |
| *(optional)* **Wake phrase / memory** | "Hey Jarvis"; remembering yesterday. Nice-to-have, not core. |

The current architecture provides only row 1. Everything else is new.

---

## 3. The key insight: you already own the hard part

The interruptible-voice-assistant technology is **already included** in the
owner's existing subscriptions:

- **ChatGPT Plus** → Advanced Voice Mode (interrupt, ask anything, scheduled tasks, Custom GPTs).
- **Claude Pro** → Claude voice on mobile + Projects.

⚠️ These subscriptions power the **consumer apps**, *not* the developer API
(building on the API is separately metered — see the README billing note). But
for a *personal* assistant you use yourself, the consumer app is exactly the
interruptible-conversation experience, at no extra cost.

So the real gap is narrow: **feed the daily curated briefing into a voice
assistant that already exists.** That reframes the project from "build a
real-time voice AI" (hard, costly) to "connect my content to one" (easy).

---

## 4. Options

### Option A — Leverage ChatGPT/Claude voice (recommended first step)

Wire the daily curated stories into a **"Jarvis" Custom GPT** (or Claude
Project / scheduled ChatGPT task). Each morning it pulls the day's stories from
R2 or the repo and reads them in **voice mode**; you interrupt, ask, resume.

- **Effort:** low (days). Mostly prompt/config + exposing today's stories as JSON at a stable URL (already have `latest`-style delivery).
- **Cost:** ~$0 beyond existing subscriptions.
- **Runtime/host:** none — the app is the runtime.
- **Client:** the ChatGPT/Claude app you already have.
- **Can do:** greet, read, full barge-in, ask anything, deep follow-ups, general knowledge.
- **Can't do:** custom branding/voice ("Jarvis" persona is only as deep as prompt + app allows); no fully automatic "plays itself at 06:45" — you open the app and say go; ties you to that vendor's app.
- **Best for:** proving the experience *now* and learning what you actually want before investing.

### Option B — Custom real-time Jarvis (the "real" build)

A voice **web-app (PWA)** — add-to-home-screen on iPhone, so it feels native
without the App Store — hosted free on **Cloudflare Pages**. It opens a
**realtime speech session** seeded with today's stories as context and a Jarvis
system prompt.

- **Realtime engine choices:**
  - **Gemini Live API** — real-time, interruptible, has a free tier (aligns with the "keep it free" goal; quotas/availability vary).
  - **OpenAI Realtime API** — best quality speech-to-speech + tool use; **paid**, metered per minute.
  - **ElevenLabs Conversational AI** — great voices; small free tier, then paid.
- **Effort:** high (weeks) — WebRTC/mic, barge-in handling, session state, deployment, seeding context.
- **Cost:** hosting free; the realtime API is free-ish (Gemini) to metered (OpenAI/ElevenLabs).
- **Runtime/host:** the realtime API holds the session; optionally a tiny Cloudflare Worker to mint tokens / inject context. On-demand, not 24/7.
- **Client:** the PWA (own icon on the home screen).
- **Can do:** everything in A, plus full ownership, custom voice/persona, tool use (look things up live), your own wake flow.
- **Can't do:** avoid real engineering + ongoing (small) cost; barge-in tuning is fiddly.
- **Best for:** once the experience is validated and you want it to be truly *yours*.

### Option C — Hybrid stepping-stone

Keep the morning **MP3 read** (works today), and add an **"ask a follow-up"**
voice Q&A button scoped to today's stories.

- **Effort:** medium. Reuses the pipeline for the read; adds a small Q&A surface (could itself be Option A's assistant scoped to today's JSON).
- **Cost:** low.
- **Can do:** keep what works; add questions on top.
- **Can't do:** true mid-read barge-in (the MP3 is still a file); the Q&A is a separate mode you switch into.
- **Best for:** minimal disruption if the current read is "good enough" and you only occasionally want to dig in.

---

## 5. Comparison at a glance

| | A: Use ChatGPT/Claude | B: Custom PWA | C: Hybrid |
|---|---|---|---|
| Effort | Low (days) | High (weeks) | Medium |
| Extra cost | ~$0 | free‑ish → metered | Low |
| Barge-in mid-read | ✅ | ✅ | ⚠️ separate mode |
| Ask follow-ups | ✅ | ✅ | ✅ (in Q&A mode) |
| Custom voice/brand | ⚠️ limited | ✅ | ⚠️ (read is custom, Q&A limited) |
| Auto "plays at 06:45" | ❌ (you open it) | ⚠️ (you open it) | ✅ for the read |
| Vendor lock-in | High | Low | Medium |
| Reuses current pipeline | ✅ (as content) | ✅ (as content) | ✅ (as the read) |

---

## 6. Reuse: what stays no matter what

The current pipeline stays valuable as the **daily knowledge base**:

- Stage 1–2 (**fetch + curate**) already produce the day's editorial selection.
- We should expose the curated stories as **structured JSON at a stable URL**
  (e.g. `stories-latest.json` in R2, alongside `latest.mp3`), including
  `headline`, `why_selected`, `source_link`, and ideally a short body. That
  file is what any interactive Jarvis (A, B, or C) loads as context.
- Stage 3–4 (**write + narrate**) remain the fallback/"just read it" path.

**Smallest enabling step, regardless of option:** add a workflow step that
writes the curated stories (and the script) to R2 as JSON. Cheap, and unblocks
all three options.

---

## 7. Recommended path (phased)

1. **Phase 0 (now):** publish `stories-latest.json` to R2 from the existing run.
2. **Phase 1:** Option A — a "Jarvis" Custom GPT/Project that reads it aloud and
   takes questions. Live in days, ~free. **Validate the experience.**
3. **Phase 2 (only if Phase 1 proves it's worth it):** Option B — the custom PWA
   with a realtime engine, for ownership + branding + a proper "Hey Jarvis" flow.

Phase 1 almost always reveals that the interactive feel is ~80% there with what
you already own, which de-risks the big build.

---

## 8. Open questions / decisions needed

- **Voice engine for Phase 2:** free-but-variable (Gemini Live) vs paid-but-best
  (OpenAI Realtime)? Decide after Phase 1.
- **Language:** English, Danish, or bilingual (understand Danish questions,
  answer in Danish)? The batch pipeline now supports `BRIEFING_LANGUAGE`; the
  realtime engine's Danish quality needs checking.
- **Scope of answers:** only today's stories, or full general knowledge + live
  lookups (tool use)?
- **Persona depth:** how "Jarvis" (name, tone, catchphrases) vs a neutral
  assistant?
- **Automation vs on-demand:** is losing the automatic 06:45 self-play
  acceptable in exchange for interactivity? (A/B require you to open the app.)

---

## 9. Constraints (unchanged)

- iPhone-first; ideally no App Store.
- Keep it free or near-free.
- No always-on server (on-demand sessions are fine).
- Reuse the existing free curation pipeline as the content source.
