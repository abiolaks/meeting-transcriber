# Tuning playbook — i7-8650U, 16 GB, single test user

Goal: make this specific machine produce the best notes it can, in the least
time, for one real person. Not a general product. One laptop, one user, measured.

Everything here is ordered by **expected gain per hour of effort**, and every
change must be measured before it ships. Numbers marked ≈ are estimates from
comparable hardware; the point of this document is to replace them.

---

## 0. Order of operations

Do these in this order. Tuning out of order wastes days.

1. `check-power.ps1` — is the CPU allowed to boost at all? **Nothing else counts
   until this is answered.**
2. Build the gold clip (§5) — 20 minutes of a *real* meeting, with a transcript.
3. Baseline measurement, default flags.
4. Apply levers one at a time, re-measure, keep what wins.
5. Lock the winning config into the spec and stop tuning.

---

## 1. Quality levers

These change what the note says. Rank order by impact.

### Q1 — Never mix the channels ★ biggest

Transcribe `ch0` (your mic) and `ch1` (the meeting audio) as **two separate
files**, then merge by timestamp. Do not sum them.

Your mic carries room echo, keyboard, fan and your own breathing. The loopback
carries a decoded digital stream — no room, no distance, no echo. Mixing them
throws mic noise on top of the cleanest audio in the whole system, and Whisper
degrades on noise far faster than it degrades on bandwidth.

Cost: two decoder runs instead of one, but the two channels together hold about
as much speech as the meeting itself, so the total is roughly a wash. Silence on
one channel is skipped independently.

### Q2 — Use `.en` models

`ggml-small.en.bin`, not `ggml-small.bin`. Same size, same speed, better English.
You already committed to English (D1), so the multilingual capability is dead
weight. Free.

### Q3 — Seed the prompt with names and jargon

```
--prompt "Attendees: Alex Chen, Sam Okoro. Project Meridian, Q3 billing migration, Stripe webhooks."
```

Whisper's initial prompt biases decoding. Meeting notes rise and fall on proper
nouns, which are exactly what an unseeded model mangles. Keep the glossary
per-user and feed it automatically. Cost: a few hundred prompt tokens, no runtime
penalty worth measuring.

### Q4 — Merge VAD segments to ≥ 5 s

Whisper hallucinates on very short, quiet fragments ("Thank you.", "Okay.",
subtitle-credit text). Feed it 5–30 second spans, not 0.4 s of breath. This is
the single most common cause of garbage lines in a transcript, and it is a
segmentation bug, not a model limitation.

### Q5 — Suppress non-speech

Turn on the logprob / entropy / no-speech thresholds (check `--help`; the flags
are `-et`, `-lpt`, `-nth` in recent builds). Set them conservatively and confirm
on a clip with a long pause and some typing. A phantom "Thanks for watching!" in
a board meeting destroys trust in the whole note.

### Q6 — Glossary post-pass

After transcription, fuzzy-match rare tokens against the user's glossary
(Levenshtein ≤ 2, phonetic match on the first syllable) and correct them. Cheap,
deterministic, and it fixes exactly the errors that annoy humans most.

### Q7 — `medium.en` as the overnight option

When accuracy matters more than time, run `medium.en` instead. Expect roughly
2.5× the runtime of `small.en` for a real but modest WER gain. Offer it as
"reprocess with higher quality", not as the default.

---

## 2. Speed levers

Ranked by gain. The first one is free.

| Lever | Expected gain | Cost |
|---|---|---|
| **Fix the clock cap** | up to 1.5× | none, if policy allows |
| AVX2/FMA build of whisper.cpp | 2–3× vs generic build | none — just use the right release |
| `q5_1` quantised model vs f16 | 1.0–1.3× — **must measure** | small WER risk, see §2.1 |
| Threads = physical cores (4), not 8 | 0–15% | none |
| `-bs 1` (greedy) instead of `-bs 5` | 1.2–1.3× | quality risk — see §6 |
| VAD gating (skip silence) | 1.1–1.3× | none |
| Skip the live ASR pass entirely | saves 9–15 min of work | lose the live pane |
| Mode II: no final re-transcription | saves 25–37 min | worse transcript |

### Measure the thread count, don't assume

Hyperthreading usually *hurts* whisper.cpp on a 4-core U-series part, because the
extra threads contend for the same execution units. Test 4, 6 and 8:

```powershell
Measure-Command { whisper-cli -m models\ggml-small.en.bin -f sample.wav -l en -t 4 -np } | % TotalSeconds
Measure-Command { whisper-cli -m models\ggml-small.en.bin -f sample.wav -l en -t 6 -np } | % TotalSeconds
Measure-Command { whisper-cli -m models\ggml-small.en.bin -f sample.wav -l en -t 8 -np } | % TotalSeconds
```

Run each twice; on a 15 W chip the second run is the honest one.

### Measure the beam size

```powershell
Measure-Command { whisper-cli -m models\ggml-small.en.bin -f sample.wav -l en -t 4 -bs 5 -np } | % TotalSeconds
Measure-Command { whisper-cli -m models\ggml-small.en.bin -f sample.wav -l en -t 4 -bs 1 -np } | % TotalSeconds
```

`-bs 1` is typically 20–30% faster. Whether you can afford it depends on whether
it starts repeating itself — check the output, not just the clock.

### 2.1 Quantisation: measure it, do not assume it

Yes, we quantise — but the reasoning matters, because for **ASR on this machine it
is not the free win it looks like**.

