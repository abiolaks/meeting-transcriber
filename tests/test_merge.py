"""Seam: merge.merge, and the `mt merge` command.

Two transcripts (mic and loopback) become one timeline. The interesting cases are
overlap and echo: simultaneous speech must interleave rather than concatenate, and
the speakerphone case — the same voice arriving on both channels — must be counted
once.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mt.merge import MergeError, merge
from mt.transcript import parse

REPO_ROOT = Path(__file__).resolve().parents[1]


def channel_transcript(channel: str, label: str, segments):
    return parse({
        "version": 1,
        "meeting": {"title": "T", "date": "2026-11-11",
                    "duration_s": max(end for _, end, _ in segments)},
        "channels": [{"id": channel, "label": label}],
        "segments": [
            {"id": f"s{i}", "start": start, "end": end, "channel": channel, "text": text}
            for i, (start, end, text) in enumerate(segments)
        ],
    })


def mic(*segments):
    return channel_transcript("ch0", "You", list(segments))


def remote(*segments):
    return channel_transcript("ch1", "Remote", list(segments))


def test_both_channels_and_labels_survive():
    result = merge([mic((0.0, 2.0, "hello")), remote((2.0, 4.0, "hi there"))])

    assert [c.id for c in result.transcript.channels] == ["ch0", "ch1"]
    assert result.transcript.label_for("ch0") == "You"
    assert result.transcript.label_for("ch1") == "Remote"


def test_segments_are_ordered_by_time():
    result = merge([mic((5.0, 7.0, "later")), remote((0.0, 2.0, "first"))])

    assert [s.text for s in result.transcript.segments] == ["first", "later"]


def test_simultaneous_speech_interleaves_rather_than_concatenates():
    result = merge([
        mic((0.0, 4.0, "i am talking")),
        remote((2.0, 6.0, "so am i")),
    ])

    assert [s.text for s in result.transcript.segments] == ["i am talking", "so am i"]
    assert [s.start for s in result.transcript.segments] == [0.0, 2.0]


def test_echo_of_the_same_speech_is_counted_once():
    text = "the retry queue is the only thing that can still bite us"
    result = merge([
        remote((10.0, 14.0, text)),
        mic((10.4, 14.6, text)),  # speakerphone: the same voice through the mic
    ])

    assert len(result.transcript.segments) == 1
    assert result.transcript.segments[0].channel == "ch1", "keep the clean loopback copy"
    assert result.echoes_removed == 1


def test_a_near_paraphrase_of_the_echo_is_still_dropped():
    result = merge([
        remote((10.0, 14.0, "the retry queue is the only thing that can bite us")),
        mic((10.3, 14.4, "the retry queue is the only thing that can still bite us")),
    ])

    assert len(result.transcript.segments) == 1
    assert result.echoes_removed == 1


def test_two_people_talking_at_once_are_both_kept():
    result = merge([
        remote((10.0, 14.0, "we should ship on the twentieth")),
        mic((10.2, 13.0, "no, that is too early for the soak test")),
    ])

    assert len(result.transcript.segments) == 2
    assert result.echoes_removed == 0


def test_the_same_words_long_afterwards_are_not_an_echo():
    text = "agreed"
    result = merge([remote((0.0, 1.0, text)), mic((60.0, 61.0, text))])

    assert len(result.transcript.segments) == 2
    assert result.echoes_removed == 0


def test_the_merged_result_is_valid_and_has_unique_segment_ids():
    result = merge([
        mic((0.0, 2.0, "one"), (3.0, 4.0, "two")),
        remote((1.0, 2.5, "other")),
    ])

    ids = [s.id for s in result.transcript.segments]
    assert len(ids) == len(set(ids))
    assert parse(result.transcript.to_dict()).meeting.duration_s == result.transcript.meeting.duration_s


def test_duration_covers_the_last_word_on_either_channel():
    result = merge([mic((0.0, 2.0, "short")), remote((0.0, 90.0, "long"))])

    assert result.transcript.meeting.duration_s == 90.0


def test_duplicate_channel_ids_are_rejected():
    with pytest.raises(MergeError, match="ch0"):
        merge([mic((0.0, 1.0, "a")), mic((1.0, 2.0, "b"))])


def test_the_cli_merges_two_files(tmp_path):
    left, right, out = tmp_path / "mic.json", tmp_path / "remote.json", tmp_path / "merged.json"
    left.write_text(json.dumps(mic((0.0, 2.0, "hello")).to_dict()), encoding="utf-8")
    right.write_text(json.dumps(remote((1.0, 3.0, "hi")).to_dict()), encoding="utf-8")

    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT / "src"))
    result = subprocess.run(
        [sys.executable, "-m", "mt", "merge", str(left), str(right), "--out", str(out)],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    merged = parse(json.loads(out.read_text(encoding="utf-8")))
    assert [s.text for s in merged.segments] == ["hello", "hi"]


def test_echo_is_detected_when_the_mic_copy_sorts_first():
    """Equal start times must not defeat echo detection.

    Sorting by (start, channel) puts ch0 first, so a rule that only inspects the
    incoming segment silently keeps both copies.
    """
    text = "the retry queue is the only thing that can still bite us"
    result = merge([
        mic((10.0, 14.0, text)),
        remote((10.0, 14.0, text)),
    ])

    assert len(result.transcript.segments) == 1
    assert result.transcript.segments[0].channel == "ch1"
    assert result.echoes_removed == 1


def test_the_loopback_copy_replaces_the_mic_copy_in_place():
    text = "we should freeze feature work until the twentieth"
    result = merge([mic((5.0, 9.0, text)), remote((5.0, 9.0, text))])

    segment = result.transcript.segments[0]
    assert segment.channel == "ch1"
    assert segment.start == 5.0


def test_colliding_labels_are_made_distinct():
    """Two transcripts both defaulting to "You" must not merge into You/You."""
    both_you = parse({
        "version": 1,
        "meeting": {"title": "T", "date": "2026-11-11", "duration_s": 3.0},
        "channels": [{"id": "ch0", "label": "You"}],
        "segments": [{"id": "s0", "start": 0.0, "end": 2.0, "channel": "ch0", "text": "hello"}],
    })
    second = parse({
        "version": 1,
        "meeting": {"title": "T", "date": "2026-11-11", "duration_s": 4.0},
        "channels": [{"id": "ch1", "label": "You"}],
        "segments": [{"id": "s0", "start": 2.0, "end": 4.0, "channel": "ch1", "text": "hi there"}],
    })

    result = merge([both_you, second])

    assert result.transcript.label_for("ch0") == "You"
    assert result.transcript.label_for("ch1") == "Remote"


def test_simultaneous_short_utterances_are_both_kept():
    """Two people saying "yes" at once is crosstalk, not speakerphone echo."""
    result = merge([mic((10.0, 10.6, "yes")), remote((10.1, 10.7, "yes"))])

    assert len(result.transcript.segments) == 2
    assert result.echoes_removed == 0


def test_channel_identity_reaches_the_rendered_note():
    from mt.note import NoteDraft, Section, build
    from mt.render import render

    class Stub:
        def draft(self, meeting, paragraphs):
            return NoteDraft(
                sections=(Section("All", 0.0, meeting.duration_s, "They talked."),),
                actions=(), decisions=(), questions=(),
            )

    merged = merge([mic((0.0, 3.0, "can you draft it")), remote((3.0, 6.0, "yes i will"))])
    note = render(build(merged.transcript, Stub()), merged.transcript)
    transcript_section = note.split("## Transcript", 1)[1]

    assert "Remote" in transcript_section
    assert "You" in transcript_section


def test_the_cli_warns_when_speakerphone_echo_is_removed(tmp_path):
    text = "the retry queue is the only thing that can still bite us"
    left, right, out = tmp_path / "mic.json", tmp_path / "remote.json", tmp_path / "m.json"
    left.write_text(json.dumps(mic((10.0, 14.0, text)).to_dict()), encoding="utf-8")
    right.write_text(json.dumps(remote((10.0, 14.0, text)).to_dict()), encoding="utf-8")

    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT / "src"))
    result = subprocess.run(
        [sys.executable, "-m", "mt", "merge", str(left), str(right), "--out", str(out)],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "speakers" in result.stderr.lower()
