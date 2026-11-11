"""Build a two-channel demo meeting for end-to-end testing on a machine without one.

Two different synthetic voices, one per channel, placed on a shared timeline with
pauses. This is *not* a substitute for a real meeting — TTS has no accents,
crosstalk or disfluencies — but it exercises multi-minute timing, merging,
sections and action extraction, which six seconds of speech does not.

    python3 tools/make_demo_audio.py
"""

from __future__ import annotations

import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

RATE = 16_000
MIC_VOICE = "Samantha"
REMOTE_VOICE = "Daniel"

# (channel, text, start_seconds)
SCRIPT: list[tuple[str, str, float]] = [
    ("r", "Thanks everyone. Let's start with the billing migration and where we actually are.", 0.0),
    ("y", "Sure. My understanding is that we are about two weeks behind. Is that right?", 7.0),
    ("r", "About two weeks, yes. The retry queue is the only thing that can still bite us.", 15.0),
    ("y", "What is the failure rate on the retries?", 23.0),
    ("r", "Roughly four percent fail on the third attempt, and then they are dropped entirely.", 27.0),
    ("r", "Nobody gets told. The customer is not charged and no invoice is raised.", 35.0),
    ("y", "That is worse than a failed payment, because it is invisible.", 42.0),
    ("r", "Exactly. That is why I would rather slip the date than ship it as it stands.", 46.0),
    ("y", "Who owns the fix?", 54.0),
    ("r", "I will fix the backoff and add a dead letter queue by Friday.", 57.0),
    ("y", "Good. Does that push the launch?", 63.0),
    ("r", "It pushes it a week, because of the soak test afterwards.", 67.0),
    ("y", "How long does the soak test need?", 73.0),
    ("r", "Five working days minimum. I do not want to find a queue problem in production.", 76.0),
    ("y", "Agreed. Let us call the launch the twentieth and freeze feature work until then.", 84.0),
    ("r", "I will update the release calendar today and tell support what changed.", 92.0),
    ("y", "Support will need a runbook for replaying a dead lettered event.", 99.0),
    ("r", "That is the part nobody has thought about. Who writes it?", 104.0),
    ("y", "Can you draft it? You know the queue better than anyone.", 110.0),
    ("r", "I can draft it, but I need sandbox access to Stripe first, and I do not have it.", 114.0),
    ("y", "I will chase that with finance today.", 121.0),
    ("r", "Then I will write the runbook once I have access, probably early next week.", 126.0),
    ("y", "What could still surprise us?", 133.0),
    ("r", "The invoice date uses server time, which is UTC, and customers complain.", 137.0),
    ("y", "Is that in scope for this launch or separate?", 144.0),
    ("r", "Separate, but it should be next. I will raise it as a ticket today.", 148.0),
    ("y", "And the migration script itself?", 155.0),
    ("r", "It has only run against the sample database. Sam will run it on a production copy.", 158.0),
    ("y", "When?", 165.0),
    ("r", "Thursday night, so we have the results on Friday. I will put it in the calendar.", 167.0),
    ("y", "Good. So the critical path is sandbox access, then the backoff fix, then the soak test.", 175.0),
    ("r", "That is right. Everything else can happen in parallel.", 183.0),
    ("y", "Let us regroup Thursday. I will send the calendar hold.", 188.0),
    ("r", "Sounds good. Thanks everyone.", 193.0),
]


def speak(text: str, voice: str, destination: Path) -> np.ndarray:
    # `say` rejects --data-format for an .aiff container; a .wav extension makes
    # it emit 16 kHz mono PCM16 directly.
    command = ["say", "-v", voice, "-o", str(destination), "--data-format=LEI16@16000", text]
    subprocess.run(command, check=True, capture_output=True)
    with wave.open(str(destination), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


def build_channel(voice: str, lines: list[tuple[str, float]], workdir: Path) -> np.ndarray:
    total = int((max(start for _, start in lines) + 6.0) * RATE)
    track = np.zeros(total, dtype=np.float32)
    for index, (text, start) in enumerate(lines):
        clip = speak(text, voice, workdir / f"{voice}-{index}.wav")
        offset = int(start * RATE)
        end = min(offset + len(clip), total)
        track[offset:end] += clip[: end - offset]
    return track


def write_wav(track: np.ndarray, path: Path) -> None:
    pcm = np.clip(track, -1.0, 1.0)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes((pcm * 32767).astype("<i2").tobytes())


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = root / "samples" / "demo"
    out.mkdir(parents=True, exist_ok=True)

    mic = [(text, start) for channel, text, start in SCRIPT if channel == "y"]
    remote = [(text, start) for channel, text, start in SCRIPT if channel == "r"]

    with tempfile.TemporaryDirectory() as directory:
        workdir = Path(directory)
        write_wav(build_channel(MIC_VOICE, mic, workdir), out / "mic.wav")
        write_wav(build_channel(REMOTE_VOICE, remote, workdir), out / "loopback.wav")

    print(f"wrote {out / 'mic.wav'} and {out / 'loopback.wav'} ({len(SCRIPT)} turns)")


if __name__ == "__main__":
    main()
