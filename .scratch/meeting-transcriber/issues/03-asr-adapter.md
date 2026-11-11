# 03: ASR adapter — audio file to transcript

**What to build:** A command that turns one 16 kHz mono WAV into the same transcript format the note generator already consumes, with word-level timestamps, running whisper.cpp locally with no network access.

Independent of ticket 01 so the two can proceed in parallel: 01 pins the transcript format against a fixture, 03 has to produce something that format already describes.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] One command produces transcript JSON matching the documented schema
- [ ] The loader from ticket 01 accepts it unchanged, with no special-casing
- [ ] Every segment carries word-level timestamps, not just sentence boundaries
- [ ] A missing model file produces an actionable error naming the file to fetch
- [ ] Real-time factor and elapsed time are printed on completion
- [ ] Runs with the network disabled once the model is present

## Comments

**2026-11-11 — complete.** whisper.cpp adapter in `src/mt/asr.py`; `mt transcribe`
writes transcript JSON. Verified against a real build (whisper.cpp source build,
`ggml-base.en-q5_1`) on synthesised speech.

All acceptance criteria met except one: "runs with the network disabled" is true
by construction (no network code anywhere in the adapter) but there is no
enforcing test. SPEC §12-M5 wants a socket-blocking test; not written yet because
the work happens in a child process, where a parent-side socket patch proves
nothing. Worth doing properly when packaging.

Notes for later tickets:
- RTF includes process start and model load (~5-7s fixed), so it is meaningless
  below ~30s of audio. Phase 0 must use clips of a realistic length.
- `--channel`/`--label` already exist, so ticket 04 can run the second track
  without changing this file.
- Segment regrouping (pause > 1s, or 12 words) produces *utterances*, not
  paragraphs. Paragraph assembly stays in the note stage; this does not conflict
  with SPEC §8-P1.
