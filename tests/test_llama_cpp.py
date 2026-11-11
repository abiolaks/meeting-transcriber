"""The real adapter's testable half: prompt, grammar, parsing.

None of these need a model. The model itself is exercised by the integration test
at the bottom, which skips unless MT_LLAMA_MODEL points at a GGUF.
"""

import json
import os
from pathlib import Path

import pytest

from mt.llama_cpp import GRAMMAR, MAX_TRANSCRIPT_CHARS, build_prompt, parse_draft, to_seconds
from mt.paragraphs import build as build_paragraphs
from mt.transcript import parse

FIVE_WORDS = "one two three four five"


def transcript():
    return parse({
        "version": 1,
        "meeting": {"title": "Weekly sync", "date": "2026-11-11", "duration_s": 120.0},
        "channels": [{"id": "ch0", "label": "You"}, {"id": "ch1", "label": "Remote"}],
        "segments": [
            {"id": "s1", "start": 0.0, "end": 30.0, "channel": "ch1", "text": FIVE_WORDS},
            {"id": "s2", "start": 30.0, "end": 60.0, "channel": "ch0", "text": FIVE_WORDS},
        ],
    })


def test_to_seconds_accepts_every_shape_a_model_emits():
    assert to_seconds(12.5) == 12.5
    assert to_seconds("12.5") == 12.5
    assert to_seconds("03:22") == 202.0
    assert to_seconds("01:02:03") == 3723.0


def test_to_seconds_rejects_nonsense():
    with pytest.raises(ValueError):
        to_seconds("soon")
    with pytest.raises(ValueError):
        to_seconds(True)


def test_the_prompt_carries_the_schema_and_the_transcript():
    parsed = transcript()
    prompt = build_prompt(parsed.meeting, build_paragraphs(parsed))

    assert '"sections"' in prompt
    assert "copied word for word" in prompt
    assert FIVE_WORDS in prompt
    assert "[00:00] Remote" in prompt


def test_a_very_long_transcript_is_truncated_rather_than_crashing():
    parsed = transcript()
    paragraphs = build_paragraphs(parsed)
    long = build_prompt(parsed.meeting, list(paragraphs) * 400)

    assert "[transcript truncated]" in long
    # Transcript is capped; the instructions and schema ride on top.
    assert len(long) < MAX_TRANSCRIPT_CHARS + 2_000


def test_the_grammar_declares_a_json_root():
    assert "root" in GRAMMAR
    assert "object" in GRAMMAR


def test_parsing_a_well_formed_draft():
    payload = {
        "sections": [{"title": "Opening", "start": 0, "end": "01:00", "summary": "They agreed."}],
        "actions": [{"owner": "Sam", "action": "Fix it", "due": "Friday",
                     "quote": "I will fix it", "start": "00:12"}],
        "decisions": [{"text": "Ship on the 20th", "start": 45}],
        "questions": ["When do we freeze?"],
    }

    draft = parse_draft(json.dumps(payload))

    assert draft.sections[0].end == 60.0
    assert draft.actions[0].owner == "Sam"
    assert draft.actions[0].start == 12.0
    assert draft.decisions[0].text == "Ship on the 20th"
    assert draft.questions == ("When do we freeze?",)


def test_parsing_tolerates_prose_around_the_json():
    text = 'Here is the note:\n{"sections": [], "actions": [], "decisions": []}\nDone.'

    draft = parse_draft(text)

    assert draft.sections == ()


def test_parsing_rejects_output_with_no_json():
    with pytest.raises(ValueError, match="JSON"):
        parse_draft("I am afraid I cannot do that.")


def test_malformed_entries_are_dropped_not_fatal():
    payload = {
        "sections": [
            {"title": "Good", "start": 0, "end": 60, "summary": ""},
            {"title": "No times"},
        ],
        "actions": [{"action": "Keep me", "start": 5}, {"start": 6}],
        "decisions": [],
        "questions": [],
    }

    draft = parse_draft(json.dumps(payload))

    assert [s.title for s in draft.sections] == ["Good"]
    assert [a.action for a in draft.actions] == ["Keep me"]
    assert draft.actions[0].owner is None


@pytest.mark.skipif(
    not os.environ.get("MT_LLAMA_MODEL"),
    reason="set MT_LLAMA_MODEL to a GGUF path to run the real model",
)
def test_the_real_model_produces_a_parseable_draft():
    from mt.llama_cpp import LlamaCppLLM

    parsed = transcript()
    llm = LlamaCppLLM(
        os.environ["MT_LLAMA_MODEL"],
        binary=os.environ.get("MT_LLAMA_BIN", "llama-cli"),
        max_tokens=400,
    )

    draft = llm.draft(parsed.meeting, build_paragraphs(parsed))

    assert draft.sections, "model returned no sections"
    assert Path(os.environ["MT_LLAMA_MODEL"]).exists()


def test_the_string_null_is_not_treated_as_a_person():
    payload = {
        "sections": [], "decisions": [], "questions": [],
        "actions": [
            {"owner": "null", "action": "Fix it", "start": 1},
            {"owner": "none", "action": "Ship it", "start": 2},
            {"owner": "Remote", "action": "Draft it", "start": 3},
        ],
    }

    draft = parse_draft(json.dumps(payload))

    assert [a.owner for a in draft.actions] == [None, None, "Remote"]
