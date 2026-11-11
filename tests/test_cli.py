"""Seam: the CLI, end to end.

This is the wiring test: a transcript file goes in, a note comes out. It uses the
fake model, so it says nothing about note quality — only that the pieces are
connected and the output has the shape a reader expects.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def write_transcript(path: Path) -> None:
    path.write_text(
        """
        {
          "version": 1,
          "meeting": {"title": "Weekly sync", "date": "2026-11-12", "duration_s": 300.0},
          "channels": [{"id": "ch0", "label": "You"}, {"id": "ch1", "label": "Remote"}],
          "segments": [
            {"id": "s1", "start": 0.0, "end": 40.0, "channel": "ch1",
             "text": "We are two weeks behind on the billing migration."},
            {"id": "s2", "start": 40.0, "end": 80.0, "channel": "ch0",
             "text": "What is the failure rate on the retries?"},
            {"id": "s3", "start": 80.0, "end": 140.0, "channel": "ch1",
             "text": "About four percent fail on the third attempt. I'll fix the backoff by Friday."},
            {"id": "s4", "start": 140.0, "end": 200.0, "channel": "ch0",
             "text": "Agreed. Let's call it the twentieth."},
            {"id": "s5", "start": 200.0, "end": 300.0, "channel": "ch1",
             "text": "I will update the release calendar today."}
          ]
        }
        """,
        encoding="utf-8",
    )


def run_cli(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(cwd / "src")
    return subprocess.run(
        [sys.executable, "-m", "mt", *args],
        cwd=cwd, env=env, capture_output=True, text=True,
    )


def test_cli_writes_a_note(tmp_path):
    transcript = tmp_path / "t.json"
    out = tmp_path / "note.md"
    write_transcript(transcript)

    result = run_cli("note", str(transcript), "--out", str(out))

    assert result.returncode == 0, result.stderr
    assert out.exists()
    assert "Weekly sync" in out.read_text(encoding="utf-8")


def test_the_note_contains_action_items_from_the_meeting(tmp_path):
    transcript = tmp_path / "t.json"
    out = tmp_path / "note.md"
    write_transcript(transcript)

    run_cli("note", str(transcript), "--out", str(out))
    text = out.read_text(encoding="utf-8")

    assert "Action items" in text
    assert "backoff" in text


def test_a_malformed_transcript_fails_with_a_useful_message(tmp_path):
    transcript = tmp_path / "bad.json"
    transcript.write_text('{"version": 1}', encoding="utf-8")

    result = run_cli("note", str(transcript), "--out", str(tmp_path / "n.md"))

    assert result.returncode == 2
    assert "meeting" in result.stderr or "channels" in result.stderr


def test_the_llama_adapter_refuses_cleanly_until_it_exists(tmp_path):
    transcript = tmp_path / "t.json"
    write_transcript(transcript)

    result = run_cli("note", str(transcript), "--out", str(tmp_path / "n.md"), "--llm", "llama")

    assert result.returncode == 3
    assert "not implemented" in result.stderr.lower()
