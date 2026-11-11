"""Speech recognition adapter: a WAV file in, a validated transcript out.

whisper.cpp is invoked with `-ml 1 -sow`, which in practice emits one entry per
word carrying millisecond offsets. (`-ml` is a character limit; the word-per-entry
result is incidental, so the parser must not depend on it.) Those words are regrouped here into readable
segments — a pause starts a new one — and every word's timing is kept, because
citations depend on them.

The result is built from the same dataclasses every other stage uses and then
validated through `parse`, so a malformed adapter output fails here rather than
halfway through note generation.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from datetime import date as date_type
from pathlib import Path
from typing import Any, Sequence

from .transcript import Channel, Meeting, Segment, Transcript, TranscriptError, Word, parse

DEFAULT_BINARY = "whisper-cli"
GAP_SECONDS = 1.0
MAX_WORDS_PER_SEGMENT = 12

# whisper emits these instead of words when it hears a gap or noise. They are not
# speech and must never reach a transcript.
NON_SPEECH = {
    "[blank_audio]", "[silence]", "(silence)", "[music]", "(music)",
    "[applause]", "(applause)", "[inaudible]",
}


def default_threads() -> int:
    """Physical cores minus one, so the meeting app keeps a core (SPEC §4-S2)."""
    logical = os.cpu_count() or 2
    return max(1, logical // 2 - 1)


def audio_duration(path: str | Path) -> float:
    """Real audio length, not the end of the last recognised word.

    Using the last word as the denominator inflates RTF on any clip that ends in
    silence, and on a 60s file with 11s of speech it reported 0.19 instead of
    0.13.
    """
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


class ASRError(RuntimeError):
    """Speech recognition could not produce a transcript."""


@dataclass(frozen=True)
class TranscriptionResult:
    transcript: Transcript
    elapsed_s: float
    audio_s: float

    @property
    def rtf(self) -> float:
        """Processing time divided by audio duration. Lower is better.

        Includes process start and model load, which is negligible on a real
        meeting and dominant on a few seconds of audio.
        """
        return self.elapsed_s / self.audio_s if self.audio_s else 0.0


def _words_from_payload(payload: dict[str, Any]) -> list[Word]:
    words: list[Word] = []
    for entry in payload.get("transcription", []):
        text = str(entry.get("text", "")).strip()
        if not text or text.lower().strip(" .") in NON_SPEECH:
            continue
        offsets = entry.get("offsets") or {}
        try:
            start = float(offsets["from"]) / 1000.0
            end = float(offsets["to"]) / 1000.0
        except (KeyError, TypeError, ValueError):
            continue
        if end < start:
            start, end = end, start
        words.append(Word(w=text, start=start, end=end))
    return words


def _group_words(words: Sequence[Word]) -> list[list[Word]]:
    """Split a word stream into readable segments at pauses or length limits."""
    groups: list[list[Word]] = []
    current: list[Word] = []

    for word in words:
        if current:
            too_long = len(current) >= MAX_WORDS_PER_SEGMENT
            big_pause = word.start - current[-1].end > GAP_SECONDS
            if too_long or big_pause:
                groups.append(current)
                current = []
        current.append(word)

    if current:
        groups.append(current)
    return groups


def parse_whisper_json(
    payload: dict[str, Any],
    *,
    title: str,
    date: str,
    channel_id: str = "ch0",
    label: str = "You",
) -> Transcript:
    """Turn whisper.cpp's JSON into a schema-valid transcript."""
    words = _words_from_payload(payload)
    if not words:
        raise ASRError("whisper produced no speech in this audio")

    segments = tuple(
        Segment(
            id=f"s{index + 1:04d}",
            start=round(group[0].start, 3),
            end=round(group[-1].end, 3),
            channel=channel_id,
            text=" ".join(word.w for word in group),
            words=tuple(group),
        )
        for index, group in enumerate(_group_words(words))
    )

    transcript = Transcript(
        meeting=Meeting(
            title=title,
            date=date,
            duration_s=round(max(segment.end for segment in segments), 3),
        ),
        channels=(Channel(id=channel_id, label=label),),
        segments=segments,
    )
    # Round-trip through the validator: the adapter is not the authority on the
    # schema, and a break here should surface at this seam.
    try:
        return parse(transcript.to_dict())
    except TranscriptError as exc:
        raise ASRError(f"whisper produced an invalid transcript: {exc}") from exc


def _run_whisper(
    wav: Path, model: Path, binary: str, threads: int, output_prefix: Path
) -> None:
    command = [
        binary,
        "-m", str(model),
        "-f", str(wav),
        "-oj",
        "-ml", "1",
        "-sow",
        "-t", str(threads),
        "-l", "en",
        "-np",
        "-of", str(output_prefix),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise ASRError(f"whisper binary not found: {binary}") from exc
    if result.returncode != 0:
        raise ASRError(
            f"whisper exited {result.returncode}: {result.stderr.strip()[:300]}"
        )


def transcribe(
    wav: str | Path,
    model: str | Path,
    *,
    binary: str = DEFAULT_BINARY,
    threads: int | None = None,
    channel_id: str = "ch0",
    label: str = "You",
    title: str | None = None,
    date: str | None = None,
) -> TranscriptionResult:
    """Transcribe one WAV file locally. No network access."""
    wav_path = Path(wav)
    model_path = Path(model)

    if not wav_path.exists():
        raise ASRError(f"audio file not found: {wav_path}")
    if not model_path.exists():
        raise ASRError(
            f"model file not found: {model_path} — fetch ggml-small.en-q5_1.bin "
            "or another whisper.cpp model (SPEC §12)"
        )

    with tempfile.TemporaryDirectory() as directory:
        prefix = Path(directory) / "out"
        started = time.monotonic()
        _run_whisper(wav_path, model_path, binary, threads or default_threads(), prefix)
        elapsed = time.monotonic() - started

        json_path = prefix.with_suffix(".json")
        if not json_path.exists():
            raise ASRError("whisper did not write a JSON result")
        payload = json.loads(json_path.read_text(encoding="utf-8"))

    transcript = parse_whisper_json(
        payload,
        title=title or wav_path.stem,
        date=date or date_type.today().isoformat(),
        channel_id=channel_id,
        label=label,
    )
    return TranscriptionResult(
        transcript=transcript,
        elapsed_s=elapsed,
        audio_s=audio_duration(wav_path),
    )
