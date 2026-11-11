"""Ticket 06 seams: WAV output, levels, silence, and device-change tolerance.

Everything here runs without an audio device. The platform-dependent tests skip
on non-Windows and when `soundcard` is missing; the rest exercise the same code
the recorder runs by injecting fake devices, so a Mac can still prove the file
format, the meter maths and the reconnect path are right. Real WASAPI capture is
only provable on the target laptop (see DEVELOPMENT.md).
"""

from __future__ import annotations

import importlib.util
import struct
import sys
import time
import wave
from types import SimpleNamespace

import pytest

import mt.capture as capture
from mt.capture import (
    BLOCK_FRAMES,
    DBFS_FLOOR,
    LOOPBACK,
    MIC,
    SAMPLE_RATE,
    SILENCE_DBFS,
    CaptureError,
    CaptureResult,
    _capture_channel,
    _dbfs,
    _is_silent,
    _pad_to_clock,
    _pcm16_bytes,
    _peak_amplitude,
    _silent_channels,
    _WavWriter,
    available,
    record,
)

HAS_SOUNDCARD = importlib.util.find_spec("soundcard") is not None
WINDOWS_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="Windows audio only")
NEEDS_SOUNDCARD = pytest.mark.skipif(
    not HAS_SOUNDCARD, reason="soundcard is not installed"
)


# --------------------------------------------------------------- fake devices


class FakeRecorder:
    """A stand-in for soundcard's recorder that can fail on demand."""

    def __init__(self, blocks: list[list[float] | Exception]) -> None:
        self._blocks = list(blocks)
        self.closed = False
        self.calls = 0

    def __enter__(self) -> FakeRecorder:
        return self

    def __exit__(self, *exc: object) -> bool:
        self.closed = True
        return False

    def record(self, numframes: int) -> list[float]:
        self.calls += 1
        if not self._blocks:
            return [0.0] * numframes
        item = self._blocks.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeDevice:
    def __init__(self, block: list[float] | Exception) -> None:
        self._block = block
        self.recorders: list[FakeRecorder] = []

    def recorder(
        self, *, samplerate: int, channels: int, blocksize: int
    ) -> FakeRecorder:
        assert samplerate == SAMPLE_RATE
        assert channels == 1
        assert blocksize == BLOCK_FRAMES
        recorder = FakeRecorder([self._block])
        self.recorders.append(recorder)
        return recorder


class FakeSoundcard:
    def __init__(self, loopback_block: list[float], mic_block: list[float]) -> None:
        self.speaker = SimpleNamespace(name="Speakers (Fake)")
        self.loopback = FakeDevice(loopback_block)
        self.microphone = FakeDevice(mic_block)

    def default_speaker(self) -> SimpleNamespace:
        return self.speaker

    def default_microphone(self) -> FakeDevice:
        return self.microphone

    def get_microphone(self, *, id: str, include_loopback: bool) -> FakeDevice:
        assert id == self.speaker.name
        assert include_loopback is True
        return self.loopback


def fake_open_recorder(block: list[float] | Exception):
    device = FakeDevice(block)
    return lambda: device.recorder(
        samplerate=SAMPLE_RATE, channels=1, blocksize=BLOCK_FRAMES
    )


# ------------------------------------------------------------------ WAV / PCM


def test_pcm16_is_little_endian_and_clipped():
    assert _pcm16_bytes([0.0]) == b"\x00\x00"
    assert _pcm16_bytes([1.0]) == b"\xff\x7f"
    assert _pcm16_bytes([-1.0]) == b"\x01\x80"
    assert _pcm16_bytes([2.0, -2.0]) == b"\xff\x7f\x00\x80"
    assert _pcm16_bytes([0.5]) == struct.pack("<h", 16_384)


