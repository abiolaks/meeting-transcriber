"""Grounding: prove each action item came from the transcript, or demote it.

The note may be incomplete; it must not be confidently wrong. Every action item is
placed by finding its quote in the transcript, and an item whose quote cannot be
found moves to an "Unverified" list rather than being silently kept or silently
deleted.

This module owns that decision. `note.build` orchestrates; `render` displays.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Sequence

from .note import ActionItem, NoteDraft
from .paragraphs import Paragraph

# Phrases that mean the speaker committed to something themselves.
STATED_CUES = re.compile(
    r"\b(i'll|i will|i can|we'll|we will|let me|i'm going to|i am going to|"
    r"can you|could you|will you|please)\b",
    re.IGNORECASE,
)

PUNCTUATION = re.compile(r"[^\w\s']")


class GroundingError(RuntimeError):
    """Nothing in the draft could be traced back to the transcript."""


@dataclass(frozen=True)
class VerificationResult:
    draft: NoteDraft
    verified: int
    unverified: int


def normalise(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace — for substring checks."""
    return " ".join(PUNCTUATION.sub(" ", text.lower()).split())


def _find_paragraph(quote: str, paragraphs: Sequence[Paragraph]) -> Paragraph | None:
    needle = normalise(quote)
    if not needle:
        return None
    return next((p for p in paragraphs if needle in normalise(p.text)), None)


def classify_owner(owner: str | None, quote: str) -> str:
    """How much the transcript actually supports the owner.

    `stated`   — the quote contains a commitment phrase.
    `inferred` — an owner was named, but the quote does not commit them.
    `unassigned` — no owner.
    """
    if not owner:
        return "unassigned"
    return "stated" if STATED_CUES.search(quote) else "inferred"


def verify(draft: NoteDraft, paragraphs: Sequence[Paragraph]) -> VerificationResult:
    """Place every action item, demoting anything that cannot be traced."""
    kept: list[ActionItem] = []
    demoted: list[ActionItem] = []

    for item in draft.actions:
        paragraph = _find_paragraph(item.quote, paragraphs)
        if paragraph is None:
            demoted.append(replace(item, owner_confidence="unassigned"))
            continue
        kept.append(replace(
            item,
            start=paragraph.start,
            owner_confidence=classify_owner(item.owner, item.quote),
        ))

    # Decisions are paraphrases and cannot be substring-checked, so they pass
    # through with the model's timestamps. That is a known soft spot.
    decisions = draft.decisions

    if draft.actions and not kept:
        raise GroundingError(
            f"none of the {len(draft.actions)} action items could be found in the "
            "transcript; the model invented them"
        )

    return VerificationResult(
        draft=replace(
            draft,
            actions=tuple(kept),
            unverified=tuple(demoted),
            decisions=decisions,
        ),
        verified=len(kept),
        unverified=len(demoted),
    )
