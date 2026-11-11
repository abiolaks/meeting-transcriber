# Local Meeting Transcriber — Specification v0.3.4

Status: draft for review. v0.3 pins the Windows target to a specific CPU and
downgrades the performance promise accordingly. v0.3.1 corrects the time budget.
v0.3.2 confirms the 16 GB configuration. v0.3.3 fixes the channel-handling
strategy. v0.3.4 makes the quantisation policy explicit.
Everything marked **[ASSUMPTION]** needs confirmation or rejection.

### Changelog

- **v0.3.4** — Quantisation policy written down (§7-S7). Model file names and
  sizes verified against the upstream repo; the spec previously said "int8" while
  sizing downloads at f16 — that contradiction is resolved. ASR weights are
  quantised only if measurably faster at ≤ 1 WER point, because 16 GB removes the
  memory argument; the LLM stays `Q4_K_M` unconditionally.
- **v0.3.3** — Single-user optimisation pass. **Per-channel transcription replaces
  channel mixing** (§7-S3) — mixing injects mic noise into the clean loopback
  signal and was costing accuracy. Switches defaults to `.en` models. Raises the
  quality expectation (§7-S6) now that the audio path is known to be pristine on
  the remote side. Adds `TUNING.md` with the measurement protocol and targets.
- **v0.3.2** — Target laptop confirmed: **15.9 GiB usable = 16 GB** (A7 resolved).
  WMI reports `MaxClockSpeed = 2112 MHz`, far below the 4.2 GHz spec, which
  suggests a power-plan or OEM cap. Adds §4 clock-speed risk and
  `bench/check-power.ps1`; Phase 0 now starts with that check.
- **v0.3.1** — Adds a worked end-to-end time budget (§4) and the two scheduling
  modes (I: cheap live / expensive final; II: expensive live / no re-run).
  Corrects A3 from "~20 minutes" to **35–45 minutes** — the earlier figure
  ignored the cost of word timestamps and assumed the ASR and LLM stages overlap.
  Flags that Phase 0 benchmarks must include timestamp generation.
- **v0.3** — Windows target pinned: Intel Core i7-8650U (2017, 4C/8T, 15 W),
  Tier C. `large-v3-turbo` final pass is **not viable** on this machine; `small`
  becomes the default. LLM drops to 3B with a hard output-token budget.
  The 5-minute notes promise is withdrawn; ~20 minutes is the honest target.
- **v0.2** — Windows target is 16 GB Intel. LLM may be resident during a meeting.
  Live *draft* notes become an opt-in feature. ASR default raised to `small` live /
  `turbo` final. 8B reprocess mode added. Degradation ladder reduced to 2 steps.
  CPU class (U vs H series) promoted to a first-class requirement.
- **v0.1** — initial draft, 8 GB target, strictly sequential ASR/LLM.

## 1. What this is

A background application for Windows, macOS and Linux that records the audio of a
remote meeting (Zoom, Microsoft Teams, Google Meet), transcribes it on-device,
and produces a readable, well-sectioned meeting note: what was discussed, what
was decided, what needs to be done, by whom, by when.

No network access at runtime. No cloud. No account.

### The one job to be done

> "Let me understand what happened in that meeting, without watching it again,
>  and without losing track of what was actually said."

Two consequences that drive the whole design:

1. **Comprehension, not verbatim fidelity, is the product.** The note is the
   deliverable; the transcript is supporting evidence.
2. **Nothing may be silently lost.** Every claim in the note must be traceable
   to a timestamped span in the recording. A wrong-but-confident action item is
   worse than a missing one.

## 2. Locked decisions

| # | Decision | Value |
|---|---|---|
| D1 | Language | English only, v1 |
| D2 | Offline | Runtime only. First run downloads weights. |
| D3 | Primary target | Windows x64, Intel **Core i7-8650U**, 4C/8T, 15 W, 16 GB RAM [A7] |
| D4 | Secondary target | macOS Apple Silicon, 16 GB (dev/reference machine) |
| D5 | Meeting type | Remote, joined on the same laptop |
| D6 | Live behaviour | Live transcript yes; live **draft** notes opt-in; final note after stop |
| D7 | Synthesis timing | Authoritative synthesis after the user presses stop |
| D8 | Speaker split | Mic = local user; loopback = remote participants |
| D9 | Visual context (shared screen) | **Out of scope v1** [ASSUMPTION A1] |
| D10 | Distribution | Installable desktop app, signed where the OS requires it |

