"""Measuring the thing, so tuning is not guesswork.

Two numbers matter: how much of what was said we captured (word error rate) and
whether the action items are the ones a human would have written (precision and
recall). Both are computed against a hand-made gold set.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Sequence

from .verify import normalise

ACTION_MATCH_THRESHOLD = 0.60


@dataclass(frozen=True)
class Scores:
    precision: float
    recall: float
    f1: float
    matched: int
    predicted: int
    expected: int


def _tokens(text: str) -> list[str]:
    return normalise(text).split()


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Edit distance between word sequences, divided by reference length."""
    ref, hyp = _tokens(reference), _tokens(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0

    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i]
        for j, hyp_word in enumerate(hyp, start=1):
            cost = 0 if ref_word == hyp_word else 1
            current.append(min(
                previous[j] + 1,        # deletion
                current[j - 1] + 1,     # insertion
                previous[j - 1] + cost,  # substitution
            ))
        previous = current
    return previous[-1] / len(ref)


def _similar(a: str, b: str) -> bool:
    return SequenceMatcher(None, normalise(a), normalise(b)).ratio() >= ACTION_MATCH_THRESHOLD


def score_actions(predicted: Sequence[str], gold: Sequence[str]) -> Scores:
    """Greedy one-to-one matching of predicted action items against the gold set."""
    remaining = list(gold)
    matched = 0
    for item in predicted:
        for index, expected in enumerate(remaining):
            if _similar(item, expected):
                matched += 1
                remaining.pop(index)
                break

    precision = matched / len(predicted) if predicted else 0.0
    recall = matched / len(gold) if gold else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return Scores(
        precision=round(precision, 3),
        recall=round(recall, 3),
        f1=round(f1, 3),
        matched=matched,
        predicted=len(predicted),
        expected=len(gold),
    )


def report(transcripts: dict[str, tuple[str, str]], actions: Scores | None = None) -> str:
    """A table suitable for pasting into bench/RESULTS.md."""
    lines = ["| metric | value |", "|---|---|"]
    for name, (reference, hypothesis) in transcripts.items():
        lines.append(f"| WER {name} | {word_error_rate(reference, hypothesis):.3f} |")
    if actions is not None:
        lines.append(f"| action precision | {actions.precision:.3f} |")
        lines.append(f"| action recall | {actions.recall:.3f} |")
        lines.append(f"| action F1 | {actions.f1:.3f} |")
        lines.append(
            f"| actions matched | {actions.matched}/{actions.expected} "
            f"(predicted {actions.predicted}) |"
        )
    return "\n".join(lines)
