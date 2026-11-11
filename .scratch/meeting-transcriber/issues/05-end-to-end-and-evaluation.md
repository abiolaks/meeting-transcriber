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
