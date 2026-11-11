# Local Meeting Transcriber

**Status: early implementation.** The note pipeline runs end to end against a
fixture transcript with a fake model; speech recognition and the real local model
are not built yet. Phase 0 hardware validation is still outstanding — see
[SPEC.md](SPEC.md) §17.

A background app that records both sides of a remote meeting (Zoom, Teams, Google
Meet) on one laptop, transcribes it on-device, and produces a readable,
well-sectioned note: what was discussed, what was decided, and what needs doing,
by whom, by when.

No cloud. No account. No network at runtime.

---

## The constraint that shapes the design

The target machine is a **2017 Intel Core i7-8650U** — 4 cores / 8 threads, 15 W,
16 GB RAM, no usable GPU. That is roughly a quarter of the sustained compute of a
current laptop, and it is what the whole design is built around.

Consequences, all argued in the spec:

- `large-v3-turbo` is **not viable** — its large encoder dominates runtime and
  doesn't shrink. `small.en` is the ceiling.
- A one-hour meeting yields its note **35–45 minutes after you press stop**, not
  in two minutes.
- A 3B LLM with a hard **1,500 output-token budget** does the summarising.
- CPU clocks are the binding constraint, not RAM. The 2112 MHz figure the machine
  reports is nominal, not a cap — it boosts to ~4.1 GHz. Measured, not assumed.

If those numbers are unacceptable, the answer is different hardware or a server —
see [DEPLOYMENT.md](DEPLOYMENT.md), not a bigger model.

---

## Documents

| File | What it covers |
|---|---|
| [SPEC.md](SPEC.md) | The product spec: architecture, capture, ASR, synthesis, output format, storage, packaging, phases |
| [TUNING.md](TUNING.md) | How to make it fast and accurate on *this* laptop: every knob, ranked, with the measurement protocol |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Where the compute runs — local, thin-agent-plus-server, or browser-only — and what "free hosting" actually gets you |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Develop on Mac, ship on Windows: what each machine can and cannot prove, and how packaging works |
| [bench/](bench/) | Phase 0: capture smoke test, benchmark kit, CPU power diagnostic, results template |

---

## Core design decisions

- **Audio is the source of truth.** Every stage is re-runnable from the recording,
  so a slow CPU costs time, never data.
- **The two channels are transcribed separately, never mixed.** The loopback is a
  decoded digital stream — the cleanest audio in the system — and mixing the mic
  into it would throw that advantage away.
- **The LLM decides where section cuts go; it never rewrites the transcript.** The
  note is readable at the top and auditable at the bottom.
- **Every action item must quote the transcript.** Anything that fails
  verification is demoted to "Unverified", never silently kept.
- **Precision over recall on owners.** An invented owner destroys trust faster
  than a missed action.
- **The recording path is never blocked, preempted, or degraded by ML work.**

## Non-goals for v1

Live summarisation · shared-screen understanding · calendar and platform
integrations · cloud sync · languages other than English · mobile · voice-based
speaker identification · auto-starting on meeting detection.

---

## Getting started (Phase 0)

Phase 0 exists to answer one question: **is this laptop fast enough to be worth
building on?** It takes an hour or two, not a week.

```powershell
cd bench
powershell -ExecutionPolicy Bypass -File .\check-power.ps1   # is the CPU capped?
```

Then follow [bench/README.md](bench/README.md): assemble whisper.cpp and
llama.cpp, record a real meeting, and measure.

The gates are in [SPEC.md](SPEC.md) §17. If gate 1 fails — `small.en` cannot
process a 60-minute file in under 35 minutes — the honest conclusion is that the
spec is right and the machine is wrong.

---

## Licence

Not yet chosen. Do not assume permissive terms until this section changes.
