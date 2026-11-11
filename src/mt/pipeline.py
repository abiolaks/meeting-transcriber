"""The end-to-end path: audio in, note out.

Kept as two layers on purpose. `process_transcripts` takes already-recognised
channels and is fully testable anywhere; `process_wavs` adds speech recognition on
top. The split means the note pipeline can be exercised without a model, and the
Windows-only capture sits outside both.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from . import note as note_module
from .asr import TranscriptionResult, transcribe
from .merge import MergeResult, merge
from .note import LLM, NoteDraft
from .render import render
from .transcript import Transcript


@dataclass(frozen=True)
class PipelineResult:
    transcript: Transcript
    draft: NoteDraft
    markdown: str
    echoes_removed: int
    timings: dict[str, float] = field(default_factory=dict)


def process_transcripts(
    mic: Transcript, remote: Transcript, llm: LLM
) -> PipelineResult:
    """Merge two recognised channels and write the note."""
    merged: MergeResult = merge([mic, remote])
    started = time.monotonic()
    draft = note_module.build(merged.transcript, llm)
    return PipelineResult(
        transcript=merged.transcript,
        draft=draft,
        markdown=render(draft, merged.transcript),
        echoes_removed=merged.echoes_removed,
        timings={"note": round(time.monotonic() - started, 2)},
    )


def process_wavs(
    mic_wav: str | Path,
    remote_wav: str | Path,
    *,
    asr_model: str | Path,
    asr_binary: str,
    llm: LLM,
    title: str | None = None,
    threads: int | None = None,
) -> PipelineResult:
    """Recognise both channels, then produce the note."""
    timings: dict[str, float] = {}

    started = time.monotonic()
    mic = transcribe(
        mic_wav, asr_model, binary=asr_binary, threads=threads,
        channel_id="ch0", label="You", title=title,
    )
    timings["asr_mic"] = round(time.monotonic() - started, 2)

    started = time.monotonic()
    remote = transcribe(
        remote_wav, asr_model, binary=asr_binary, threads=threads,
        channel_id="ch1", label="Remote", title=title,
    )
    timings["asr_remote"] = round(time.monotonic() - started, 2)

    result = process_transcripts(mic.transcript, remote.transcript, llm)
    merged_timings = {**timings, **result.timings}
    merged_timings["asr_audio_s"] = round(mic.audio_s + remote.audio_s, 2)
    return PipelineResult(
        transcript=result.transcript,
        draft=result.draft,
        markdown=result.markdown,
        echoes_removed=result.echoes_removed,
        timings=merged_timings,
    )


def transcriptions(*results: TranscriptionResult) -> Sequence[Transcript]:
    """Convenience for tests and callers holding TranscriptionResults."""
    return [result.transcript for result in results]
