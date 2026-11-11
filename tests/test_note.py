"""Seam: note.build.

The LLM proposes where topics begin and end. It will get that wrong sometimes —
gaps, overlaps, backwards ranges, or nothing usable at all. The orchestrator's
job is to turn any of that into sections that tile the meeting exactly once and
that cite moments which actually occur in the transcript.

When nothing usable comes back, we retry once and then fail. We never invent
sections: a note with fabricated structure looks like it covered the meeting.
"""

import pytest

from mt.note import ActionItem, Decision, NoteDraft, NoteError, Section, build
from mt.transcript import parse

FIVE_WORDS = "one two three four five"


def doc(segments, duration=120.0):
    return {
        "version": 1,
        "meeting": {"title": "Weekly sync", "date": "2026-11-11", "duration_s": duration},
        "channels": [{"id": "ch0", "label": "You"}, {"id": "ch1", "label": "Remote"}],
        "segments": segments,
    }


def transcript(duration=120.0):
    return parse(doc(
        [{"id": f"s{i}", "start": i * 10.0, "end": i * 10.0 + 10.0, "channel": "ch1",
          "text": FIVE_WORDS} for i in range(int(duration // 10))],
        duration=duration,
    ))


class Stub:
    def __init__(self, sections=(), actions=(), decisions=()):
        self.sections = list(sections)
        self.actions = list(actions)
        self.decisions = list(decisions)
        self.calls = 0

    def draft(self, meeting, paragraphs):
        self.calls += 1
        return NoteDraft(
            sections=tuple(self.sections),
            actions=tuple(self.actions),
            decisions=tuple(self.decisions),
            questions=(),
        )


class FlakyStub:
    """Fails once, then returns something usable — tests the one retry."""

    def __init__(self, good_sections):
        self.good_sections = list(good_sections)
        self.calls = 0

    def draft(self, meeting, paragraphs):
        self.calls += 1
        sections = [] if self.calls == 1 else self.good_sections
        return NoteDraft(sections=tuple(sections), actions=(), decisions=(), questions=())


def assert_tiles(note, duration):
    assert note.sections, "expected at least one section"
    assert note.sections[0].start == 0.0
    assert note.sections[-1].end <= duration
    for earlier, later in zip(note.sections, note.sections[1:]):
        assert earlier.end == later.start


def test_well_formed_sections_survive_with_their_titles():
    llm = Stub([
        Section("Opening", 0.0, 60.0, "They said hello."),
        Section("Close", 60.0, 120.0, "They said goodbye."),
    ])

    note = build(transcript(120.0), llm)

    assert [s.title for s in note.sections] == ["Opening", "Close"]
    assert_tiles(note, 120.0)


def test_a_gap_between_sections_is_closed():
    llm = Stub([Section("A", 0.0, 30.0, ""), Section("B", 60.0, 120.0, "")])

    note = build(transcript(120.0), llm)

    assert_tiles(note, 120.0)


def test_an_overlap_is_clipped_not_double_counted():
    llm = Stub([Section("A", 0.0, 70.0, ""), Section("B", 50.0, 120.0, "")])

    note = build(transcript(120.0), llm)

    assert_tiles(note, 120.0)


def test_sections_out_of_order_are_sorted():
    llm = Stub([Section("B", 60.0, 120.0, ""), Section("A", 0.0, 60.0, "")])

    note = build(transcript(120.0), llm)

    assert [s.title for s in note.sections] == ["A", "B"]


def test_the_first_section_is_stretched_back_to_zero():
    llm = Stub([Section("Late start", 40.0, 120.0, "")])

    note = build(transcript(120.0), llm)

    assert note.sections[0].start == 0.0


def test_backwards_and_zero_length_sections_are_discarded():
    llm = Stub([
        Section("Good", 0.0, 60.0, ""),
        Section("Backwards", 90.0, 80.0, ""),
        Section("Empty", 70.0, 70.0, ""),
    ])

    note = build(transcript(120.0), llm)

    assert [s.title for s in note.sections] == ["Good"]


def test_boundaries_are_anchored_to_real_paragraph_starts():
    llm = Stub([Section("A", 0.0, 63.0, ""), Section("B", 63.0, 120.0, "")])

    note = build(transcript(120.0), llm)

    # Paragraphs merge to 40s, so the nearest real boundary after 63s is 80s.
    assert note.sections[0].end == 80.0
    assert note.sections[1].start == 80.0


def test_the_last_section_ends_at_the_last_word_not_past_it():
    llm = Stub([Section("Everything", 0.0, 120.0, "")])

    note = build(transcript(120.0), llm)

    assert note.sections[-1].end == 120.0


def test_unusable_sections_are_retried_once_then_fail_loudly():
    llm = Stub([Section("Junk", 500.0, 400.0, "")])

    with pytest.raises(NoteError):
        build(transcript(600.0), llm)

    assert llm.calls == 2, "expected exactly one retry"


def test_a_single_retry_is_enough_when_the_second_attempt_works():
    llm = FlakyStub([Section("Real", 0.0, 120.0, "")])

    note = build(transcript(120.0), llm)

    assert [s.title for s in note.sections] == ["Real"]
    assert llm.calls == 2


def test_action_items_and_decisions_survive_the_round_trip():
    llm = Stub(
        sections=[Section("All", 0.0, 120.0, "")],
        actions=[ActionItem(
            owner="Sam", action="Fix the backoff", due="Friday",
            quote="I'll fix the backoff", start=12.0,
        )],
        decisions=[Decision("Ship on the 20th", 30.0)],
    )

    note = build(transcript(120.0), llm)

    assert note.actions[0].owner == "Sam"
    assert note.decisions[0].text == "Ship on the 20th"
