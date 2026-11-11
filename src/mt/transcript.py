"""The transcript contract.

One document type, shared by every stage: ASR produces it, the two-channel merge
combines it, the note generator consumes it. It is validated on the way in,
because a schema error that slips through here surfaces much later as a note that
quietly misses the middle of a meeting.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_VERSION = 1


class TranscriptError(ValueError):
    """A transcript document violated the schema."""


@dataclass(frozen=True)
class Word:
    w: str
    start: float
    end: float


@dataclass(frozen=True)
class Segment:
    id: str
    start: float
    end: float
    channel: str
    text: str
    words: tuple[Word, ...] = ()


@dataclass(frozen=True)
class Channel:
    id: str
    label: str


@dataclass(frozen=True)
class Meeting:
    title: str
    date: str
    duration_s: float


@dataclass(frozen=True)
class Transcript:
    meeting: Meeting
    channels: tuple[Channel, ...]
    segments: tuple[Segment, ...]

    def to_dict(self) -> dict[str, Any]:
        """The document form, for writing back to disk."""
        return {
            "version": SUPPORTED_VERSION,
            "meeting": {
                "title": self.meeting.title,
                "date": self.meeting.date,
                "duration_s": self.meeting.duration_s,
            },
            "channels": [{"id": c.id, "label": c.label} for c in self.channels],
            "segments": [
                {
                    "id": s.id,
                    "start": s.start,
                    "end": s.end,
                    "channel": s.channel,
                    "text": s.text,
                    "words": [
                        {"w": w.w, "start": w.start, "end": w.end} for w in s.words
                    ],
                }
                for s in self.segments
            ],
        }

    def label_for(self, channel_id: str) -> str:
        for channel in self.channels:
            if channel.id == channel_id:
                return channel.label
        raise TranscriptError(f"unknown channel {channel_id!r}")


# --------------------------------------------------------------------- helpers


def _field(obj: Any, key: str, where: str) -> Any:
    if not isinstance(obj, dict):
        raise TranscriptError(f"{where}: expected an object, got {type(obj).__name__}")
    if key not in obj:
        raise TranscriptError(f"{where}: missing required field {key!r}")
    return obj[key]


def _string(obj: Any, key: str, where: str) -> str:
    value = _field(obj, key, where)
    if not isinstance(value, str) or not value.strip():
        raise TranscriptError(f"{where}.{key}: expected a non-empty string")
    return value


def _number(obj: Any, key: str, where: str) -> float:
    value = _field(obj, key, where)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TranscriptError(
            f"{where}.{key}: expected a number, got {type(value).__name__}"
        )
    return float(value)


def _list(obj: Any, key: str, where: str) -> list[Any]:
    value = _field(obj, key, where)
    if not isinstance(value, list) or not value:
        raise TranscriptError(f"{where}.{key}: expected a non-empty list")
    return value


# ---------------------------------------------------------------------- parsing


def _parse_meeting(doc: dict[str, Any]) -> Meeting:
    raw = _field(doc, "meeting", "document")
    duration = _number(raw, "duration_s", "meeting")
    if duration <= 0:
        raise TranscriptError("meeting.duration_s: must be greater than zero")
    return Meeting(
        title=_string(raw, "title", "meeting"),
        date=_string(raw, "date", "meeting"),
        duration_s=duration,
    )


def _parse_channels(doc: dict[str, Any]) -> tuple[Channel, ...]:
    channels: list[Channel] = []
    seen: set[str] = set()
    for index, raw in enumerate(_list(doc, "channels", "document")):
        where = f"channels[{index}]"
        channel_id = _string(raw, "id", where)
        label = _string(raw, "label", where)
        if channel_id in seen:
            raise TranscriptError(f"{where}.id: duplicate channel id {channel_id!r}")
        seen.add(channel_id)
        channels.append(Channel(id=channel_id, label=label))
    return tuple(channels)


def _parse_words(raw_segment: dict[str, Any], where: str, start: float, end: float) -> tuple[Word, ...]:
    raw_words = raw_segment.get("words", [])
    if not isinstance(raw_words, list):
        raise TranscriptError(f"{where}.words: expected a list")

    words: list[Word] = []
    for index, raw in enumerate(raw_words):
        word_where = f"{where}.words[{index}]"
        word_start = _number(raw, "start", word_where)
        word_end = _number(raw, "end", word_where)
        if word_start < start - 1e-6 or word_end > end + 1e-6:
            raise TranscriptError(
                f"{where}.words[{index}]: word ends at {word_end}, outside segment "
                f"[{start}, {end}]"
            )
        words.append(Word(w=_string(raw, "w", word_where), start=word_start, end=word_end))
    return tuple(words)


def _parse_segments(doc: dict[str, Any], channel_ids: set[str]) -> tuple[Segment, ...]:
    segments: list[Segment] = []
    for index, raw in enumerate(_list(doc, "segments", "document")):
        where = f"segments[{index}]"
        start = _number(raw, "start", where)
        end = _number(raw, "end", where)
        if end <= start:
            raise TranscriptError(f"{where}: end ({end}) must be after start ({start})")

        channel = _string(raw, "channel", where)
        if channel not in channel_ids:
            raise TranscriptError(f"{where}.channel: unknown channel {channel!r}")

        segments.append(
            Segment(
                id=_string(raw, "id", where),
                start=start,
                end=end,
                channel=channel,
                text=_string(raw, "text", where),
                words=_parse_words(raw, where, start, end),
            )
        )

    for index in range(1, len(segments)):
        if segments[index].start < segments[index - 1].start:
            raise TranscriptError(
                "segments: not in time order "
                f"(segments[{index}] starts at {segments[index].start}, "
                f"before segments[{index - 1}] at {segments[index - 1].start})"
            )
    return tuple(segments)


def parse(doc: Any) -> Transcript:
    """Validate a transcript document and return the typed form."""
    if not isinstance(doc, dict):
        raise TranscriptError(f"document: expected an object, got {type(doc).__name__}")

    version = _field(doc, "version", "document")
    if version != SUPPORTED_VERSION:
        raise TranscriptError(
            f"document.version: unsupported version {version!r}, expected {SUPPORTED_VERSION}"
        )

    channels = _parse_channels(doc)
    return Transcript(
        meeting=_parse_meeting(doc),
        channels=channels,
        segments=_parse_segments(doc, {c.id for c in channels}),
    )


def load(path: str | Path) -> Transcript:
    """Read and validate a transcript JSON file."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TranscriptError(f"{path}: not valid JSON ({exc.msg} at line {exc.lineno})") from exc
    return parse(doc)