## 3. Assumptions to confirm

- **A1** "What I'm seeing" in the brief means *understanding the conversation*,
  not capturing shared-screen pixels. Visual context is a separate feature.
- **A2** Speaker *names* are not required in v1. "You" / "Remote participant 1..N"
  plus a manual rename box is acceptable.
- **A3** A 60-minute meeting yields its note **35–45 minutes after stop** on the
  target i7-8650U, and within ~15 minutes on Apple Silicon. Under Mode II
  (§4, "expensive live") the wait drops to 5–12 minutes at some cost in quality.
  **Do not promise anything faster than this on Tier C.**
  [corrected in v0.3.1 — the earlier "20 minutes" ignored ASR timestamps and
  assumed stages overlap; see the worked budget in §4]
- **A4** Typical meeting length is 15–90 minutes, hard cap 3 hours.
- **A5** Users can be asked to wear headphones — this gives a free 2-channel
  speaker split and avoids echo.
- **A6** Confirmed target: **Intel Core i7-8650U** (Kaby Lake-R, 2017), 4 cores /
  8 threads, 1.9 GHz base, 4.2 GHz max turbo, 15 W TDP, AVX2, Intel UHD 620.
  This is **Tier C** in the table in §4. It has ~1/4 the sustained compute of a
  current 45 W H-series part. Performance promises must be written for this CPU,
  not for the developer's M2.
- **A7** **Confirmed 2026-11-11:** the target laptop reports 17,053,384,704 bytes
  of physical memory = **15.9 GiB usable**, i.e. 16 GB. The co-residency allowance
  in §4 therefore stands. (Had it been 8 GB, v0.1's strictly-sequential rule would
  have returned.)
- **A8** Installing a background app that taps system audio on a *work* laptop is
  permitted by IT. Endpoint protection, application allow-listing, and unsigned
  binaries are all plausible blockers. **This is a bigger risk than the CPU.**

## 4. The binding constraint: CPU, not RAM

At 16 GB the memory budget is comfortable. The CPU is now the limit.

Resident-memory budget during a meeting:

| Component | Resident |
|---|---|
| Windows 11 + services | 3.5 – 4.5 GB |
| Teams / Zoom / browser (Meet) | 1.0 – 1.8 GB |
| Our app: Python sidecar, SQLite, UI | 0.3 – 0.4 GB |
| Audio buffers + Silero VAD | ~0.05 GB |
| ASR `small` int8 (live and final) | ~0.4 GB |
| LLM 3B Q4_K_M + 4k KV | ~2.2 GB |
| **Total, live** | **~8 – 9 GB** |
| **Total, final pass with 3B** | **~8.5 – 9.5 GB** |

Peak stays under 10 GB, leaving ~6 GB headroom. Co-residency of ASR and LLM is
therefore *memory*-affordable on a 16 GB machine [A7] — but not on 8 GB. On the
i7-8650U the real limit is **sustained CPU**, and both engines idle at zero when
not decoding, so co-residency is safe as long as only one decodes at a time.

> **Invariant I1.** The recording path must never block on, wait for, or be
> preempted by any ML task. Audio writing has the highest priority in the process.

> **Invariant I2.** Raw audio is always written to disk before any processing.
> Every later stage is re-runnable from the recording alone.

> **Invariant I3.** Only one ML engine decodes at a time. Model loads are
> serialised behind a single loader lock.

I2 matters enormously on this hardware: it means a slow CPU costs you *time*,
never *data*, and any meeting can be reprocessed later on a faster machine.

### CPU tiering

| Tier | Example | Live ASR | Final ASR | LLM |
|---|---|---|---|---|
| **A — fast** | M-series Mac, H-series i7/i9 ≥6P | `small` | `large-v3-turbo` | 4B, 8B reprocess |
| **B — capable** | Modern U-series, 4P+8E | `small` | `medium` | 4B |
| **C — target** | **i7-8650U, 4C/8T, 15 W** | `base`, `small` if it holds | **`small`**, `medium` overnight | **3B only** |
| **D — floor** | 4C, pre-2018 | `base` | `small` | 1.7B, final pass only |

Tier is auto-detected at first run by a 20-second micro-benchmark (a fixed 60 s
audio clip through `base`), cached, and overridable in settings.

