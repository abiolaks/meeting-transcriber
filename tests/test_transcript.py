"""Seam: transcript.load / transcript.parse.

The transcript is the contract between ASR (ticket 03), the merger (04) and the
note generator (01). If it accepts garbage, every stage downstream inherits it.
"""

import json

import pytest

from mt.transcript import TranscriptError, load, parse


def valid_doc():
    return {
        "version": 1,
        "meeting": {"title": "Weekly sync", "date": "2026-11-11", "duration_s": 120.0},
        "channels": [
            {"id": "ch0", "label": "You"},
            {"id": "ch1", "label": "Remote"},
        ],
        "segments": [
            {"id": "s1", "start": 0.0, "end": 4.0, "channel": "ch0", "text": "Morning."},
            {"id": "s2", "start": 4.0, "end": 9.5, "channel": "ch1", "text": "Morning, all."},
        ],
    }


def test_loads_a_valid_transcript():
    t = parse(valid_doc())

    assert t.meeting.title == "Weekly sync"
    assert t.meeting.duration_s == 120.0
    assert [c.id for c in t.channels] == ["ch0", "ch1"]
    assert [s.text for s in t.segments] == ["Morning.", "Morning, all."]
    assert t.label_for("ch1") == "Remote"


def test_load_reads_from_disk(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(json.dumps(valid_doc()), encoding="utf-8")

    assert load(path).meeting.title == "Weekly sync"


def test_missing_top_level_field_names_it():
    doc = valid_doc()
    del doc["segments"]

    with pytest.raises(TranscriptError, match="segments"):
        parse(doc)


def test_bad_segment_field_is_named_precisely():
    doc = valid_doc()
    del doc["segments"][1]["text"]

    with pytest.raises(TranscriptError, match=r"segments\[1\].*text"):
        parse(doc)


def test_unknown_channel_is_rejected():
    doc = valid_doc()
    doc["segments"][0]["channel"] = "ch9"

    with pytest.raises(TranscriptError, match="ch9"):
        parse(doc)


def test_segment_ending_before_it_starts_is_rejected():
    doc = valid_doc()
    doc["segments"][0]["end"] = -1.0

    with pytest.raises(TranscriptError, match=r"segments\[0\]"):
        parse(doc)


def test_segments_must_be_in_time_order():
    doc = valid_doc()
    doc["segments"].reverse()

    with pytest.raises(TranscriptError, match="order"):
        parse(doc)


def test_word_timings_must_lie_inside_their_segment():
    doc = valid_doc()
    doc["segments"][0]["words"] = [{"w": "Morning.", "start": 0.0, "end": 99.0}]

    with pytest.raises(TranscriptError, match=r"segments\[0\].*word"):
        parse(doc)


def test_unique_channel_ids_are_required():
    doc = valid_doc()
    doc["channels"][1]["id"] = "ch0"

    with pytest.raises(TranscriptError, match="ch0"):
        parse(doc)
