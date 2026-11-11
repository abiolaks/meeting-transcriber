# Meeting transcriber — implementation tickets

The product spec is [`../../SPEC.md`](../../SPEC.md). This directory holds the
implementation tickets for **Phase 1 (pipeline) plus Windows capture** — the work
between "the spec is agreed" and "it runs on the target laptop".

Phase 0 (hardware validation, see [`../../bench/`](../../bench/)) is human-run and
is not ticketed. It gates the *timing* decisions, not the note-quality work, which
is why tickets 01 and 03 can start before the benchmark finishes.

## Ticket map

| # | Ticket | Blocked by |
|---|---|---|
| 01 | [Note generation from a fixture transcript](issues/01-note-generation-from-fixture-transcript.md) | — |
| 02 | [Grounding verifier](issues/02-grounding-verifier.md) | 01 |
| 03 | [ASR adapter](issues/03-asr-adapter.md) | — |
| 04 | [Two-channel merge and speaker attribution](issues/04-two-channel-merge.md) | 03 |
| 05 | [End-to-end pipeline and evaluation harness](issues/05-end-to-end-and-evaluation.md) | 02, 04 |
| 06 | [Windows capture](issues/06-windows-capture.md) | — |
| 07 | [Windows end-to-end with live capture](issues/07-windows-end-to-end.md) | 05, 06 |

```
01 ──► 02 ──┐
            ├──► 05 ──┐
03 ──► 04 ──┘         ├──► 07
                      │
06 ───────────────────┘
```

Frontier at the start: **01, 03, 06** — three independent roots, deliberately
chosen so capture (the untestable-on-Mac part), ASR, and note quality can all
progress in parallel.

## Ordering rationale

The first slice is note generation, not transcription, because the highest-risk
unknown is whether a 3B model writes a note worth trusting. That question can be
answered with a hand-written fixture — no models beyond the LLM, no audio, no
access to the laptop.

## Out of scope here

Persistence, tray UI, installer, and signing are Phase 2–3. Mixing them into this
set would swamp the frontier.
