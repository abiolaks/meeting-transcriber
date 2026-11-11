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

## Comments

**2026-11-11 — deterministic core landed, model still missing.**

Done: transcript schema with precise validation errors, paragraph assembly,
section normalisation (gaps closed, overlaps clipped, backwards ranges dropped),
markdown rendering with a verbatim transcript section, and a CLI. `FakeLLM` sits
behind the adapter seam. 38 tests, mypy clean, ruff clean. The 10-minute fixture
in `fixtures/` exercises the whole path.

Still open, and it is the half that matters: `LlamaCppLLM.draft` — the llama.cpp
invocation, the GBNF grammar, and the model fetch. Until that exists, `--llm llama`
exits with status 3.

**What this ticket has actually proven:** the renderer, the schema and the
section-tiling are correct. **What it has not proven:** that a small local model
can write a note worth reading. The "At a glance" bullets above the fold are
currently arbitrary lines from the fake, not summaries. Do not read the demo note
as evidence of note quality.
