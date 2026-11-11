"""Ticket 03 seams: whisper JSON parsing, the adapter, and the CLI wiring.

The parser is a pure function over a payload, so most of this runs without a
model. The end-to-end test skips unless MT_WHISPER_MODEL, MT_WHISPER_BIN and
MT_WHISPER_WAV are set.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mt.asr import ASRError, parse_whisper_json, transcribe
from mt.transcript import parse

REPO_ROOT = Path(__file__).resolve().parents[1]


def payload(entries):
    """entries: (start_ms, end_ms, text)"""
    return {
        "transcription": [
            {"offsets": {"from": start, "to": end}, "text": f" {text}"}
            for start, end, text in entries
        ]
    }


def test_words_become_segments_with_second_offsets():
    doc = payload([
        (0, 400, "the"), (400, 700, "retry"), (700, 1100, "queue"),
        (1100, 1400, "is"), (1400, 1700, "broken"),
    ])

    transcript = parse_whisper_json(doc, title="t", date="2026-11-11")

    assert len(transcript.segments) == 1
    segment = transcript.segments[0]
    assert segment.text == "the retry queue is broken"
    assert segment.start == 0.0
    assert segment.end == 1.7
    assert len(segment.words) == 5
    assert segment.words[1].w == "retry"


def test_a_pause_starts_a_new_segment():
    doc = payload([
        (0, 400, "hello"), (400, 800, "there"),
        (5000, 5400, "again"),
    ])

    transcript = parse_whisper_json(doc, title="t", date="2026-11-11")

    assert [s.text for s in transcript.segments] == ["hello there", "again"]
    assert transcript.segments[1].start == 5.0


def test_empty_entries_are_ignored():
    doc = payload([(0, 10, ""), (0, 400, "real"), (400, 500, "  "), (500, 900, "words")])

    transcript = parse_whisper_json(doc, title="t", date="2026-11-11")

    assert transcript.segments[0].text == "real words"


def test_a_long_run_of_words_is_split_into_readable_segments():
    entries = [(i * 100, i * 100 + 100, f"w{i}") for i in range(30)]

    transcript = parse_whisper_json(payload(entries), title="t", date="2026-11-11")

    assert len(transcript.segments) >= 3
    assert all(len(s.words) <= 12 for s in transcript.segments)


def test_the_result_passes_the_transcript_schema_unchanged():
    doc = payload([(0, 400, "one"), (400, 900, "two"), (2000, 2400, "three")])

    transcript = parse_whisper_json(doc, title="t", date="2026-11-11")

    assert transcript.meeting.duration_s == 2.4
    assert transcript.label_for("ch0") == "You"


def test_a_transcript_survives_its_document_form():
    doc = payload([(0, 400, "one"), (400, 900, "two")])

    first = parse_whisper_json(doc, title="t", date="2026-11-11")
    second = parse(first.to_dict())

    assert [s.text for s in second.segments] == [s.text for s in first.segments]
    assert second.segments[0].words == first.segments[0].words


def test_an_empty_transcription_is_an_error_not_an_empty_note():
    with pytest.raises(ASRError, match="no speech"):
        parse_whisper_json(payload([(0, 10, "")]), title="t", date="2026-11-11")


def test_a_missing_model_is_reported_clearly(tmp_path):
    with pytest.raises(ASRError, match="model"):
        transcribe(tmp_path / "a.wav", tmp_path / "missing.bin", binary="whisper-cli")


def test_a_missing_audio_file_is_reported_clearly(tmp_path):
    model = tmp_path / "m.bin"
    model.write_bytes(b"not really a model")

    with pytest.raises(ASRError, match="audio"):
        transcribe(tmp_path / "absent.wav", model, binary="whisper-cli")


SAMPLE_SPEECH = (
    "The retry queue is the only thing that can still bite us. "
    "I will fix the backoff and add a dead letter queue by Friday."
)


def sample_wav(tmp_path: Path) -> Path | None:
    """Use MT_WHISPER_WAV if set, otherwise synthesise speech locally."""
    override = os.environ.get("MT_WHISPER_WAV")
    if override and Path(override).exists():
        return Path(override)
    if sys.platform != "darwin" or not (shutil.which("say") and shutil.which("ffmpeg")):
        return None
    aiff = tmp_path / "speech.aiff"
    wav = tmp_path / "speech.wav"
    subprocess.run(["say", "-o", str(aiff), SAMPLE_SPEECH], check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1",
         "-c:a", "pcm_s16le", str(wav)],
        check=True, capture_output=True,
    )
    return wav


def whisper_assets() -> tuple[Path, Path] | None:
    model = Path(os.environ.get("MT_WHISPER_MODEL", "models/ggml-base.en-q5_1.bin"))
    binary = Path(os.environ.get("MT_WHISPER_BIN", "vendor/whisper.cpp/build/bin/whisper-cli"))
    if model.exists() and binary.exists():
        return model, binary
    return None


def test_the_cli_writes_a_transcript_and_reports_rtf(tmp_path):
    assets = whisper_assets()
    wav = sample_wav(tmp_path)
    if assets is None or wav is None:
        pytest.skip("whisper binary/model or speech synthesis unavailable")

    model, binary = assets
    out = tmp_path / "t.json"
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT / "src"))
    result = subprocess.run(
        [sys.executable, "-m", "mt", "transcribe", str(wav),
         "--model", str(model), "--binary", str(binary), "--out", str(out)],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "rtf" in result.stdout.lower()
    parsed = parse(json.loads(out.read_text(encoding="utf-8")))
    assert parsed.segments
    assert all(segment.words for segment in parsed.segments)


def test_non_speech_tokens_never_become_words():
    doc = payload([
        (0, 400, "real"), (400, 800, "speech"),
        (800, 1200, "[BLANK_AUDIO]"), (1200, 9000, "(silence)"),
    ])

    transcript = parse_whisper_json(doc, title="t", date="2026-11-11")

    assert transcript.segments[0].text == "real speech"


def test_audio_duration_measures_the_file_not_the_last_word(tmp_path):
    import wave as wave_module

    path = tmp_path / "silence.wav"
    with wave_module.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 16000 * 3)

    from mt.asr import audio_duration

    assert audio_duration(path) == 3.0


def test_a_schema_violation_is_reported_as_an_asr_error():
    """A TranscriptError escaping as a traceback would look like a crash."""
    doc = payload([(0, 0, "zero"), (0, 0, "length")])

    with pytest.raises(ASRError, match="invalid transcript"):
        parse_whisper_json(doc, title="t", date="2026-11-11")


def test_the_channel_can_be_labelled_for_the_second_track():
    doc = payload([(0, 400, "hello")])

    transcript = parse_whisper_json(
        doc, title="t", date="2026-11-11", channel_id="ch1", label="Remote",
    )

    assert transcript.segments[0].channel == "ch1"
    assert transcript.label_for("ch1") == "Remote"
