"""Seams: pipeline.process_transcripts and evaluate's two metrics.

The pipeline test uses the fake model and hand-built transcripts, so it says
nothing about model quality — only that both channels reach the note intact.
"""

from mt.evaluate import report, score_actions, word_error_rate
from mt.note import ActionItem, NoteDraft, Section
from mt.pipeline import process_transcripts
from mt.transcript import parse

MIC = "Can you draft the runbook by Thursday"
REMOTE = "I will fix the backoff and add a dead letter queue"


def transcript(channel, label, text, start, end):
    return parse({
        "version": 1,
        "meeting": {"title": "Weekly", "date": "2026-11-11", "duration_s": end},
        "channels": [{"id": channel, "label": label}],
        "segments": [{"id": "s1", "start": start, "end": end, "channel": channel, "text": text}],
    })


class Stub:
    def __init__(self, draft):
        self._draft = draft

    def draft(self, meeting, paragraphs):
        return self._draft


def notes():
    return NoteDraft(
        sections=(Section("All", 0.0, 120.0, "They planned the work."),),
        actions=(ActionItem(owner="Remote", action="Fix the backoff", due="Friday",
                            quote="I will fix the backoff", start=0.0),),
        decisions=(), questions=(),
    )


def test_both_channels_reach_the_note():
    result = process_transcripts(
        transcript("ch0", "You", MIC, 0.0, 4.0),
        transcript("ch1", "Remote", REMOTE, 4.0, 9.0),
        Stub(notes()),
    )

    assert result.transcript.label_for("ch0") == "You"
    assert result.transcript.label_for("ch1") == "Remote"
    assert MIC in result.markdown
    assert REMOTE in result.markdown


def test_the_pipeline_reports_stage_timings():
    result = process_transcripts(
        transcript("ch0", "You", MIC, 0.0, 4.0),
        transcript("ch1", "Remote", REMOTE, 4.0, 9.0),
        Stub(notes()),
    )

    assert "note" in result.timings


def test_word_error_rate_is_zero_for_identical_text():
    assert word_error_rate("the retry queue is broken", "the retry queue is broken") == 0.0


def test_word_error_rate_counts_a_substitution():
    # five words, one substitution
    assert word_error_rate("the retry queue is broken", "the retry queue is fixed") == 0.2


def test_word_error_rate_handles_an_empty_hypothesis():
    assert word_error_rate("one two three four", "") == 1.0


def test_action_scoring_perfect_match():
    scores = score_actions(
        ["fix the backoff by Friday", "draft the runbook"],
        ["fix the backoff by Friday", "draft the runbook"],
    )

    assert scores.precision == 1.0
    assert scores.recall == 1.0
    assert scores.matched == 2


def test_action_scoring_penalises_invention_and_omission():
    scores = score_actions(
        ["fix the backoff by Friday", "buy a new laptop"],
        ["fix the backoff by Friday", "draft the runbook"],
    )

    assert scores.precision == 0.5
    assert scores.recall == 0.5
    assert scores.matched == 1


def test_a_near_paraphrase_still_counts_as_a_match():
    scores = score_actions(
        ["fix the backoff and add a dead letter queue by Friday"],
        ["fix the backoff and add a dead letter queue"],
    )

    assert scores.matched == 1


def test_the_report_is_markdown_ready():
    text = report({"all": ("a b c", "a b c")}, score_actions(["x"], ["x"]))

    assert "| WER all | 0.000 |" in text
    assert "| action precision | 1.000 |" in text
