"""Deterministic paragraph assembly.

The meeting note is readable at the top and auditable at the bottom, and the
bottom half is only readable if the transcript is grouped sensibly. Grouping is
mechanical on purpose: merging consecutive turns is something a rule does better
than a language model, and it can be tested.
"""

from __future__ import annotations

from dataclasses import dataclass

from .transcript import Transcript

DEFAULT_MAX_WORDS = 45
DEFAULT_MAX_SECONDS = 45.0
DEFAULT_MAX_GAP = 2.0


@dataclass(frozen=True)
class Paragraph:
    start: float
    end: float
    channel: str
    label: str
    text: str
    word_count: int

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def midpoint(self) -> float:
        return self.start + (self.end - self.start) / 2.0


def build(
    transcript: Transcript,
    *,
    max_words: int = DEFAULT_MAX_WORDS,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    max_gap: float = DEFAULT_MAX_GAP,
) -> list[Paragraph]:
    """Merge consecutive same-speaker turns into readable paragraphs."""
    paragraphs: list[Paragraph] = []

    current_channel: str | None = None
    current_parts: list[str] = []
    current_words = 0
    current_start = 0.0
    current_end = 0.0

    def flush() -> None:
        nonlocal current_parts, current_words, current_channel
        if current_channel is None or not current_parts:
            return
        paragraphs.append(
            Paragraph(
                start=current_start,
                end=current_end,
                channel=current_channel,
                label=transcript.label_for(current_channel),
                text=" ".join(current_parts).strip(),
                word_count=current_words,
            )
        )
        current_parts = []
        current_words = 0
        current_channel = None

    for segment in transcript.segments:
        word_count = len(segment.text.split())
        same_speaker = segment.channel == current_channel
        gap = segment.start - current_end
        fits_words = current_words + word_count <= max_words
        fits_seconds = (segment.end - current_start) <= max_seconds if current_parts else True

        if current_parts and same_speaker and gap <= max_gap and fits_words and fits_seconds:
            current_parts.append(segment.text)
            current_words += word_count
            current_end = segment.end
            continue

        flush()
        current_channel = segment.channel
        current_parts = [segment.text]
        current_words = word_count
        current_start = segment.start
        current_end = segment.end

    flush()
    return paragraphs
