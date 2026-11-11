"""Note orchestration: from a transcript to a draft the renderer can trust.

The language model proposes; this module disposes. Whatever it returns for
section boundaries — gaps, overlaps, backwards ranges — the sections come out
tiling the meeting exactly once and anchored to real moments in the transcript.

If the model returns nothing usable, we ask once more and then fail. We never
invent sections: a note with made-up structure reads as if it covered the
meeting when it did not.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol, Sequence

from .paragraphs import Paragraph, build as build_paragraphs
from .transcript import Meeting, Transcript


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


def anchor_actions(
    draft: NoteDraft, paragraphs: Sequence[Paragraph]
) -> tuple[NoteDraft, int]:
    """Point every action item at the moment its quote was actually spoken.

    The model is not asked to compute timestamps any more, because it gets them
    wrong: a quote it placed at 00:20 appeared at 02:15. The quote itself is
    checkable, so the position is computed from it. Items whose quote is not in
    the transcript are dropped, and counted so the loss is visible.
    """
    spoken = [(paragraph, _normalise(paragraph.text)) for paragraph in paragraphs]
    kept: list[ActionItem] = []
    dropped = 0

    for item in draft.actions:
        quote = _normalise(item.quote)
        match = next((p for p, text in spoken if quote and quote in text), None)
        if match is None:
            dropped += 1
            continue
        kept.append(replace(item, start=match.start))

    return replace(draft, actions=tuple(kept)), dropped


def is_grounded(draft: NoteDraft, paragraphs: Sequence[Paragraph]) -> bool:
    """A cheap guard against total fabrication.

    If the model produced action items but not one of their quotes appears in the
    transcript, it is writing from its imagination — usually by copying the
    prompt's example. Per-item demotion is ticket 02; this only stops a wholly
    invented note from being written at all.
    """
    if not draft.actions:
        return True
    spoken = _normalise(" ".join(paragraph.text for paragraph in paragraphs))
    return any(_normalise(item.quote) and _normalise(item.quote) in spoken for item in draft.actions)


class NoteError(RuntimeError):
    """The draft could not be turned into a note that covers the meeting."""


@dataclass(frozen=True)
class Section:
    title: str
    start: float
    end: float
    summary: str

    def contains(self, instant: float) -> bool:
        return self.start <= instant < self.end


@dataclass(frozen=True)
class ActionItem:
    owner: str | None
    action: str
    due: str | None
    quote: str
    start: float


@dataclass(frozen=True)
class Decision:
    text: str
    start: float


@dataclass(frozen=True)
class NoteDraft:
    sections: tuple[Section, ...]
    actions: tuple[ActionItem, ...]
    decisions: tuple[Decision, ...]
    questions: tuple[str, ...] = ()


class LLM(Protocol):
    """The adapter seam: a fake and a local model are interchangeable here."""

    def draft(self, meeting: Meeting, paragraphs: Sequence[Paragraph]) -> NoteDraft:
        ...


def normalise_sections(sections: Sequence[Section], duration: float) -> list[Section]:
    """Clamp, order and de-overlap sections. Returns [] when nothing is usable."""
    usable = [
        replace(s, start=max(0.0, s.start), end=min(duration, s.end))
        for s in sections
        if s.end > s.start and s.start < duration and s.end > 0.0
    ]
    usable.sort(key=lambda s: s.start)

    clipped: list[Section] = []
    for section in usable:
        if clipped and section.start <= clipped[-1].start:
            continue  # fully contained in the previous section
        if clipped and section.start < clipped[-1].end:
            clipped[-1] = replace(clipped[-1], end=section.start)
        clipped.append(section)

    clipped = [s for s in clipped if s.end > s.start]
    if not clipped:
        return []

    for index in range(len(clipped) - 1):
        if clipped[index + 1].start > clipped[index].end:
            clipped[index] = replace(clipped[index], end=clipped[index + 1].start)

    clipped[0] = replace(clipped[0], start=0.0)
    return [s for s in clipped if s.end > s.start]


def anchor_to_transcript(
    sections: Sequence[Section], paragraphs: Sequence[Paragraph]
) -> list[Section]:
    """Move interior boundaries onto real paragraph starts.

    A heading like "00:03:22" should point at something that was actually said.
    Arithmetic boundaries can land mid-sentence, or past the last word spoken.
    """
    if not sections or not paragraphs:
        return list(sections)

    anchored = list(sections)
    starts = [p.start for p in paragraphs]

    for index in range(len(anchored) - 1):
        boundary = anchored[index].end
        candidate = next((start for start in starts if start >= boundary - 1e-6), None)
        if candidate is not None and anchored[index].start < candidate < anchored[index + 1].end:
            anchored[index] = replace(anchored[index], end=candidate)
            anchored[index + 1] = replace(anchored[index + 1], start=candidate)

    last = anchored[-1]
    final_end = max(p.end for p in paragraphs)
    if last.start < final_end:
        anchored[-1] = replace(last, end=final_end)

    return [s for s in anchored if s.end > s.start]


def build(transcript: Transcript, llm: LLM) -> NoteDraft:
    """Produce a note draft whose sections tile the meeting and cite real moments."""
    paragraphs = build_paragraphs(transcript)
    duration = transcript.meeting.duration_s

    for attempt in range(2):
        draft = llm.draft(transcript.meeting, paragraphs)
        sections = normalise_sections(draft.sections, duration)
        if sections and is_grounded(draft, paragraphs):
            sections = anchor_to_transcript(sections, paragraphs)
            draft, _dropped = anchor_actions(draft, paragraphs)
            return replace(draft, sections=tuple(sections))
        if attempt == 0:
            continue  # the spec allows exactly one retry

    raise NoteError(
        "the model did not return any usable section boundaries after one retry; "
        "no note was written"
    )
