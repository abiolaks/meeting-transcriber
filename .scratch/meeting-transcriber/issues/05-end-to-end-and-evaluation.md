# 05: End-to-end pipeline and evaluation harness

**What to build:** One command that takes two channel WAVs and writes a finished `note.md`, with no manual steps between. Plus a harness that scores a run against a gold set — WER per channel, action-item precision and recall, decision recall — printed in a form that can be pasted straight into `bench/RESULTS.md`.

Without the harness, every later tuning change is judged by vibes. This is the ticket that makes quality measurable.

**Blocked by:** 02, 04

**Status:** ready-for-agent

- [ ] Single command: two WAVs in, `note.md` out, unattended
- [ ] Harness prints WER for each channel against a gold transcript
- [ ] Harness prints action-item precision, recall and F1, and decision recall
- [ ] Harness output is paste-ready into `bench/RESULTS.md` without reformatting
- [ ] A deliberately degraded run (e.g. wrong model) lowers the scores, proving the harness actually measures something
- [ ] Exits non-zero on any stage failure rather than writing a partial note
- [ ] Total wall-clock time is recorded per stage

## Comments

**2026-11-11 — implemented, pending the gold set.** `mt run` takes two channel WAVs
and writes `note.md`; `mt eval` prints WER per channel plus action-item
precision/recall as a markdown table ready for `bench/RESULTS.md`.

Structure: `pipeline.process_transcripts` (testable anywhere, no models) is lifted
by `pipeline.process_wavs` (adds ASR). Stage timings and echo count are reported.

Not done: the gold set itself. Scoring is meaningless until there are ten real
meetings with hand-written action items — that is calendar time, not code.
