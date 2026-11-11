"""Windows audio capture: system loopback and microphone to two WAV files.

The remote participants arrive on the speaker's WASAPI loopback; the local user
arrives on the default microphone. They are recorded simultaneously as two mono
48 kHz PCM16 files, never mixed, because the loopback stream is the cleanest
audio in the meeting and keeping it separate is what makes speaker attribution
free (see docs/transcript-format.md).

`soundcard` is imported lazily, so this module is importable and testable on
every platform. Only `record()` and `available()` touch audio hardware.

The loopback stream is the decoded output, not a room recording. With
headphones that is exactly right. With laptop speakers the microphone also
hears the remote voices, and the loopback contains the local voice, so the two
files stop being cleanly separated — there is no echo cancellation here. Use
headphones for a meeting; this module cannot detect a speakerphone and warn.

A dropped or unplugged device is treated as a temporary outage: the channel
logs it, fills the elapsed gap with silence so both files stay aligned to the
wall clock, and reopens the device while the other channel keeps recording.
"""

from __future__ import annotations

import importlib
import logging
import math
import sys
import threading
import time
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

logger = logging.getLogger(__name__)

SAMPLE_RATE = 48_000
SAMPLE_WIDTH = 2
CHANNEL_COUNT = 1
BLOCK_FRAMES = 4_800  # 100 ms at 48 kHz: fast enough for a responsive meter
SILENCE_DBFS = -55.0
DBFS_FLOOR = -120.0
RECONNECT_DELAY_S = 0.05
MAX_RECONNECT_DELAY_S = 1.0

LOOPBACK = "loopback"
MIC = "mic"
CHANNEL_NAMES = (LOOPBACK, MIC)

_SILENT_FRAME = b"\x00\x00"


class CaptureError(RuntimeError):
    """Capture could not start, or no channel produced a usable recording."""


@dataclass(frozen=True)
class CaptureResult:
    """The two files and what the meters saw.

    `silent` names every channel whose peak stayed below `SILENCE_DBFS` for the
    whole capture, so the caller can warn before the user stops the meeting
    rather than discovering an empty channel during transcription.
    """

    loopback_path: Path
    mic_path: Path
    seconds: float
    peak_dbfs: dict[str, float]
    silent: tuple[str, ...] = ()


class _Recorder(Protocol):
    """The slice of soundcard's recorder this module relies on."""

    def record(self, numframes: int) -> Sequence[float]: ...

    def __enter__(self) -> _Recorder: ...

    def __exit__(self, *exc: object) -> object: ...


# --------------------------------------------------------------------- levels


def _peak_amplitude(samples: Sequence[float]) -> float:
    """Largest absolute sample in a float block, in the range soundcard uses."""
    return max((abs(float(sample)) for sample in samples), default=0.0)


def _dbfs(peak: float) -> float:
    """Peak amplitude as dBFS, floored so silence is a finite number."""
    if peak <= 0.0:
        return DBFS_FLOOR
    return max(DBFS_FLOOR, 20.0 * math.log10(peak))


def _is_silent(peak_dbfs: float) -> bool:
    """True when a channel never rose above the audible floor."""
    return peak_dbfs < SILENCE_DBFS


def _silent_channels(peaks: dict[str, float]) -> tuple[str, ...]:
    return tuple(name for name in CHANNEL_NAMES if _is_silent(peaks.get(name, DBFS_FLOOR)))


def _notify(
    on_level: Callable[[str, float], None] | None, name: str, level: float
) -> None:
    """Deliver a meter update without letting a UI bug stop the recording."""
    if on_level is None:
        return
    try:
        on_level(name, level)
    except Exception:
        logger.warning("%s: level callback failed", name, exc_info=True)


# ------------------------------------------------------------------ PCM / WAV


def _pcm16_bytes(samples: Sequence[float]) -> bytes:
    """Convert float samples in [-1, 1] to little-endian mono PCM16."""
    frames = array(
        "h",
        (
            max(-32_768, min(32_767, int(round(float(sample) * 32_767.0))))
            for sample in samples
        ),
    )
    if sys.byteorder == "big":
        frames.byteswap()
    return frames.tobytes()


def _as_mono(samples: Any) -> Sequence[float]:
    """Flatten a recorder block that may arrive as (frames, 1).

    soundcard returns a one-dimensional block for a mono recorder on current
    releases, but the shape has varied by backend; normalising here keeps a
    two-dimensional block from being written as garbage.
    """
    if getattr(samples, "ndim", 1) > 1:
        return samples.reshape(-1)
    return samples


def _write_silence(writer: _WavWriter, frames: int) -> None:
    """Write silence in bounded chunks so a long outage cannot balloon memory."""
    while frames > 0:
        chunk = min(frames, SAMPLE_RATE)
        writer.write(_SILENT_FRAME * chunk)
        frames -= chunk