### Measured expectations for the target CPU

Estimates from published RTF figures for 4-core 15 W Kaby Lake-U parts. These are
**hypotheses, not measurements** — Phase 0 replaces them with real numbers.
Whisper.cpp int8, 4 threads, sustained (i.e. after throttling):

| Model | RTF | 60-min meeting | Verdict |
|---|---|---|---|
| `base` | 0.15 – 0.25 | 9 – 15 min | fine, quality is marginal |
| `small` | 0.40 – 0.60 | 24 – 36 min | **default final pass** |
| `medium` | 1.0 – 1.4 | 60 – 84 min | "overnight / batch" only |
| `large-v3-turbo` | 1.1 – 1.6 | 66 – 96 min | **not viable — withdrawn** |

The reason `turbo` is not the answer here: it is a *large* encoder with a
four-layer decoder. The encoder dominates runtime and does not shrink, so the
decoder savings that make turbo fast on GPU buy almost nothing on a weak CPU.
Turbo ≈ `medium` on this machine.

#### Unverified risk: is the CPU allowed to boost?

The target laptop reports `MaxClockSpeed = 2112 MHz`. The i7-8650U is rated to
4.2 GHz. 2112 MHz is only 11% above base clock, which is the signature of:

- a power plan capped at < 100% maximum processor state,
- "Processor performance boost mode" disabled,
- an OEM thermal profile set to Quiet/Cool,
- a BIOS power limit, or
- a corporate image that pins clocks on purpose.

**If the machine is genuinely pinned near 2.1 GHz, every figure in the table above
degrades by roughly 1.4–1.5×**, and the `small` final pass becomes 36–54 minutes
instead of 25–37 — which fails gate 1 in §17. This must be settled *before* the
benchmark, because a benchmark run on a capped machine measures the cap, not the
CPU.

`bench/check-power.ps1` answers this in about a minute: it samples
`\Processor Information(_Total)\% Processor Performance` at idle and under
full-core load. Values near 100% mean pinned; 150%+ means boost is working.

The 15 W envelope still limits sustained clocks to roughly 2.2–3.0 GHz on a thin
laptop even when everything is configured correctly. Plan on the sustained number,
never the peak.

#### What RTF means

RTF (realtime factor) is *processing time divided by audio duration*.

- RTF 0.40 → 1 minute of audio costs 24 seconds of CPU → a 60-minute meeting costs
  24 minutes.
- RTF 1.00 → the machine is exactly as slow as the people talking.
- RTF > 1.0 → processing takes longer than the meeting itself took.

So "`small` = 0.40–0.60" reads as: **the laptop needs between 40% and 60% of the
meeting's length, again, to grind through the recording.** One hour of meeting →
roughly half an hour of fan-spinning.

#### Worked end-to-end budget for a 60-minute meeting

| Stage | Rate on Tier C | Cost |
|---|---|---|
| ASR `small`, int8, 4 threads, **with word timestamps** | RTF 0.42 – 0.62 | 25 – 37 min |
| Alignment / channel merge / diarization | — | 1 – 3 min |
| LLM 3B: ≤12k prompt in, ≤1.5k tokens out | 6–9 tok/s gen | 5 – 10 min |
| **Total, press-stop to note** | | **31 – 50 min** |

Two things this table corrects:

1. **Word timestamps are not free.** Producing them costs roughly 10–20% extra
   over a plain transcription run. Benchmarks run without `--output-words-style`
   or token timestamps will *understate* the product's real cost. The Phase 0
   script must measure the flags the product actually uses.
2. **A3 in §3 said ~20 minutes. That was wrong.** It was written before the ASR
   and LLM numbers were worked out together, and it silently assumed the stages
   overlap and the timestamps are free. The honest figure is ~35–45 minutes for a
   60-minute meeting, and A3 is corrected accordingly.

#### The wait is a scheduling choice, not a law

The same total compute can be spent at different times. There are two coherent
products, and they differ only in *when* the expensive ASR runs:

| | Mode I — "cheap live, expensive final" | Mode II — "expensive live, no re-run" |
|---|---|---|
| Live ASR | `base`, ~20% CPU | `small`, ~50–60% CPU |
| Final ASR | re-run `small` over the whole file | **reuse the live transcript** |
| Wait after stop | 30–40 min | 5–12 min (LLM only) |
| Meeting experience | laptop stays cool and responsive | fan audible, Teams competes for cores |
| Quality | better — full-file context, second attempt, no dropped segments | worse — live chunks miss context, crosstalk suffers |
| Risk | you wait | a dropped live segment is permanent |

