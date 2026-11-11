"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from . import note as note_module
from .asr import ASRError, transcribe
from .llama_cpp import LlamaCppLLM
from . import capture, evaluate, pipeline
from .merge import MergeError, merge
from .llm import FakeLLM
from .render import render
from .note import NoteError
from .transcript import TranscriptError, load

FAKE_WARNING = (
    "warning: --llm fake produces placeholder content, not summaries. "
    "It exercises the pipeline; it does not write a note."
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mt", description="Offline meeting notes")
    sub = parser.add_subparsers(dest="command", required=True)

    note = sub.add_parser("note", help="generate a note from a transcript")
    note.add_argument("transcript", help="path to a transcript JSON file")
    note.add_argument("--out", default="note.md", help="output markdown path")
    note.add_argument(
        "--llm", choices=("fake", "llama"), default="fake",
        help="which model adapter to use (default: fake)",
    )
    note.add_argument("--model", default=None, help="path to a GGUF model for --llm llama")
    note.add_argument("--binary", default="llama-cli", help="path to the llama.cpp binary")

    tr = sub.add_parser("transcribe", help="transcribe a WAV file to transcript JSON")
    tr.add_argument("audio", help="path to a 16 kHz mono WAV file")
    tr.add_argument("--model", required=True, help="path to a whisper.cpp model")
    tr.add_argument("--binary", default="whisper-cli", help="path to whisper-cli")
    tr.add_argument("--out", default=None, help="output JSON path (default: <audio>.json)")
    tr.add_argument("--threads", type=int, default=None, help="default: cores - 1")
    tr.add_argument("--channel", default="ch0", help="channel id written to the transcript")
    tr.add_argument("--label", default="You", help="speaker label for this channel")

    mg = sub.add_parser("merge", help="merge per-channel transcripts onto one timeline")
    mg.add_argument("transcripts", nargs="+", help="one transcript JSON per channel")
    mg.add_argument("--out", required=True, help="output JSON path")
    mg.add_argument("--mic-channel", default="ch0",
                    help="channel id carrying your microphone; its echo copies are dropped")

    run = sub.add_parser("run", help="two channel WAVs in, note.md out")
    run.add_argument("mic", help="your microphone recording")
    run.add_argument("remote", help="the meeting (loopback) recording")
    run.add_argument("--asr-model", required=True, help="whisper.cpp model")
    run.add_argument("--asr-binary", default="whisper-cli")
    run.add_argument("--model", required=True, help="GGUF model for the note")
    run.add_argument("--binary", default="llama-cli")
    run.add_argument("--threads", type=int, default=None)
    run.add_argument("--out", default="note.md")
    run.add_argument("--llm", choices=("llama", "fake"), default="llama")

    cap = sub.add_parser("capture", help="record loopback and mic (Windows)")
    cap.add_argument("--seconds", type=float, required=True)
    cap.add_argument("--out-dir", default="sessions/capture")
    cap.add_argument("--levels", action="store_true", help="print live levels")

    ev = sub.add_parser("eval", help="score a transcript or note against a gold set")
    ev.add_argument("transcript", help="predicted transcript JSON")
    ev.add_argument("--gold", required=True, help="gold transcript JSON")
    ev.add_argument("--pred-items", default=None, help="JSON list of predicted action items")
    ev.add_argument("--gold-items", default=None, help="JSON list of expected action items")
    return parser


def _write_transcript(path: Path, transcript) -> None:
    _write_atomically(path, json.dumps(transcript.to_dict(), indent=2) + "\n")


def _write_atomically(path: Path, text: str) -> None:
    """Write via a temporary file so a crash cannot leave a half-written note."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _transcribe(args: argparse.Namespace) -> int:
    try:
        result = transcribe(
            args.audio, args.model, binary=args.binary, threads=args.threads,
            channel_id=args.channel, label=args.label,
        )
    except ASRError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out = Path(args.out) if args.out else Path(args.audio).with_suffix(".json")
    _write_transcript(out, result.transcript)

    print(
        f"{result.transcript.meeting.title}: {len(result.transcript.segments)} segments, "
        f"{result.audio_s:.1f}s audio in {result.elapsed_s:.1f}s "
        f"(rtf {result.rtf:.2f}) -> {out}"
    )
    return 0


def _merge(args: argparse.Namespace) -> int:
    try:
        transcripts = [load(path) for path in args.transcripts]
        result = merge(transcripts, mic_channel=args.mic_channel)
    except (MergeError, TranscriptError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out = Path(args.out)
    _write_transcript(out, result.transcript)
    print(
        f"merged {len(transcripts)} channels: {len(result.transcript.segments)} segments, "
        f"{result.echoes_removed} echoes removed -> {out}"
    )
    if result.echoes_removed:
        print(
            "warning: the same speech arrived on both channels — you were probably on "
            "speakers rather than headphones. The cleaner copy was kept.",
            file=sys.stderr,
        )
    return 0


def _capture(args: argparse.Namespace) -> int:
    if not capture.available():
        print(
            "error: capture is unavailable — needs Windows, the soundcard package, "
            "and an audio output device",
            file=sys.stderr,
        )
        return 2

    callback = None
    if args.levels:
        def callback(name: str, dbfs: float) -> None:  # noqa: E306
            bar = "#" * max(0, int((dbfs + 60) / 2))
            print(f"  {name:<8} {dbfs:6.1f} dBFS {bar}", end="\r")

    print(f"recording {args.seconds:.0f}s with headphones on...", file=sys.stderr)
    try:
        result = capture.record(args.seconds, Path(args.out_dir), on_level=callback)
    except capture.CaptureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"captured {result.seconds:.1f}s -> {result.loopback_path}, {result.mic_path}"
    )
    for name, dbfs in result.peak_dbfs.items():
        print(f"  {name:<8} peak {dbfs:6.1f} dBFS")
    if result.silent:
        print(
            f"warning: {', '.join(result.silent)} stayed silent — check that the "
            "meeting audio is playing and the right default device is selected",
            file=sys.stderr,
        )
    return 0


def _run(args: argparse.Namespace) -> int:
    llm = FakeLLM() if args.llm == "fake" else LlamaCppLLM(args.model, binary=args.binary)
    try:
        result = pipeline.process_wavs(
            args.mic, args.remote,
            asr_model=args.asr_model, asr_binary=args.asr_binary,
            llm=llm, threads=args.threads,
        )
    except (ASRError, MergeError, NoteError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out = Path(args.out)
    _write_atomically(out, result.markdown)
    timings = ", ".join(f"{k} {v}s" for k, v in result.timings.items())
    print(
        f"{result.transcript.meeting.title}: {len(result.draft.sections)} sections, "
        f"{len(result.draft.actions)} actions, {result.echoes_removed} echoes -> {out}"
    )
    print(f"timings: {timings}")
    if result.draft.unverified:
        print(
            f"warning: {len(result.draft.unverified)} action items could not be traced "
            "to the transcript and are listed as Unverified",
            file=sys.stderr,
        )
    return 0


def _text(transcript) -> str:
    return " ".join(segment.text for segment in transcript.segments)


def _evaluate(args: argparse.Namespace) -> int:
    try:
        predicted = load(args.transcript)
        gold = load(args.gold)
    except (TranscriptError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    channels = {c.id: c.label for c in gold.channels}
    comparisons = {"all": (_text(gold), _text(predicted))}
    for channel_id, label in channels.items():
        reference = " ".join(s.text for s in gold.segments if s.channel == channel_id)
        if reference:
            hypothesis = " ".join(s.text for s in predicted.segments if s.channel == channel_id)
            comparisons[label] = (reference, hypothesis)

    scores = None
    if args.pred_items and args.gold_items:
        predicted_items = json.loads(Path(args.pred_items).read_text(encoding="utf-8"))
        gold_items = json.loads(Path(args.gold_items).read_text(encoding="utf-8"))
        scores = evaluate.score_actions(predicted_items, gold_items)

    print(evaluate.report(comparisons, scores))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "transcribe":
        return _transcribe(args)

    if args.command == "merge":
        return _merge(args)

    if args.command == "run":
        return _run(args)

    if args.command == "capture":
        return _capture(args)

    if args.command == "eval":
        return _evaluate(args)

    if args.command != "note":  # pragma: no cover - argparse enforces this
        raise SystemExit(f"unknown command {args.command!r}")

    try:
        transcript = load(args.transcript)
    except (TranscriptError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    llm = FakeLLM() if args.llm == "fake" else LlamaCppLLM(
        args.model, binary=args.binary,
    )
    if llm.name == "fake":
        print(FAKE_WARNING, file=sys.stderr)

    started = time.monotonic()
    try:
        draft = note_module.build(transcript, llm)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except note_module.NoteError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4
    build_seconds = time.monotonic() - started

    markdown = render(draft, transcript)
    out = Path(args.out)
    _write_atomically(out, markdown)

    print(
        f"{transcript.meeting.title}: {len(draft.sections)} sections, "
        f"{len(draft.actions)} action items, {len(draft.decisions)} decisions "
        f"-> {out} (draft {build_seconds:.2f}s, llm={llm.name})"
    )
    return 0