| File | Size | |
|---|---|---|
| `ggml-small.en.bin` (f16) | 488 MB | baseline |
| `ggml-small.en-q8_0.bin` | 265 MB | near-lossless |
| `ggml-small.en-q5_1.bin` | 190 MB | the usual pick |
| `ggml-base.en-q5_1.bin` | 60 MB | live pass |

Two things drive the speed of quantised CPU inference: **memory bandwidth**, which
quantisation genuinely reduces, and **int8 dot-product instructions**, which your
Kaby Lake chip **does not have** (AVX2, no VNNI). On this CPU ggml dequantises and
then does float FMA, so the win is bandwidth-only — real, but often 0–30%, and
occasionally negative once dequantisation overhead is counted.

And the usual reason to quantise is absent: you have 16 GB, so a 488 MB model is
nothing. **There is no memory pressure to relieve, so quantisation has to earn its
place on speed alone.**

So run the A/B on the gold clip, twice each:

```powershell
Measure-Command { whisper-cli -m models\ggml-small.en.bin        -f sample.wav -l en -t 4 -np } | % TotalSeconds
Measure-Command { whisper-cli -m models\ggml-small.en-q8_0.bin   -f sample.wav -l en -t 4 -np } | % TotalSeconds
Measure-Command { whisper-cli -m models\ggml-small.en-q5_1.bin   -f sample.wav -l en -t 4 -np } | % TotalSeconds
```

Decision rule:

- `q5_1` **≥ 10% faster** and WER within 1 point → **use `q5_1`** (saves 300 MB of
  download as a bonus).
- Faster by less than that, or WER visibly worse → **use f16**. Simplicity and
  accuracy beat 5%.
- Never `q4_*` for ASR. The errors land on rare words, and rare words are names,
  product names and jargon — literally the content of the note.

The LLM is the opposite case: a 3B at f16 would be ~6 GB and roughly 2× slower.
`Q4_K_M` there is mandatory, and the quality cost is well understood and
acceptable for a constrained extraction task.

---

## 3. LLM side

| Setting | Value | Why |
|---|---|---|
| Temperature | 0.0–0.1 | extraction is not a creative task |
| Top-k | 20 | narrow |
| Repeat penalty | 1.05–1.1 | small models loop without it |
| Context | 4096 | enough for a 1.5k-token window + output |
| Grammar | GBNF, forced JSON | malformed JSON is the #1 small-model failure |
| Threads | 4 | same argument as ASR |

Prompt layout that works for a 3B, in order: role (one line) → the JSON schema →
one worked example → the candidate sentences. Put the schema *before* the
examples and keep the whole thing under ~700 tokens, or the model starts
copying the schema back at you instead of filling it in.

---

## 4. Anti-patterns

Things that look like optimisations and are not:

- **Bigger model to fix bad notes.** Fix the audio, segmentation and prompt
  first. A well-grounded `small.en` beats a stuffed-context `medium` on action
  items every time.
- **`-bs 1` everywhere.** Cheap speed that shows up as repetition loops in the
  transcript, which then poison the summary.
- **Splitting audio into tiny chunks.** Faster to stream, much worse to read.
- **Feeding the whole transcript to the LLM.** It will summarise the beginning
  and the end and invent the middle. See the token budget in SPEC §9.
- **8 threads because 8 logical processors.** Contention.
- **`q4_*` ASR weights** to save 60 MB of disk on a machine with 16 GB of RAM.
- **Assuming quantisation is faster** because it is smaller. Measure it.
- **Tuning on synthetic audio.** TTS has no disfluencies, no crosstalk, no
  accents. It will make every configuration look better than it is.

---

## 5. The gold clip

Before any tuning, make this:

- 20 minutes of a **real** meeting you attended.
- Ideally: 2+ speakers, one accented, some crosstalk, some silence.
- Recorded as two channels, exactly as the product will (`ch0` mic, `ch1` loopback).
- Hand-corrected transcript for both channels — yes, this is tedious. It is the
  only way to know if a change helped or just felt faster.

Twenty minutes is enough to be representative and short enough to iterate on.

Score each run on: WER per channel, wall-clock seconds, and a count of
hallucinated lines. Keep a one-line log per configuration — you will not remember
which flag combination was which.

---

## 6. Choosing the final config

After the matrix, pick the **fastest configuration that meets the WER targets in
SPEC §4**. Concretely:

```
if   RTF(small.en, fastest safe flags) <= 0.40  -> ship it
elif RTF <= 0.55                               -> ship it, accept ~40 min
elif clock cap cannot be fixed                 -> Mode II, or server, or hardware
```

Do not accept `-bs 1` speed if it costs more than ~1 point of WER, and never
accept a config that hallucinates text into silence.

---

## 7. What "working well" looks like

The end state to aim for, on this laptop:

- Press stop after 60 minutes → honest progress with an ETA → note appears in
  **~28–35 minutes**, not 55.
- Remote-channel WER around **9–11%**; your own mic channel worse, **15–18%**,
  which is expected and does not hurt the note much.
- Action items: owners and quotes correct, **at most one or two wrong** in a
  45-minute meeting, and anything uncertain explicitly marked unassigned.
- Section headings that a person who was there would recognise as "yes, that's
  what we talked about and in that order".
- Zero invented content. A shorter note that is entirely true beats a longer one
  that is partly false.

If it hits that, it is a good tool. If it lands at 50 minutes with 18% WER, the
answer is not more tuning — it is `DEPLOYMENT.md` Mode B, or a different laptop.
