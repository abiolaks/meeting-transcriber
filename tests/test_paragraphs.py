"""Seam: paragraphs.build.

Paragraphs are what makes the transcript readable, and they are assembled
deterministically — the LLM never decides wording. The rules that matter: never
merge two speakers into one paragraph, and never let a paragraph grow into a wall.
"""

from mt.paragraphs import build
from mt.transcript import parse

FIVE_WORDS = "one two three four five"


def doc(segments, duration=120.0):
    return {
        "version": 1,
        "meeting": {"title": "T", "date": "2026-11-11", "duration_s": duration},
        "channels": [{"id": "ch0", "label": "You"}, {"id": "ch1", "label": "Remote"}],
        "segments": segments,
    }


def seg(i, start, end, channel, text):
    return {"id": f"s{i}", "start": start, "end": end, "channel": channel, "text": text}


def test_consecutive_turns_by_one_speaker_become_a_single_paragraph():
    t = parse(doc([
        seg(1, 0.0, 2.0, "ch1", FIVE_WORDS),
        seg(2, 2.0, 4.0, "ch1", FIVE_WORDS),
        seg(3, 4.0, 6.0, "ch1", FIVE_WORDS),
    ]))

    paragraphs = build(t)

    assert len(paragraphs) == 1
    assert paragraphs[0].word_count == 15
    assert paragraphs[0].start == 0.0
    assert paragraphs[0].end == 6.0
    assert paragraphs[0].label == "Remote"


def test_paragraphs_never_span_two_speakers():
    t = parse(doc([
        seg(1, 0.0, 2.0, "ch0", FIVE_WORDS),
        seg(2, 2.0, 4.0, "ch1", FIVE_WORDS),
        seg(3, 4.0, 6.0, "ch0", FIVE_WORDS),
    ]))

    paragraphs = build(t)

    assert [p.channel for p in paragraphs] == ["ch0", "ch1", "ch0"]


def test_a_paragraph_is_capped_by_word_count():
    segments = [seg(i, float(i), float(i) + 1.0, "ch1", FIVE_WORDS) for i in range(10)]
    t = parse(doc(segments))

    paragraphs = build(t, max_words=45)

    assert [p.word_count for p in paragraphs] == [45, 5]


def test_a_paragraph_is_capped_by_duration():
    segments = [seg(i, i * 10.0, i * 10.0 + 10.0, "ch1", FIVE_WORDS) for i in range(5)]
    t = parse(doc(segments))

    paragraphs = build(t, max_seconds=45.0)

    assert len(paragraphs) == 2
    assert paragraphs[0].end - paragraphs[0].start <= 45.0


def test_a_long_silence_starts_a_new_paragraph():
    t = parse(doc([
        seg(1, 0.0, 5.0, "ch1", FIVE_WORDS),
        seg(2, 30.0, 35.0, "ch1", FIVE_WORDS),
    ]))

    paragraphs = build(t, max_gap=2.0)

    assert len(paragraphs) == 2


def test_paragraphs_stay_in_time_order():
    t = parse(doc([
        seg(1, 0.0, 2.0, "ch0", FIVE_WORDS),
        seg(2, 2.0, 4.0, "ch1", FIVE_WORDS),
        seg(3, 4.0, 6.0, "ch1", FIVE_WORDS),
    ]))

    paragraphs = build(t)

    assert [p.start for p in paragraphs] == [0.0, 2.0]
