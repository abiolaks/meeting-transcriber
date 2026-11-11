"""Markdown rendering.

The note is the product. It has to be readable at the top and auditable at the
bottom, so the two halves are built from different sources: summaries come from
the model, the transcript section is cut straight out of the transcript at the
model's chosen boundaries. The model never gets to retype what was said.
"""

from __future__ import annotations

from typing import Sequence

from .note import NoteDraft, Section
from .paragraphs import Paragraph, build as build_paragraphs
from .transcript import Transcript

MAX_GLANCE = 8


def _split_clock(seconds: float) -> tuple[int, int, int]:
    total = max(0, int(round(seconds)))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return hours, minutes, secs


def clock(seconds: float) -> str:
    """01:23:45 — used for citations."""
    hours, minutes, secs = _split_clock(seconds)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def short_clock(seconds: float) -> str:
    """01:23 under an hour, 1:01:23 above it — used for section ranges."""
    hours, minutes, secs = _split_clock(seconds)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def range_label(section: Section) -> str:
    return f"{short_clock(section.start)} – {short_clock(section.end)}"


def _first_sentence(text: str) -> str:
    text = " ".join(text.split())
    for index, char in enumerate(text):
        if char in ".!?" and index + 1 < len(text):
            return text[: index + 1]
    return text


def _owner_label(item) -> str:
    if not item.owner:
        return "Unassigned"
    if item.owner_confidence == "inferred":
        return f"{item.owner} (suspected)"
    return item.owner


def _glance(draft: NoteDraft) -> list[str]:
    bullets = [
        summary
        for summary in (_first_sentence(section.summary).strip() for section in draft.sections)
        if summary
    ]
    return (bullets or [f"{len(draft.sections)} sections discussed."])[:MAX_GLANCE]


def _paragraphs_for(section: Section, paragraphs: list[Paragraph]) -> list[Paragraph]:
    """Paragraphs are assigned by midpoint, so each one appears in exactly one section."""
    return [p for p in paragraphs if section.contains(p.midpoint)]


def _render_section(draft: NoteDraft, section: Section) -> list[str]:
    lines = [f"## {range_label(section)}  {section.title}", ""]

    summary = section.summary.strip()
    if summary:
        lines += [summary, ""]

    for item in draft.actions:
        if section.contains(item.start) and item.quote:
            lines += [f'> "{item.quote}" — [{clock(item.start)}]', ""]

    return lines


def _render_table(headers: Sequence[str], rows: list[list[str]], empty: str) -> list[str]:
    if not rows:
        return [empty, ""]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines + [""]


def _render_transcript(sections: tuple[Section, ...], paragraphs: list[Paragraph]) -> list[str]:
    lines = ["## Transcript", ""]
    for section in sections:
        for paragraph in _paragraphs_for(section, paragraphs):
            lines += [f"### {clock(paragraph.start)}  {paragraph.label}", ""]
            lines += [paragraph.text, ""]
    return lines


def render(draft: NoteDraft, transcript: Transcript) -> str:
    paragraphs = build_paragraphs(transcript)
    meeting = transcript.meeting
    minutes = int(meeting.duration_s // 60)
    duration = f"{minutes} min" if minutes else f"{int(meeting.duration_s)}s"

    lines = [f"# {meeting.title} — {meeting.date}, {duration}", ""]

    lines += ["**At a glance**", ""]
    lines += [f"- {bullet}" for bullet in _glance(draft)]
    lines += [""]

    for section in draft.sections:
        lines += _render_section(draft, section)

    lines += ["## Decisions", ""]
    lines += _render_table(
        ["#", "Decision", "Time"],
        [[str(i), d.text, f"[{clock(d.start)}]"] for i, d in enumerate(draft.decisions, 1)],
        "_None recorded._",
    )

    lines += ["## Action items", ""]
    lines += _render_table(
        ["Owner", "Action", "Due", "Source"],
        [[
            _owner_label(item),
            item.action,
            item.due or "—",
            f"[{clock(item.start)}]",
        ] for item in draft.actions],
        "_None recorded._",
    )

    if draft.unverified:
        lines += ["## Unverified", ""]
        lines += [
            "These were reported by the model but could not be found in the "
            "transcript. Treat them as suggestions, not facts.",
            "",
        ]
        lines += _render_table(
            ["Action", "Owner", "Claimed quote"],
            [[item.action, item.owner or "Unassigned", f'"{item.quote}"']
             for item in draft.unverified],
            "",
        )

    lines += ["## Open questions", ""]
    if draft.questions:
        lines += [f"- {question}" for question in draft.questions]
        lines += [""]
    else:
        lines += ["_None recorded._", ""]

    lines += _render_transcript(draft.sections, paragraphs)
    return "\n".join(lines).rstrip() + "\n"
