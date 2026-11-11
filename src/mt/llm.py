"""Language-model adapters.

`FakeLLM` is a test double: deterministic, no model, no download. It exists so the
whole pipeline can be built and tested before a single weight is fetched, and so
tests never depend on how a model happens to phrase something.

`LlamaCppLLM` is the real adapter and is deliberately unimplemented for now —
ticket 01's remaining work. It is not stubbed out quietly: calling it raises with
the exact reason.
"""

from __future__ import annotations

from math import ceil
from typing import Sequence

from .note import ActionItem, Decision, NoteDraft, Section
from .paragraphs import Paragraph
from .transcript import Meeting

ACTION_CUES = ("i'll ", "i will ", "can you ", "i'm going to ", "let me ")
DECISION_CUES = ("agreed", "we decided", "let's call it", "let's go with")


class FakeLLM:
    """Deterministic stand-in. Mirrors the real adapter's interface only."""

    name = "fake"

    def draft(self, meeting: Meeting, paragraphs: Sequence[Paragraph]) -> NoteDraft:
        duration = meeting.duration_s
        count = max(1, min(3, ceil(duration / 60)))
        width = duration / count

        sections = [
            Section(
                title=f"Part {index + 1}",
                start=index * width,
                end=(index + 1) * width,
                summary=_summary_for(index * width, (index + 1) * width, paragraphs),
            )
            for index in range(count)
        ]

        actions: list[ActionItem] = []
        decisions: list[Decision] = []
        for paragraph in paragraphs:
            lowered = paragraph.text.lower()
            if any(cue in lowered for cue in ACTION_CUES):
                actions.append(ActionItem(
                    owner=paragraph.label,
                    action=_clause(paragraph.text),
                    due=None,
                    quote=_quote(paragraph.text),
                    start=paragraph.start,
                ))
            if any(cue in lowered for cue in DECISION_CUES):
                decisions.append(Decision(text=_clause(paragraph.text), start=paragraph.start))

        return NoteDraft(
            sections=tuple(sections),
            actions=tuple(actions),
            decisions=tuple(decisions),
            questions=(),
        )


def _summary_for(start: float, end: float, paragraphs: Sequence[Paragraph]) -> str:
    """A stand-in for a summary: the most substantial line in the section.

    Deliberately not a summary. It exists so the rendered note is readable while
    the real model is missing, and so tests do not depend on model phrasing.
    """
    inside = [p for p in paragraphs if start <= p.start < end]
    if not inside:
        return ""
    text = max(inside, key=lambda p: len(p.text)).text
    return text if len(text) <= 160 else text[:157].rstrip() + "..."


def _quote(text: str) -> str:
    sentence = _clause(text)
    words = sentence.split()
    return " ".join(words[:15])


def _clause(text: str) -> str:
    for separator in (". ", "; ", ", and "):
        if separator in text:
            return text.split(separator, 1)[0].strip()
    return text.strip()


class LlamaCppLLM:
    """Local llama.cpp backend. Ticket 01's remaining work."""

    name = "llama"

    def __init__(self, model_path: str | None = None) -> None:
        self.model_path = model_path

    def draft(self, meeting: Meeting, paragraphs: Sequence[Paragraph]) -> NoteDraft:
        raise NotImplementedError(
            "LlamaCppLLM is not implemented yet. Ticket 01 still needs the "
            "llama.cpp invocation, the JSON grammar, and the model fetch. "
            "Use --llm fake until then."
        )
