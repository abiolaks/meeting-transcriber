# Development and packaging workflow

Target is a Windows laptop. Development happens on a Mac. This document says
what that split actually means so we don't discover a wall in week six.

## The short version

| Activity | Where | Why |
|---|---|---|
| Pipeline logic, chunking, prompts, note rendering | Mac | pure Python, no OS contact |
| ASR / LLM invocation and flags | Mac | whisper.cpp and llama.cpp have identical CLIs on every platform |
| Audio capture | **Windows** | WASAPI loopback exists nowhere else; macOS needs ScreenCaptureKit instead |
| Benchmarking for the target | **Windows** | an M2 number is not a i7-8650U number |
| Packaging / installer | **Windows** (or CI) | PyInstaller cannot cross-compile |
| Anything the user will actually use | **Windows** | "works on my machine" is the default failure mode |

Rule of thumb: **the Mac can prove the logic is right; only the laptop can prove
the product is right.**

## Native binaries are downloaded, not built

whisper.cpp and llama.cpp are C++ with per-platform release binaries. We do not
compile them, and we certainly do not cross-compile them from macOS.

- Windows: `*-bin-win-avx2-x64.zip` from the upstream releases.
- macOS: the corresponding arm64 build.

Their command-line interfaces are the same, which is why the orchestration layer
is portable. The only differences the code cares about are **the binary path**
and **the audio backend**. Keep both behind one module boundary.

## The one-interface rule

All OS-specific code lives behind a single interface, so the rest of the pipeline
never asks "which platform am I on":

```
capture/
  __init__.py      # get_recorder() -> Recorder
  windows.py       # WASAPI loopback + input  (the real target)
  macos.py         # ScreenCaptureKit
  linux.py         # PulseAudio/PipeWire monitor
```

`Recorder` exposes exactly: `start()`, `read_chunk()`, `stop()`, and a per-channel
level callback. Everything else — VAD, segmentation, ASR, synthesis, rendering —
is platform-agnostic and testable on the Mac.

## Packaging: not now, and not on this Mac

**Phase 0 and Phase 1 need no packaging at all.** The deliverable is a folder you
copy to the laptop and run. Packaging is a Phase 3 concern.

When we do get there:

- PyInstaller must run **on Windows** to produce a Windows executable. There is no
  cross-compile.
- The installer is small by design (models download on first run), so this is
  simpler than it sounds.
- Do it in **GitHub Actions on a `windows-latest` runner**, triggered on tag. That
  gives a reproducible build that does not depend on anyone's laptop, and it is
  how the Mac stays a development machine rather than becoming an unofficial
  build server.
- Code signing needs a real certificate. An unsigned installer on a corporate
  laptop will be blocked by SmartScreen and probably by endpoint protection.
  Budget for a certificate, or expect the recipient to click through warnings.

```
.github/workflows/
  build-windows.yml    # Phase 3: python -m pyinstaller, upload artifact
  build-macos.yml      # Phase 3: optional, secondary platform
```

## Prerequisites on the Windows laptop

Phase 0 (benchmark only) needs no Python:

- whisper.cpp `*-bin-win-avx2-x64.zip`
- llama.cpp `*-bin-win-avx2-x64.zip`
- ffmpeg on PATH (`winget install Gyan.FFmpeg`)

The capture test needs Python, because the audio plumbing is `soundcard`:

```cmd
winget install Python.Python.3.12
py -3 -m pip install soundcard numpy
```

Phase 1 will need Python 3.11+ as well. If installing Python on a corporate
machine is blocked, that is worth discovering now rather than in Phase 2 — it
would push us toward a prebuilt binary much earlier, or toward `DEPLOYMENT.md`
Mode B.

## What "done" means for Phase 1

A phase is done when it runs **on the target laptop**, not when it runs in this
repo. Specifically:

- [ ] `record → wav → transcript → note.md` completes on Windows, unattended
- [ ] Both channels are captured separately and the outputs are not mixed
- [ ] The note renders with sections, decisions and quoted action items
- [ ] Timing is recorded in `bench/RESULTS.md`
- [ ] Same command works on macOS, or is documented as Windows-only

Until then, everything on the Mac is a prototype.
