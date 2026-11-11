# 01: Note generation from a fixture transcript

**What to build:** A command that reads a checked-in two-channel transcript fixture and writes a complete meeting note — at-a-glance bullets, topic sections with time ranges, decisions, and action items carrying owner, quote and timestamp. The same command fetches the LLM weights it needs, so a fresh clone can produce a note without a separate setup step.

This is the first slice because it carries the project's biggest unknown — whether a small local model can write a note a human would trust — and it needs no ASR, no audio, and no access to the target laptop to answer that.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] A two-channel transcript fixture of at least 10 minutes is committed, with speaker labels and word-level timestamps
- [ ] The transcript format is documented, and a loader rejects malformed input with an error naming the offending field
- [ ] One command produces `note.md` containing at-a-glance bullets, sections with time ranges, decisions, and action items
- [ ] Every section heading carries a time range that exists in the fixture
- [ ] Invalid model output is retried once, then fails loudly; a partial note is never written to disk
- [ ] After the first model fetch, the command runs to completion with the network disabled
- [ ] Total generation time for the 10-minute fixture is printed

Notes: the section boundaries come from the model, but the transcript text inside each section is cut verbatim by the renderer — the model never rewrites what people said.