Mode I is the spec's default because it protects the meeting itself (Invariant I1)
and gives the best notes. Mode II is what you choose when "I want the summary
before I leave the room" matters more than the last 5% of accuracy. Both are the
same pipeline with a different schedule — this is the original "live vs. after"
question from the brief, showing up again as a compute-allocation decision rather
than an architecture one.

Neither mode makes the laptop faster. Only a smaller model (worse notes), a
server (Mode B in `DEPLOYMENT.md`), or different hardware does that.

#### Optimisation targets for the single test user

Measured on the target i7-8650U, 60-minute meeting, Mode I:

| Metric | Acceptable | Good | Reject |
|---|---|---|---|
| ASR RTF (`small.en`, 4 threads, timestamps on) | ≤ 0.55 | ≤ 0.40 | > 0.65 |
| WER, remote channel | ≤ 14% | ≤ 10% | > 20% |
| WER, local mic channel | ≤ 22% | ≤ 16% | > 30% |
| End-to-end, stop → note | ≤ 45 min | ≤ 30 min | > 55 min |
| Action-item precision | ≥ 0.80 | ≥ 0.90 | < 0.65 |
| Note comprehension (10 questions, note only) | ≥ 7/10 | ≥ 9/10 | < 5/10 |

The protocol for hitting these, and every knob that moves them, is in
`TUNING.md`. Do not tune by intuition — each change below is either measured or
it does not ship.

LLM throughput (3B Q4_K_M, 4 threads): ~6–9 tok/s generation, ~18–25 tok/s
prompt processing. This is tight enough that §9 imposes a hard token budget.

### Degradation ladder

Two steps only. Sampled every 5 s; steps down, never up mid-meeting.

1. **Normal** — everything on.
2. **Constrained** — suspend live draft notes, drop live ASR to `base`, reduce UI
   refresh, keep recording.

Recording itself is never degraded. If the process is killed, at most 60 s of
audio is lost.

### Smoothness requirements

"As smooth as it can" is specified as behaviour, not vibes:

- **S1** All ML work runs at *below normal* process priority. Audio capture runs
  at *above normal*. The meeting app must never stutter because of us.
- **S2** Thread count is capped to physical P-cores, minus one, so the meeting
  app always has a core.
- **S3** The final pass waits until `stop` + 3 s, so UI teardown finishes first.
- **S4** Final pass checks power state: on battery it defers unless the user says
  "process now", and warns about battery drain.
- **S5** Thermal guard: if the CPU has been at ~100% for > 2 minutes and the
  throttle flag is set, reduce to 2 threads and tell the user ETA will slip.
- **S6** Never quantise the audio path to save CPU. Capture fidelity is fixed.

## 5. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ CAPTURE                                                    │
│  mic ──────────────► ch0 (You)                             │
│  system loopback ──► ch1 (Remote)      WASAPI / SCK / Pulse │
└───────────────────────┬──────────────────────────────────────┘
                        ▼
              WAV writer (16 kHz mono per channel, PCM16)
              + 60 s rolling segments, flushed to disk
                        ▼
┌──────────────────────────────────────────────────────────────┐
│ LIVE (low latency, expendable)                             │
│  Silero VAD → segment → whisper.cpp small → caption stream │
│  optional: append-only DRAFT note per completed section    │
└───────────────────────┬──────────────────────────────────────┘
                        ▼  user presses STOP