class _WavWriter:
    """A streaming 48 kHz mono PCM16 WAV writer."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._closed = False
        try:
            self._handle = wave.open(str(path), "wb")
        except OSError as exc:
            raise CaptureError(f"cannot open {path} for writing: {exc}") from exc
        self._handle.setnchannels(CHANNEL_COUNT)
        self._handle.setsampwidth(SAMPLE_WIDTH)
        self._handle.setframerate(SAMPLE_RATE)

    def write(self, frames: bytes) -> None:
        if self._closed:
            raise ValueError(f"{self.path} is already closed")
        self._handle.writeframes(frames)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._handle.close()

    def __enter__(self) -> _WavWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _close_writer(writer: _WavWriter) -> None:
    try:
        writer.close()
    except Exception:
        logger.warning("%s: closing the WAV file failed", writer.path, exc_info=True)


# ---------------------------------------------------------------- capture loop


def _close_recorder(recorder: _Recorder) -> None:
    try:
        recorder.__exit__(None, None, None)
    except Exception:
        logger.debug("closing the recorder failed", exc_info=True)


def _pad_to_clock(
    writer: _WavWriter,
    written: int,
    total_frames: int,
    started: float,
    name: str,
    on_level: Callable[[str, float], None] | None,
) -> int:
    """Fill a device outage with silence so the file tracks wall-clock time.

    Without this a headset swap would shorten one channel and knock the two
    transcript timelines out of alignment for the rest of the meeting.
    """
    expected = min(total_frames, int((time.monotonic() - started) * SAMPLE_RATE))
    gap = expected - written
    if gap <= 0:
        return written
    _write_silence(writer, gap)
    _notify(on_level, name, DBFS_FLOOR)
    return written + gap


def _capture_channel(
    name: str,
    writer: _WavWriter,
    total_frames: int,
    open_recorder: Callable[[], _Recorder],
    on_level: Callable[[str, float], None] | None = None,
    stop: threading.Event | None = None,
    origin: float | None = None,
) -> float:
    """Record one device to one WAV file and return its peak dBFS.

    `origin` is the common monotonic start instant shared by both channels; any
    device-open latency after it is written as leading silence, so the two files
    share a timeline instead of starting whenever their WASAPI streams happened
    to come up. A read or reopen failure is logged and the channel continues;
    only a failure to write the file escapes, because there is nothing useful
    left to do then.
    """
    peak = DBFS_FLOOR
    written = 0
    failures = 0
    started = origin if origin is not None else time.monotonic()
    recorder: _Recorder | None = None

    try:
        while written < total_frames and not (stop is not None and stop.is_set()):
            if recorder is None:
                try:
                    recorder = open_recorder().__enter__()
                except Exception as exc:
                    failures += 1
                    logger.warning(
                        "%s: could not open recorder (attempt %d): %s", name, failures, exc
                    )
                    written = _pad_to_clock(
                        writer, written, total_frames, started, name, on_level
                    )
                    delay = min(MAX_RECONNECT_DELAY_S, RECONNECT_DELAY_S * failures)
                    if stop is not None:
                        stop.wait(delay)
                    else:
                        time.sleep(delay)
                    continue
                # The device may have taken time to open; keep the file's origin
                # shared with the other channel rather than starting late.
                written = _pad_to_clock(
                    writer, written, total_frames, started, name, on_level
                )
                if written >= total_frames:
                    continue

            want = min(BLOCK_FRAMES, total_frames - written)
            try:
                samples = _as_mono(recorder.record(want))
                if len(samples) == 0:
                    raise RuntimeError("device returned no frames")
            except Exception as exc:
                logger.warning("%s: read failed, reopening device: %s", name, exc)
                _close_recorder(recorder)
                recorder = None
                failures += 1
                written = _pad_to_clock(
                    writer, written, total_frames, started, name, on_level
                )
                delay = min(MAX_RECONNECT_DELAY_S, RECONNECT_DELAY_S * failures)
                if stop is not None:
                    stop.wait(delay)
                else:
                    time.sleep(delay)
                continue

            # A device that returns more than asked for must not overrun the file.
            block = samples[:want] if len(samples) > want else samples
            writer.write(_pcm16_bytes(block))
            written += len(block)
            failures = 0
            level = _dbfs(_peak_amplitude(block))
            peak = max(peak, level)
            _notify(on_level, name, level)
    finally:
        if recorder is not None:
            _close_recorder(recorder)

    if written < total_frames and not (stop is not None and stop.is_set()):
        # Defensive: keep the declared duration exact if the loop ever exits short.
        _write_silence(writer, total_frames - written)
    return peak


# ------------------------------------------------------------------- devices


def _load_soundcard() -> Any:
    """Import soundcard at call time so the module imports on every OS."""
    try:
        return importlib.import_module("soundcard")
    except (ImportError, OSError) as exc:
        raise CaptureError(
            "soundcard is not installed — run `py -3 -m pip install soundcard numpy`"
        ) from exc


def _resolve_device(sc: Any, name: str) -> Any:
    """Resolve only the device this channel needs.

    Keeping the two lookups independent matters during a headset swap: a
    missing microphone must not stop the loopback channel from reopening, and
    vice versa.
    """
    if name == LOOPBACK:
        try:
            speaker = sc.default_speaker()
        except Exception as exc:
            raise CaptureError(f"cannot find a default speaker: {exc}") from exc
        if speaker is None:
            raise CaptureError("no default speaker — cannot capture system audio")
        try:
            return sc.get_microphone(id=str(speaker.name), include_loopback=True)
        except Exception as exc:
            raise CaptureError(
                f"no loopback device for speaker {speaker.name!r}: {exc}"
            ) from exc

    try:
        microphone = sc.default_microphone()
    except Exception as exc:
        raise CaptureError(f"cannot find a default microphone: {exc}") from exc
    if microphone is None:
        raise CaptureError("no default microphone — cannot capture the local user")
    return microphone


def _resolve_devices(sc: Any) -> tuple[Any, Any]:
    """Return (loopback microphone, default microphone) or raise CaptureError."""
    return _resolve_device(sc, LOOPBACK), _resolve_device(sc, MIC)


def _recorder_factory(sc: Any, name: str) -> Callable[[], _Recorder]:
    """Re-resolve the default device on every open.

    A headset swap changes which device is the default, and the old device
    object may be dead. Resolving again here is what lets the channel come back
    after the user plugs the headset back in, without restarting the meeting.
    """

    def open_recorder() -> _Recorder:
        device = _resolve_device(sc, name)
        return device.recorder(
            samplerate=SAMPLE_RATE, channels=CHANNEL_COUNT, blocksize=BLOCK_FRAMES
        )

    return open_recorder


def available() -> bool:
    """True only where this recorder can actually work.

    That means Windows (WASAPI loopback), an importable soundcard, and both a
    default speaker with a matching loopback device and a default microphone.
    """
    if sys.platform != "win32":
        return False
    try:
        sc = _load_soundcard()
        _resolve_devices(sc)
    except CaptureError:
        return False
    except Exception:
        logger.debug("audio availability probe failed", exc_info=True)
        return False
    return True


# -------------------------------------------------------------------- public


def record(
    seconds: float,
    out_dir: Path,
    *,
    on_level: Callable[[str, float], None] | None = None,
) -> CaptureResult:
    """Record loopback and microphone for `seconds` into `out_dir`.

    Writes `loopback.wav` and `mic.wav` (48 kHz mono PCM16) and calls
    `on_level(name, peak_dbfs)` about every 100 ms for each channel, where name
    is `"loopback"` or `"mic"`. The callback is invoked from the two capture
    threads, so it must be thread-safe and should only update the UI. The
    channels run on separate threads; a failure on one does not abort the other.

    With laptop speakers the loopback also contains the local voice and the
    microphone also hears the remote voices. Use headphones.
    """
    if not math.isfinite(seconds) or seconds <= 0:
        raise CaptureError(f"capture seconds must be a positive number, got {seconds!r}")

    if sys.platform != "win32":
        raise CaptureError(
            "Windows audio capture is unavailable on this platform; "
            "loopback capture needs WASAPI (see DEVELOPMENT.md)"
        )

    sc = _load_soundcard()
    output = Path(out_dir)
    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CaptureError(f"cannot create output directory {output}: {exc}") from exc

    # Fail before writing files or waiting out a long silent capture. The
    # channel factories resolve again for every reopen so a headset swap can
    # recover; this first probe only rejects a machine with no usable devices.
    _resolve_devices(sc)
    total_frames = int(round(seconds * SAMPLE_RATE))
    if total_frames <= 0:
        raise CaptureError(f"capture is too short to record: {seconds!r}s")

    paths = {LOOPBACK: output / "loopback.wav", MIC: output / "mic.wav"}
    writers: dict[str, _WavWriter] = {}
    try:
        for name in CHANNEL_NAMES:
            writers[name] = _WavWriter(paths[name])
    except Exception:
        for writer in writers.values():
            _close_writer(writer)
        raise

    peaks = {name: DBFS_FLOOR for name in CHANNEL_NAMES}
    failures: dict[str, str] = {}
    stop = threading.Event()

    def run(name: str) -> None:
        try:
            peaks[name] = _capture_channel(
                name,
                writers[name],
                total_frames,
                _recorder_factory(sc, name),
                on_level,
                stop,
                origin,
            )
        except Exception as exc:
            logger.exception("%s: capture channel failed", name)
            failures[name] = str(exc)

    threads = [
        threading.Thread(target=run, args=(name,), name=f"mt-capture-{name}", daemon=True)
        for name in CHANNEL_NAMES
    ]
    origin = time.monotonic()
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        stop.set()
        for thread in threads:
            thread.join(timeout=2.0)
        raise
    finally:
        for writer in writers.values():
            _close_writer(writer)

    if len(failures) == len(CHANNEL_NAMES):
        details = "; ".join(f"{name}: {message}" for name, message in failures.items())
        raise CaptureError(f"capture failed on both channels: {details}")

    result = CaptureResult(
        loopback_path=paths[LOOPBACK],
        mic_path=paths[MIC],
        seconds=total_frames / SAMPLE_RATE,
        peak_dbfs=peaks,
        silent=_silent_channels(peaks),
    )
    for name in result.silent:
        logger.warning(
            "%s: peak stayed below %.0f dBFS for the whole capture", name, SILENCE_DBFS
        )
    return result
