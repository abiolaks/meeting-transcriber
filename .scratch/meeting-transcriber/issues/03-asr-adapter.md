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