┌──────────────────────────────────────────────────────────────┐
│ FINAL PASS (authoritative, sequential model loads)         │
│  1. transcribe ch0 and ch1 SEPARATELY (never mix)          │
│  2. word timestamps + per-channel attribution, merge by ts │
│  3. transcript normalisation, paragraph assembly           │
│  4. chunk → extractive candidates → tiny LLM → merge       │
│  5. verifier: every claim anchored to a timestamped quote  │
│  6. render note + transcript → SQLite + Markdown/JSON      │
└──────────────────────────────────────────────────────────────┘
```

The live draft from step "LIVE" is **discarded** at the start of the final pass.
It exists to reassure the user, not to feed the result.

## 6. Capture

The hard, platform-specific part. Most of the porting effort lives here.

| OS | Remote audio | Local mic | Notes |
|---|---|---|---|
| Windows | WASAPI loopback on default render device | WASAPI input | No permission prompt. Primary target. |
| macOS 13+ | ScreenCaptureKit system audio | CoreAudio | Screen-recording permission; user must re-grant after some updates. |
| macOS < 13 | BlackHole 2ch virtual device | CoreAudio | Documented fallback only. |
| Linux | PulseAudio/PipeWire monitor source | ALSA/Pulse | Easy on PipeWire; document quirks. |

Rules:

- **C1** Prefer the OS-native loopback. Do not install kernel drivers.
- **C2** Capture both channels independently; never rely on the meeting app's own
  recording (it truncates, compresses, and sometimes needs host permission).
- **C3** Detect and warn about speakerphone use (echo → duplicated speech). Detect
  by correlating ch0 and ch1 energy envelope.
- **C4** Write audio incrementally; a crash loses at most 60 s.
- **C5** Show a live level meter per channel. Silence on the remote channel is the
  #1 support issue — surface it during the meeting, not after.
- **C6** No auto-start on meeting detection in v1; user starts and stops explicitly.
- **C7** Handle audio device changes mid-meeting (headset plugged in, Bluetooth
  switched) without dropping the recording — resample and continue.

## 7. Speech recognition

Single runtime: **whisper.cpp** (static binary per platform, AVX2/Vulkan/Metal,
no Python ML stack, no PyTorch).

| Pass | Model | Why |
|---|---|---|
| Live | `ggml-base.en-q5_1` (60 MB) | Tier C cannot afford `small` live *and* a responsive UI |
| Final | **`ggml-small.en-q5_1`** (190 MB) | Only model that clears ~30 min for a 60-min meeting on this CPU |
| Batch | `ggml-medium.en-q5_0` (539 MB), user-initiated | "Leave it running overnight" quality option |
| Reprocess | `large-v3-turbo`, different machine | Not viable on i7-8650U — see §4 |

Exact sizes verified against `ggerganov/whisper.cpp` on 2026-11-11. Note the
naming is not uniform: `small` and `base` ship `q5_1`, while `medium` and
`large-v3-turbo` ship `q5_0`. Do not assume the suffix.

- **S1** No PyTorch anywhere in the product. Keeps installer near ~150 MB and the
  resident set small.
- **S2** Word-level timestamps are mandatory — they anchor citations.
- **S3** **Transcribe the two channels separately and never mix them.** Mixing adds
  the noisy mic signal to the clean loopback signal and makes the remote
  participants *harder* to hear. Per-channel transcription gives four wins at
  roughly zero cost, because the two channels' speech rarely fully overlaps:

  1. remote audio stays pristine (the loopback is a decoded digital stream, not a
     room recording — this is the single biggest accuracy advantage the
     architecture has);
  2. silence on one channel is skipped independently, offsetting the extra decodes;
  3. speaker attribution falls out of which channel the words came from;
  4. echo (speakerphone use) shows up as duplicated text and can be detected and
     dropped deterministically, instead of being baked into a mixed signal.

  Merge by timestamp afterwards; on overlap, keep both, interleaved.
- **S4** Optional speaker clustering *within* the remote channel (ONNX speaker
  embeddings + simple clustering) produces "Remote 1..N". Off by default; the
  16 GB headroom makes it affordable, but it is a quality feature, not a v1 must.
- **S5** Prompt/initial-prompt seeding (`--prompt`) with attendee names, product
  names and domain jargon, taken from a per-user glossary. Free WER improvement on
  proper nouns, which are exactly the words that matter in a meeting note.
- **S6** `small.en` has a real ceiling, but it is higher than v0.3 assumed.
  On clean loopback audio expect ~8–12% WER; the local mic channel is the weak
  one (room echo, keyboard, fan). The earlier 12–18% figure was a far-field
  estimate and was too pessimistic for this architecture.
- **S7 — Quantisation policy.** ASR weights are quantised **only if they measure
  faster**. On a 16 GB machine there is no memory pressure to relieve: `small.en`
  at f16 is 488 MB, and even `medium.en` at f16 is 1.5 GB. Quantisation here buys
  *bandwidth*, not headroom, and on AVX2 without VNNI the speedup is modest and
  not guaranteed. Therefore: A/B `q5_1` against f16 on the gold clip; keep `q5_1`
  only if it is ≥ 10% faster at ≤ 1 WER point of cost, otherwise ship f16.
  Never `q4_*` for ASR — the quality loss lands on rare words, which are exactly
  the names and terms a meeting note depends on.
  The LLM is different: quantisation there is mandatory, not a trade-off.

## 8. Segmentation and paragraphing

"well sectioned into paragraphs so we don't lose sight of what was said" is a
rendering contract, not a summarisation one.

- **P1** *Paragraph assembly is deterministic from the transcript.* Merge
  consecutive same-speaker turns until ≥ 45 words or ≥ 45 s; never cross a
  channel boundary mid-paragraph.
- **P2** *Section boundaries are proposed by the LLM*, which sees only chunk
  summaries and timestamps — then the renderer **cuts the verbatim transcript at
  those timestamps**. The LLM never rewrites transcript text.
- **P3** Each paragraph carries `[hh:mm:ss]` and a speaker label.
- **P4** Target section length: 2–6 minutes of meeting time. If the LLM proposes
  fewer than 3 sections for a 45-minute meeting, re-segment.

P2 is the design trick that makes sectioning both meaningful and faithful: the
model decides *where the cuts go*, never *what the words are*.

## 9. Synthesis (the small model)

Runtime: **llama.cpp** server, GBNF grammar-constrained JSON. Default model
**3B-class Q4_K_M**. 4B is allowed on Tier A/B; 8B is not supported on the target
CPU at all.

### The token budget is the design constraint

At ~6–9 tok/s generation on the i7-8650U, every output token costs ~0.13 s. That
makes a 60-minute meeting affordable only if total generation stays small:

> **T1.** Total LLM *output* for a 60-minute meeting: **≤ 1,500 tokens**.
> **T2.** Total LLM *prompt* processed: **≤ 12,000 tokens** (chunked, never one call).
> **T3.** Any stage that would exceed T1/T2 is redesigned, not given more time.

Corollary: **the LLM is not allowed to read the whole transcript.** The extractive
pass must be done mostly *without* the LLM — regex/keyword cues ("I'll", "we
decided", "by Friday", "can you", "let's", numbers, dates) plus speaker-turn
structure do the candidate finding, and the model only filters and formats. This
is the difference between a note in 20 minutes and a note in 90.

Three passes, all on chunked input:

1. **Extract** — per ~1,500-token window with 200-token overlap, pull:
   commitments, decisions, open questions, numbers/dates, named entities.
   Each item carries its source span. Cheap deterministic cue-matching narrows
   each window to a handful of candidate sentences *before* the model sees it.
2. **Merge** — dedupe near-identical items, resolve contradictions ("we'll ship
   Friday" vs "actually Monday" → keep the later, note the change), cap at 25
   action items and 12 decisions.
3. **Verify** — a candidate survives only if its `quote` is a normalised verbatim
   substring of the transcript. Failing items are demoted to "Unverified",
   never silently kept.

Action item schema:

```json
{
  "owner": "string|null",
  "owner_confidence": "stated|inferred|unassigned",
  "action": "string",
  "due": "YYYY-MM-DD|null",
  "due_text": "string|null",
  "quote": "exact transcript substring",
  "start_ts": 1382.4,
  "end_ts": 1391.0
}
```

Owner resolution: only `stated` ("I'll…", "Sam will…", "can you…") counts.
`inferred` items are grouped under "Suspected, confirm"; anything else goes to
"Unassigned". **Precision over recall** — an invented owner destroys trust faster
than a missed one.

### Live draft notes (opt-in; unavailable on Tier C)

On the i7-8650U this feature is **disabled and hidden**, not merely off by default:
running a 3B model mid-meeting would compete with the live ASR and the meeting
app for the same four cores, which is exactly the stutter Invariant I1 exists to
prevent. Tier A/B may enable it.

- Runs only on *completed* sections, never the in-progress one.
- Append-only. Prior output is never rewritten.
- Rendered in a panel stamped **DRAFT — not the final note**.
- Automatically suspended when free RAM < 2.5 GB or CPU pressure is high.
- **Discarded entirely** when the final pass starts.
- Default: **off**.

## 10. Output format

The deliverable, as Markdown (also stored as structured JSON):

```markdown
# Weekly sync — 12 Nov, 42 min

