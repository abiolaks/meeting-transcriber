"""Seam: render.render.

Two things must hold no matter what the model did: the note has the five sections
a reader expects, and the transcript section is *verbatim*. The model may write
summaries; it may not touch what people actually said.
"""

import re

from mt.note import ActionItem, Decision, NoteDraft, Section
from mt.render import render
from mt.transcript import parse

TRANSCRIPT = "We are two weeks behind on the billing migration."


def transcript():
    return parse({
        "version": 1,
        "meeting": {"title": "Weekly sync", "date": "2026-11-12", "duration_s": 120.0},
        "channels": [{"id": "ch0", "label": "You"}, {"id": "ch1", "label": "Remote"}],
        "segments": [
            {"id": "s1", "start": 0.0, "end": 30.0, "channel": "ch1", "text": TRANSCRIPT},
            {"id": "s2", "start": 30.0, "end": 60.0, "channel": "ch0", "text": "What is the failure rate?"},
            {"id": "s3", "start": 60.0, "end": 120.0, "channel": "ch1", "text": "About four percent."},
        ],
    })


def draft():
    return NoteDraft(
        sections=(
            Section("Status", 0.0, 60.0, "The migration is late."),
            Section("Numbers", 60.0, 120.0, "They discussed failure rates."),
        ),
        actions=(
            ActionItem(owner="Sam", action="Fix the retry backoff", due="Friday",
                       quote="I'll fix it", start=72.0),
            ActionItem(owner=None, action="Confirm sandbox access", due=None,
                       quote="someone should check", start=90.0),
        ),
        decisions=(Decision("Ship on the 20th", 45.0),),
        questions=("When do we freeze?",),
    )


def test_header_carries_title_and_date():
    out = render(draft(), transcript())

    assert "Weekly sync" in out
    assert "2026-11-12" in out


def test_the_note_has_the_sections_a_reader_expects():
    out = render(draft(), transcript())

    # "At a glance" is bold prose per the output format in SPEC.md §10; the rest
    # are headings so a reader can jump around.
    assert "**At a glance**" in out
    for heading in ("Decisions", "Action items", "Open questions", "Transcript"):
        assert f"## {heading}" in out


def test_each_section_heading_carries_a_time_range():
    out = render(draft(), transcript())

    assert re.search(r"## \d{2}:\d{2} – \d{2}:\d{2}\s+Status", out)


def test_action_items_render_owner_action_and_due():
    out = render(draft(), transcript())

    assert "Sam" in out
    assert "Fix the retry backoff" in out
    assert "Friday" in out


def test_an_ownerless_item_is_marked_unassigned():
    out = render(draft(), transcript())

    assert "Unassigned" in out


def test_citations_carry_a_timestamp():
    out = render(draft(), transcript())

    assert re.search(r"\[\d{2}:\d{2}:\d{2}\]", out)


def test_the_transcript_is_verbatim():
    out = render(draft(), transcript())
    transcript_section = out.split("## Transcript", 1)[1]

    assert TRANSCRIPT in transcript_section


def test_model_prose_never_leaks_into_the_transcript():
    out = render(draft(), transcript())
    transcript_section = out.split("## Transcript", 1)[1]

    assert "The migration is late." not in transcript_section
    assert "They discussed failure rates." not in transcript_section


def test_speaker_labels_appear_in_the_transcript():
    out = render(draft(), transcript())
    transcript_section = out.split("## Transcript", 1)[1]

    assert "Remote" in transcript_section
    assert "You" in transcript_section


def test_every_paragraph_appears_exactly_once():
    """Sections tile the meeting, so no paragraph may be dropped or duplicated."""
    from mt.paragraphs import build as build_paragraphs

    parsed = transcript()
    out = render(draft(), parsed)
    body = out.split("## Transcript", 1)[1]

    for paragraph in build_paragraphs(parsed):
        assert body.count(paragraph.text) == 1, paragraph.text


def test_an_inferred_owner_is_marked_as_suspected():
    from mt.note import ActionItem

    draft_with_inferred = NoteDraft(
        sections=(Section("All", 0.0, 120.0, ""),),
        actions=(ActionItem(owner="Sam", action="Fix it", due=None,
                            quote="one two three", start=1.0,
                            owner_confidence="inferred"),),
        decisions=(), questions=(),
    )

    out = render(draft_with_inferred, transcript())

    assert "Sam (suspected)" in out


def test_unverified_items_get_their_own_section():
    from mt.note import ActionItem

    draft_with_demoted = NoteDraft(
        sections=(Section("All", 0.0, 120.0, ""),),
        actions=(),
        decisions=(), questions=(),
        unverified=(ActionItem(owner="Priya", action="Send the budget", due=None,
                               quote="I will send it Thursday", start=0.0),),
    )

    out = render(draft_with_demoted, transcript())

    assert "## Unverified" in out
    assert "Send the budget" in out
    assert "could not be found" in out