def test_the_wav_writer_produces_48k_mono_pcm16(tmp_path):
    path = tmp_path / "loopback.wav"
    samples = [0.0, 0.5, -0.5]

    with _WavWriter(path) as writer:
        writer.write(_pcm16_bytes(samples))

    with wave.open(str(path), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == SAMPLE_RATE
        assert handle.getnframes() == len(samples)
        assert handle.getcomptype() == "NONE"
        assert handle.readframes(len(samples)) == _pcm16_bytes(samples)


def test_a_writer_cannot_be_used_after_close(tmp_path):
    writer = _WavWriter(tmp_path / "mic.wav")
    writer.close()

    with pytest.raises(ValueError, match="closed"):
        writer.write(b"\x00\x00")


# --------------------------------------------------------------------- levels


def test_peak_amplitude_uses_the_largest_absolute_sample():
    assert _peak_amplitude([0.1, -0.8, 0.3]) == pytest.approx(0.8)
    assert _peak_amplitude([]) == 0.0


def test_dbfs_of_full_scale_is_zero_and_half_scale_is_minus_six():
    assert _dbfs(1.0) == pytest.approx(0.0)
    assert _dbfs(0.5) == pytest.approx(-6.0206, abs=1e-3)
    assert _dbfs(0.0) == DBFS_FLOOR
    assert _dbfs(-0.5) == DBFS_FLOOR


def test_silence_is_below_minus_55_dbfs():
    assert _is_silent(_dbfs(0.0))
    assert _is_silent(_dbfs(0.001))  # about -60 dBFS
    assert not _is_silent(_dbfs(0.01))  # about -40 dBFS
    assert not _is_silent(SILENCE_DBFS)
    assert _is_silent(SILENCE_DBFS - 0.001)


def test_silent_channels_names_each_quiet_channel():
    assert _silent_channels({LOOPBACK: -70.0, MIC: -20.0}) == (LOOPBACK,)
    assert _silent_channels({LOOPBACK: -20.0, MIC: -20.0}) == ()
    assert _silent_channels({}) == (LOOPBACK, MIC)


# --------------------------------------------------------------- capture loop


def test_a_failed_read_reopens_the_device_and_finishes_the_file(tmp_path):
    path = tmp_path / "loopback.wav"
    opened: list[FakeRecorder] = []

    def factory() -> FakeRecorder:
        blocks: list[list[float] | Exception]
        if not opened:
            blocks = [[0.5] * BLOCK_FRAMES, RuntimeError("headset unplugged")]
        else:
            blocks = [[0.25] * BLOCK_FRAMES for _ in range(10)]
        recorder = FakeRecorder(blocks)
        opened.append(recorder)
        return recorder

    total = 4 * BLOCK_FRAMES
    levels: list[tuple[str, float]] = []
    with _WavWriter(path) as writer:
        peak = _capture_channel(
            LOOPBACK,
            writer,
            total,
            factory,
            on_level=lambda name, level: levels.append((name, level)),
        )

    assert peak == pytest.approx(_dbfs(0.5))
    assert len(opened) == 2
    assert opened[0].closed
    assert {name for name, _ in levels} == {LOOPBACK}
    assert max(level for _, level in levels) == pytest.approx(_dbfs(0.5))
    assert len(levels) >= 4
    with wave.open(str(path), "rb") as handle:
        assert handle.getnframes() == total


def test_a_gap_is_filled_with_silence_so_the_file_tracks_the_clock(tmp_path):
    path = tmp_path / "mic.wav"
    levels: list[tuple[str, float]] = []
    total = 2 * SAMPLE_RATE

    with _WavWriter(path) as writer:
        written = _pad_to_clock(
            writer,
            0,
            total,
            time.monotonic() - 0.5,
            MIC,
            lambda name, level: levels.append((name, level)),
        )

    assert 0.4 * SAMPLE_RATE <= written <= 0.6 * SAMPLE_RATE
    assert levels == [(MIC, DBFS_FLOOR)]
    with wave.open(str(path), "rb") as handle:
        assert handle.getnframes() == written


def test_a_failing_level_callback_does_not_stop_the_capture(tmp_path):
    path = tmp_path / "mic.wav"

    def explode(name: str, level: float) -> None:
        raise RuntimeError("UI bug")

    with _WavWriter(path) as writer:
        peak = _capture_channel(
            MIC, writer, BLOCK_FRAMES, fake_open_recorder([0.25] * BLOCK_FRAMES),
            on_level=explode,
        )

    assert peak == pytest.approx(_dbfs(0.25))
    with wave.open(str(path), "rb") as handle:
        assert handle.getnframes() == BLOCK_FRAMES


def test_a_two_dimensional_block_is_flattened(tmp_path):
    """soundcard backends have returned both (n,) and (n, 1) for mono."""
    path = tmp_path / "mic.wav"
    flat = [0.5] * BLOCK_FRAMES

    class TwoDimensionalBlock:
        ndim = 2

        def __len__(self) -> int:
            return len(flat)

        def reshape(self, *shape: int) -> list[float]:
            return flat

    class TwoDimensionalRecorder:
        def __enter__(self) -> TwoDimensionalRecorder:
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def record(self, numframes: int) -> TwoDimensionalBlock:
            return TwoDimensionalBlock()

    with _WavWriter(path) as writer:
        peak = _capture_channel(
            MIC, writer, BLOCK_FRAMES, TwoDimensionalRecorder
        )

    assert peak == pytest.approx(_dbfs(0.5))
    with wave.open(str(path), "rb") as handle:
        assert handle.getnframes() == BLOCK_FRAMES


def test_silent_input_reports_the_dbfs_floor(tmp_path):
    path = tmp_path / "mic.wav"

    with _WavWriter(path) as writer:
        peak = _capture_channel(
            MIC, writer, BLOCK_FRAMES, fake_open_recorder([0.0] * BLOCK_FRAMES)
        )

    assert peak == DBFS_FLOOR
    assert _is_silent(peak)


# --------------------------------------------------------------- record / API


def test_record_writes_two_separate_files_and_reports_both_channels(
    tmp_path, monkeypatch
):
    fake_sc = FakeSoundcard([0.5] * BLOCK_FRAMES, [0.25] * BLOCK_FRAMES)
    monkeypatch.setattr(capture, "_load_soundcard", lambda: fake_sc)
    monkeypatch.setattr(
        capture, "sys", SimpleNamespace(platform="win32", byteorder=sys.byteorder)
    )
    levels: list[tuple[str, float]] = []

    result = record(0.5, tmp_path, on_level=lambda name, level: levels.append((name, level)))

    assert isinstance(result, CaptureResult)
    assert result.loopback_path == tmp_path / "loopback.wav"
    assert result.mic_path == tmp_path / "mic.wav"
    assert result.seconds == pytest.approx(0.5)
    assert set(result.peak_dbfs) == {LOOPBACK, MIC}
    assert result.peak_dbfs[LOOPBACK] == pytest.approx(_dbfs(0.5))
    assert result.peak_dbfs[MIC] == pytest.approx(_dbfs(0.25))
    assert result.silent == ()
    assert {name for name, _ in levels} == {LOOPBACK, MIC}
    for path in (result.loopback_path, result.mic_path):
        with wave.open(str(path), "rb") as handle:
            assert handle.getnchannels() == 1
            assert handle.getsampwidth() == 2
            assert handle.getframerate() == SAMPLE_RATE
            assert handle.getnframes() == SAMPLE_RATE // 2


def test_record_names_a_silent_channel_in_the_result(tmp_path, monkeypatch):
    fake_sc = FakeSoundcard([0.5] * BLOCK_FRAMES, [0.0] * BLOCK_FRAMES)
    monkeypatch.setattr(capture, "_load_soundcard", lambda: fake_sc)
    monkeypatch.setattr(
        capture, "sys", SimpleNamespace(platform="win32", byteorder=sys.byteorder)
    )

    result = record(0.5, tmp_path)

    assert result.silent == (MIC,)
    assert result.peak_dbfs[MIC] == DBFS_FLOOR


def test_one_broken_channel_does_not_abort_the_other(tmp_path, monkeypatch):
    class FailingMicrophone:
        def recorder(self, **kwargs):
            return FakeRecorder([RuntimeError("microphone gone")] * 10)

    class OneSidedSoundcard:
        def __init__(self) -> None:
            self.speaker = SimpleNamespace(name="Speakers (Fake)")

        def default_speaker(self) -> SimpleNamespace:
            return self.speaker

        def default_microphone(self) -> FailingMicrophone:
            return FailingMicrophone()

        def get_microphone(self, *, id: str, include_loopback: bool) -> FakeDevice:
            return FakeDevice([0.5] * BLOCK_FRAMES)

    monkeypatch.setattr(capture, "_load_soundcard", OneSidedSoundcard)
    monkeypatch.setattr(
        capture, "sys", SimpleNamespace(platform="win32", byteorder=sys.byteorder)
    )

    result = record(0.2, tmp_path)

    assert result.peak_dbfs[LOOPBACK] == pytest.approx(_dbfs(0.5))
    assert result.peak_dbfs[MIC] == DBFS_FLOOR
    assert result.silent == (MIC,)
    for path in (result.loopback_path, result.mic_path):
        with wave.open(str(path), "rb") as handle:
            assert handle.getnframes() == SAMPLE_RATE // 5


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf")])
def test_record_rejects_an_impossible_duration(tmp_path, seconds):
    with pytest.raises(CaptureError, match="positive"):
        record(seconds, tmp_path)


@pytest.mark.skipif(sys.platform == "win32", reason="asserts the non-Windows branch")
def test_record_says_capture_needs_windows(tmp_path):
    with pytest.raises(CaptureError, match="Windows"):
        record(1.0, tmp_path)


@pytest.mark.skipif(sys.platform == "win32", reason="asserts the non-Windows branch")
def test_available_is_false_off_windows():
    assert available() is False


@WINDOWS_ONLY
@NEEDS_SOUNDCARD
def test_available_returns_a_bool_on_windows():
    assert isinstance(available(), bool)