**At a glance**
- Billing migration slips one week; root cause is the Stripe webhook retry.
- Agreed to freeze feature work until the 20th.

## 00:00 – 08:30  Billing migration status
Sam walked through the current state...

> "The retry queue is the only thing that can still bite us." — [00:06:12]

## 08:30 – 21:00  Scope for the freeze
...

## Decisions
| # | Decision | Time |
|---|---|---|

## Action items
| Owner | Action | Due | Source |
|---|---|---|---|
| Sam | Fix webhook retry backoff | 15 Nov | [00:06:40] |
| Unassigned | Confirm Stripe sandbox access | — | [00:18:02] |

## Open questions
...

## Transcript
### 00:00  You
...
```

## 11. Storage

- SQLite: `meetings`, `segments`, `paragraphs`, `items`, `models`.
- Audio: `.wav` during recording, converted to Opus after the final pass.
  ~115 MB/hour as 16 kHz mono PCM16; ~30 MB/hour Opus.
- Retention: keep audio 30 days by default, user-configurable; deleting the note
  deletes its audio. A "keep audio" toggle exists because reprocessing needs it.
- All paths under a single data root; export = note + optional audio.

## 12. Install and model management

- **M1** Installer ships code only (~150 MB). No weights bundled.
- **M2** First-run wizard: check disk (needs ~6 GB free for the default set),
  download from a versioned manifest with SHA-256, resumable, proxy-aware,
  retry with backoff.
- **M3** Manifest is signed and pinned; models are versioned and swappable
  without an app update.
- **M4** "Verify and repair" re-hashes local weights.
- **M5** Runtime makes **zero** network calls — enforced by a test that blocks
  sockets in the pipeline process. No telemetry, no crash upload, no
  auto-update ping in v1.
- **M6** Manual side-load from a file for air-gapped machines.

Default model set on the target machine (sizes verified 2026-11-11):
`ggml-small.en-q5_1` 190 MB + 3B Q4_K_M ~2.0 GB + `ggml-base.en-q5_1` 60 MB +
Silero VAD ≈ **2.3 GB**. Because §7-S7 allows f16 for ASR if it measures faster,
the download may grow to ~2.6 GB — still well within budget either way.

`medium.en` (539 MB quantised / 1.5 GB f16) and `large-v3-turbo` are optional
downloads for people who want to run a batch pass overnight or reprocess on
better hardware; neither is part of the default experience on Tier C.

**Use the `.en` variants, not the multilingual ones.** English-only builds are
slightly more accurate on English at the same size and cost — this is a free win
for a product that has already committed to English (D1).

## 13. Packaging and platforms

| Layer | Choice | Rationale |
|---|---|---|
| Core pipeline | Python 3.11 sidecar, no torch | Fast to build; ML lives in native binaries |
| ASR | bundled whisper.cpp | Static, no deps |
| LLM | bundled llama.cpp server | Static, no deps |
| Storage | SQLite (WAL) | Zero-admin |
| UI shell | Tauri (fallback: Electron for the Phase 1 spike) | Small resident set |
| Audio | `pyaudiowpatch` (Win), `sounddevice` (mac/Linux) | Loopback + mic |
| Decoding imports | ffmpeg (bundled) | Audio/video file import |

- **X1** Windows x64 only in v1. No ARM64 Windows.
- **X2** macOS: universal binary, notarised, hardened runtime.
- **X3** Linux: AppImage plus `.deb`; PipeWire assumed.
- **X4** Rust toolchain is *not* installed on the dev machine — Phase 2 setup task.

## 14. Accuracy strategy

Accuracy is attacked in this order, because that is the order of impact:

1. **Capture** — channel separation, echo avoidance, level warnings.
2. **ASR final pass** — the largest model that fits the time budget, run on the
   full recording rather than on live chunks.
3. **Grounding** — verbatim quotes + timestamp citations + verifier.
4. **Prompting** — small model, narrow task, JSON schema, no long context.
5. **Model size** — last resort; most expensive lever per point of gain.

### Evaluation harness

- Gold set: 10 real meetings (3 one-on-one, 4 small group, 3 with crosstalk),
  hand-annotated transcript + actions + decisions. Collected in Phase 0–1.
- Metrics: normalised WER (`jiwer`), action-item precision/recall/F1, decision
  recall, section-heading quality (human 1–5), and a 10-question comprehension
  test answered from the note alone.
- **Targets (Tier C, revised in v0.3):** WER ≤ 18% on clean remote audio with
  `small`; action-item precision ≥ 0.80; decision recall ≥ 0.70; note rated ≥ 4/5
  for "I can tell what happened" by the user who attended.
  The old 15%-WER / turbo target is retained for Tier A hardware only.

## 15. Privacy and legal

- Everything local; no analytics; no account; no network at runtime.
- Recording-consent notice on first use and a visible recording indicator. Some
  jurisdictions and employers require disclosure to other participants. The app
  informs; it does not adjudicate.
- At rest: plain files in the user's app-data dir in v1; OS full-disk encryption
  is the assumed baseline. At-rest encryption is a v2 consideration.

## 16. Non-goals (v1)

- Live summarisation as the source of truth (draft-only, opt-in).
- Shared-screen / slide understanding (see A1).
- Calendar, email, or meeting-platform integrations.
- Cloud sync, sharing, teams/workspaces.
- Languages other than English.
- Mobile, browser-only operation.
- Speaker *name* recognition from voice.
- Auto-detecting a meeting and starting itself.

## 17. Phases

**Phase 0 — Hardware truth (1–2 days, do this first).**
*Step 0, 1 minute:* run `bench/check-power.ps1`. If it reports PINNED AT BASE, fix
the power configuration before measuring anything, or the benchmark will simply
confirm the cap. Record the sustained effective GHz — it is the number the rest of
the plan is really built on.

*Step 1:* benchmark kit in `bench/`. On the i7-8650U: measure whisper.cpp RTF for
`base`/`small`/`medium`/`turbo` **with word timestamps enabled**, and llama.cpp
prompt/generation throughput for 1.7B/3B/4B. Then record one real Zoom, one Teams
and one Meet call to prove WASAPI loopback works and measure echo.

*Go/no-go gate (revised for Tier C):*
1. `small` must process a 60-minute file in **≤ 35 minutes**. If not, the product
   is not viable on this laptop and we stop before writing the UI.
2. `base` must sustain **≥ 3× realtime** for the live pane to exist at all.
3. A 3B model must emit a schema-valid note from a scoped 1,500-token chunk in
   **< 45 s**. If not, drop to 1.7B, or move to a two-stage extract-then-format
   split where the model only fills a template.
4. Total end-to-end for a 60-minute meeting must land **≤ 55 minutes**.

If gate 1 or 3 fails, the honest conclusion is that the spec is right but *this
machine is the wrong machine*, and the decision becomes: change target hardware,
or accept overnight batch processing. Better to learn that in two days than after
Phase 2.

**Phase 1 — Headless pipeline (1.5 weeks).** `record → wav → transcript → note.md`.
CLI only, no UI. Fastest path to "is the output actually useful?" Run it against
the gold set.

**Phase 2 — Background app (2 weeks).** Tray icon, start/stop, live transcript
pane, level meters, meeting list, note viewer, rename speakers, export.

**Phase 3 — Productisation (1.5 weeks).** Installer, first-run model download,
code signing/notarisation, crash-safe recording, per-OS capture hardening.

**Phase 4 — Quality tuning (ongoing).** Prompt/schema iteration against the gold
set, optional remote-channel clustering, name seeding.

## 18. Open questions

1. **A6b** — Is the 2112 MHz cap a fixable power setting, or policy on a corporate
   image? Run `bench/check-power.ps1`; if boost cannot be restored, the plan needs
   a smaller model, a server, or different hardware.
2. **A8** — Will IT allow an unsigned background app that captures system audio on
   this work laptop? This can sink the project regardless of performance.
3. **A1** — Is "what I'm seeing" really just the conversation, or must the app know
   what is on screen?
4. **A2** — Are auto-detected speaker names required, or is "Remote 1/2/3" with a
   rename field enough for v1?
5. **A3** — Given Tier C, is **35–45 minutes** to notes acceptable, or is the
   trade in Mode II (5–12 min wait, ~50% CPU during the call, slightly worse
   notes) worth it? Or should we re-target hardware?
6. Export targets: Markdown only, or also PDF/DOCX?
7. Does the note need to be shareable with participants in v1, or personal-only?
