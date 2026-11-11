"""Seam: verify.verify.

Grounding is the difference between a note that is incomplete and a note that is
confidently wrong. Each action item is placed by finding its quote in the
transcript; anything that cannot be found is demoted, never silently kept.
"""

import pytest

from mt.note import ActionItem, Decision, NoteDraft, Section
from mt.paragraphs import build as build_paragraphs
from mt.transcript import parse
from mt.verify import GroundingError, classify_owner, normalise, verify

SPOKEN = "I will fix the backoff and add a dead letter queue by Friday."


def transcript():
    return parse({
        "version": 1,
        "meeting": {"title": "T", "date": "2026-11-11", "duration_s": 120.0},
        "channels": [{"id": "ch0", "label": "You"}, {"id": "ch1", "label": "Remote"}],
        "segments": [
            {"id": "s1", "start": 5.0, "end": 20.0, "channel": "ch1", "text": SPOKEN},
            {"id": "s2", "start": 20.0, "end": 30.0, "channel": "ch0", "text": "Agreed, ship on the twentieth."},
        ],
    })


def draft(*actions, decisions=()):
    return NoteDraft(
        sections=(Section("All", 0.0, 120.0, "Summary."),),
        actions=tuple(actions),
        decisions=tuple(decisions),
    )


def test_a_quote_that_was_spoken_is_kept_and_placed():
    item = ActionItem(owner="Sam", action="Fix the backoff", due="Friday",
                      quote="fix the backoff and add a dead letter queue", start=99.0)

    result = verify(draft(item), build_paragraphs(transcript()))

    assert result.verified == 1
    assert result.draft.actions[0].start == 5.0, "timestamp comes from the transcript"


def test_an_invented_quote_is_demoted_not_deleted():
    """One bad item among good ones is demoted; the note still gets written."""
    good = ActionItem(owner="Sam", action="Fix the backoff", due="Friday",
                      quote="fix the backoff", start=0.0)
    bad = ActionItem(owner="Priya", action="Send the budget", due=None,
                     quote="I will send it Thursday", start=0.0)

    result = verify(draft(good, bad), build_paragraphs(transcript()))

    assert [a.action for a in result.draft.actions] == ["Fix the backoff"]
    assert [a.action for a in result.draft.unverified] == ["Send the budget"]
    assert result.verified == 1 and result.unverified == 1


def test_a_wholly_invented_draft_raises():
    item = ActionItem(owner=None, action="Something", due=None, quote="never said", start=0.0)

    with pytest.raises(GroundingError, match="invented"):
        verify(draft(item), build_paragraphs(transcript()))


def test_normalisation_ignores_case_and_punctuation():
    item = ActionItem(owner=None, action="A", due=None,
                      quote="FIX the backoff, and add a dead-letter queue!", start=0)

    result = verify(draft(item), build_paragraphs(transcript()))

    assert result.verified == 1


def test_stated_versus_inferred_owner():
    assert classify_owner("Sam", "I will fix it") == "stated"
    assert classify_owner("Sam", "the queue is broken") == "inferred"
    assert classify_owner(None, "I will fix it") == "unassigned"


def test_the_confidence_is_recorded_on_the_kept_item():
    item = ActionItem(owner="Sam", action="Fix", due=None,
                      quote="I will fix the backoff", start=0)

    result = verify(draft(item), build_paragraphs(transcript()))

    assert result.draft.actions[0].owner_confidence == "stated"


def test_decisions_are_carried_through_unchanged():
    result = verify(
        draft(decisions=(Decision("Ship on the twentieth", 45.0),)),
        build_paragraphs(transcript()),
    )

    assert result.draft.decisions[0].text == "Ship on the twentieth"


def test_normalise_strips_punctuation_and_case():
    assert normalise("Hello,  WORLD!") == "hello world"
