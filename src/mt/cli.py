"""Command line entry point."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from . import note as note_module
from .llm import FakeLLM, LlamaCppLLM
from .render import render
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
    return parser


def _write_atomically(path: Path, text: str) -> None:
    """Write via a temporary file so a crash cannot leave a half-written note."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command != "note":  # pragma: no cover - argparse enforces this
        raise SystemExit(f"unknown command {args.command!r}")

    try:
        transcript = load(args.transcript)
    except (TranscriptError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    llm = FakeLLM() if args.llm == "fake" else LlamaCppLLM(args.model)
    if llm.name == "fake":
        print(FAKE_WARNING, file=sys.stderr)

    started = time.monotonic()
    try:
        draft = note_module.build(transcript, llm)
    except NotImplementedError as exc:
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
