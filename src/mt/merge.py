"""Merge the microphone and loopback transcripts onto one timeline.

The two channels are transcribed separately because mixing them would pour room
noise into the cleanest audio in the system. Merging happens *after* recognition,
on text and timestamps, so that advantage is kept.

Two behaviours matter here:

- simultaneous speech **interleaves** by timestamp rather than being concatenated,
  which is what makes the transcript read like a conversation;
- the same voice arriving on both channels — the speakerphone case — is counted
  once, keeping the loopback copy because that one is a decoded digital stream
  rather than a recording of a room.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from typing import Sequence

from .transcript import Channel, Meeting, Segment, Transcript, parse

ECHO_WINDOW_S = 1.5
ECHO_SIMILARITY = 0.85
# Short utterances are never treated as echo: two people saying "yes" at the same
# moment is crosstalk, not a speakerphone artefact, and dropping one loses speech.
MIN_ECHO_WORDS = 3
MIC_CHANNEL = "ch0"


def _distinct_labels(channels: list[Channel], mic_channel: str) -> list[Channel]:
    """Give each channel a different label.

    Two transcripts transcribed without --label both come back as "You", and a
    note whose every line is attributed to You is worse than useless.
    """
    labels = [channel.label for channel in channels]
    if len(set(labels)) == len(labels):
        return channels

    renamed: list[Channel] = []
    others = 0
    for channel in channels:
        if channel.id == mic_channel:
            renamed.append(replace(channel, label="You"))
            continue
        others += 1
        renamed.append(replace(channel, label="Remote" if others == 1 else f"Remote {others}"))
    return renamed


class MergeError(ValueError):
    """The channels could not be merged into one transcript."""


@dataclass(frozen=True)
class MergeResult:
    transcript: Transcript
    echoes_removed: int


def _is_duplicate_of(segment: Segment, other: Segment) -> bool:
    """Same speech on two different channels, close in time."""
    if segment.channel == other.channel:
        return False
    if abs(segment.start - other.start) > ECHO_WINDOW_S:
        return False
    if min(len(segment.text.split()), len(other.text.split())) < MIN_ECHO_WORDS:
        return False
    ratio = SequenceMatcher(None, segment.text.lower(), other.text.lower()).ratio()
    return ratio >= ECHO_SIMILARITY


def merge(transcripts: Sequence[Transcript], *, mic_channel: str = MIC_CHANNEL) -> MergeResult:
    """Combine per-channel transcripts into one speaker-attributed transcript."""
    if not transcripts:
        raise MergeError("nothing to merge")

    channels: list[Channel] = []
    seen: set[str] = set()
    for transcript in transcripts:
        for channel in transcript.channels:
            if channel.id in seen:
                raise MergeError(f"duplicate channel id {channel.id!r}; merge one transcript per channel")
            seen.add(channel.id)
            channels.append(channel)

    channels = _distinct_labels(channels, mic_channel)

    ordered = sorted(
        (segment for transcript in transcripts for segment in transcript.segments),
        key=lambda segment: (segment.start, segment.channel),
    )

    kept: list[Segment] = []
    echoes = 0
    for segment in ordered:
        duplicate_at = next(
            (index for index, other in enumerate(kept) if _is_duplicate_of(segment, other)),
            None,
        )
        if duplicate_at is None:
            kept.append(segment)
            continue

        duplicate = kept[duplicate_at]
        segment_is_mic = segment.channel == mic_channel
        duplicate_is_mic = duplicate.channel == mic_channel

        # The decision is by role, never by which one happened to arrive first:
        # sorting by (start, channel) would otherwise make the outcome depend on
        # a channel id.
        if segment_is_mic and not duplicate_is_mic:
            echoes += 1
            continue
        if duplicate_is_mic and not segment_is_mic:
            kept[duplicate_at] = segment
            echoes += 1
            continue

        kept.append(segment)

    segments = tuple(replace(segment, id=f"s{index + 1:04d}") for index, segment in enumerate(kept))
    duration = max((segment.end for segment in segments), default=0.0)
    if duration <= 0:
        raise MergeError("merged transcript has no positive duration")

    title = transcripts[0].meeting.title
    date = transcripts[0].meeting.date
    merged = Transcript(
        meeting=Meeting(title=title, date=date, duration_s=round(duration, 3)),
        channels=tuple(channels),
        segments=segments,
    )
    return MergeResult(transcript=parse(merged.to_dict()), echoes_removed=echoes)
