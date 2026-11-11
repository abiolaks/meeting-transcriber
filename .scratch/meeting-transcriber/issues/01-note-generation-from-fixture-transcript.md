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

**2026-11-11 — real local model wired in. Ticket still open.**

`LlamaCppLLM` now exists: prompt builder, GBNF grammar forcing JSON, a parser that
survives llama.cpp's banner and truncated generations, and two guards. Tested
against a real llama.cpp build (b12284) and Qwen2.5 1.5B and 3B on Apple Silicon.

Evidence from real runs, which is the point of this ticket:

- **1.5B copies the prompt's example.** Given a filled example it returned
  "Budget review", "Priya", "Cut vendor spend by ten percent" — none of which
  happened. Grounding caught it; no note was written.
- **3B produced a genuinely grounded note once**: real quotes, a correct summary,
  six action items drawn from the transcript.
- **3B then failed to emit JSON at all** on a later run, twice. Small local models
  are flaky; one retry is not enough. Bump to three.
- **Timestamps must never be asked for.** The model cited `00:00:20` for a quote
  spoken at `02:15`. Action times are now computed from where the quote occurs in
  the transcript; unplaceable items are dropped.
- Draft time on an M2: ~105s for a 10-minute meeting, single attempt.

Remaining: raise the retry count, ground and timestamp decisions, force more than
one section (3B returned a single section), and compare against `medium.en` output
quality. Fixtures and models are gitignored — 2.8GB of weights stay out of the repo.
