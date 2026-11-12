# Local Meeting Transcriber

Records both sides of a remote meeting on one laptop, transcribes it offline, and
writes a note: what was discussed, what was decided, and what needs doing, by
whom, by when.

No cloud. No account. No network at runtime.

**Status: early implementation.** The whole path runs end to end on macOS. The
Windows capture path is written but has never executed on Windows — see
[What is not proven](#what-is-not-proven) before you rely on it.

---

## Contents

- [What it does](#what-it-does)
- [Requirements](#requirements)
- [Setup on Windows](#setup-on-windows)
- [Setup on macOS / Linux (development)](#setup-on-macos--linux-development)
- [Running it](#running-it)
- [Commands](#commands)
- [How it works](#how-it-works)
- [Tests](#tests)
- [What is not proven](#what-is-not-proven)
- [Documentation](#documentation)

---

## What it does

```
 microphone ─┐
             ├─ two WAVs ─ whisper.cpp ─ merge ─ note ─ note.md
 loopback  ──┘   (separate)   (per channel)  (timeline)  (3B LLM)
```

The two channels are transcribed **separately and never mixed**. The loopback
channel is a decoded digital stream — no room acoustics, no echo — so keeping it
apart from your microphone gives cleaner remote audio, free speaker attribution,
and a way to detect the speakerphone case.

Every action item in the note must quote the transcript verbatim. Anything the
model reports that cannot be found in the transcript is demoted to an
**Unverified** section rather than being silently kept.

---

## Requirements

| | |
|---|---|
| OS | Windows 10/11 x64 (primary), macOS (development), Linux (untested) |
| CPU | x86-64 with AVX2. 4 cores minimum; 15 W laptops work but are slow |
| RAM | 16 GB recommended, 8 GB workable |
| Disk | ~2.5 GB for models and binaries |
| Software | Python 3.11+, ffmpeg |
| Audio | Headphones. On laptop speakers, echo detection has to clean up after you |

**Expected speed on the target hardware** (2017 i7-8650U, 15 W): roughly 25–40
minutes to process a 60-minute meeting. On an M-series Mac it is about 5× faster.
These are estimates, not measurements — see [bench/](bench/).

---

## Setup on Windows

```cmd
git clone https://github.com/abiolaks/meeting-transcriber
cd meeting-transcriber

winget install Python.Python.3.12
winget install Gyan.FFmpeg

powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
```

The script downloads the native binaries (whisper.cpp, llama.cpp) and the models
into `vendor\` and `models\`, installs the `soundcard` audio package, and prints
the exact run commands with the resolved binary paths. It is safe to re-run and
skips anything already present. Use `-SkipModels` to defer the ~2.3 GB download.

Nothing is installed system-wide; everything lives inside the repo directory.

### Check it can hear a meeting

Before anything else, with a meeting running and headphones on:

```cmd
py -3 -c "import soundcard as sc; s=sc.default_speaker(); print(repr(s.name)); print(sc.get_microphone(id=str(s.name), include_loopback=True))"
```

If this raises, capture will not work on that machine and the rest is moot. This
is the one part of the project that cannot be tested off Windows.

---

## Setup on macOS / Linux (development)

macOS is what the project was built on. There is no setup script; build whisper.cpp
and fetch llama.cpp by hand:

```bash
git clone https://github.com/ggml-org/whisper.cpp vendor/whisper.cpp
cd vendor/whisper.cpp
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j --target whisper-cli
cd ../..

mkdir -p models vendor
curl -L -o models/ggml-small.en-q5_1.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en-q5_1.bin
curl -L -o models/qwen2.5-3b-instruct-q4_k_m.gguf \
  https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf
```

For llama.cpp, take `llama-b####-bin-macos-arm64.tar.gz` from
[the releases page](https://github.com/ggml-org/llama.cpp/releases).

Capture on macOS needs ScreenCaptureKit (macOS 13+) or a virtual loopback device.
It is not implemented yet — only transcription of existing files is.

---

## Running it

Set `PYTHONPATH` once per shell:

```cmd
:: Windows
set PYTHONPATH=src
```

```bash
# macOS / Linux
export PYTHONPATH=src
```

### 1. Record a meeting (Windows)

```cmd
py -3 -m mt capture --seconds 3600 --out-dir sessions\q3-sync --levels
```

Writes `loopback.wav` and `mic.wav`. `--levels` shows a live per-channel meter so
silence is visible during the meeting, not discovered after it.

### 2. Turn it into a note

```cmd
py -3 -m mt run sessions\q3-sync\mic.wav sessions\q3-sync\loopback.wav ^
  --asr-model models\ggml-small.en-q5_1.bin ^
  --asr-binary vendor\whisper\whisper-cli.exe ^
  --model models\qwen2.5-3b-instruct-q4_k_m.gguf ^
  --binary vendor\llama\llama-cli.exe ^
  --out sessions\q3-sync\note.md
```

Prints stage timings and the number of echo duplicates removed. If any action
item could not be traced to the transcript, it says so on stderr and lists it
under **Unverified** in the note.

Add `--llm fake` to exercise the pipeline without a model — useful for checking
wiring, useless for note quality.

---

## Commands

| Command | What it does |
|---|---|
| `mt capture --seconds N --out-dir DIR [--levels]` | Record loopback + mic (Windows only) |
| `mt run MIC REMOTE --asr-model M --model G --out note.md` | Whole path: two WAVs → note |
| `mt transcribe AUDIO --model M [--out t.json]` | One WAV → transcript JSON |
| `mt merge MIC.json REMOTE.json --out merged.json` | Two transcripts → one timeline |
| `mt note TRANSCRIPT.json [--out note.md]` | Transcript → note, no audio |
| `mt eval PRED.json --gold GOLD.json` | WER and action precision/recall |

`mt transcribe` takes `--channel`/`--label` so each side can be labelled; by
default it writes `ch0`/`You`. Use `--channel ch1 --label Remote` for the loopback
side when transcribing by hand.

---

## How it works

1. **Capture** — loopback and mic to two separate WAVs (never mixed).
2. **Transcribe** — whisper.cpp per channel, word-level timestamps.
3. **Merge** — one timeline, speaker labels preserved, speakerphone echo counted
   once (the loopback copy wins).
4. **Note** — the model proposes section boundaries and extracts commitments; the
   renderer cuts the *verbatim* transcript at those boundaries, so the note is
   readable at the top and auditable at the bottom.
5. **Verify** — every action item must quote the transcript. Failures are demoted,
   not silently dropped.

Design docs: [SPEC.md](SPEC.md) for the reasoning, [DEVELOPMENT.md](DEVELOPMENT.md)
for the Mac-vs-Windows split, [docs/transcript-format.md](docs/transcript-format.md)
for the data contract.

---

## Tests

```bash
python3 -m pytest -q          # 127 tests, 2 skipped (need real audio/models)
mypy
ruff check src tests tools
```

Integration tests that need a model skip unless `MT_LLAMA_MODEL`,
`MT_WHISPER_MODEL` and `MT_WHISPER_BIN` are set.

---

## What is not proven

Read this before trusting the output.

- **Capture has never run on Windows.** WASAPI loopback is unverified. It is the
  first thing to test and the most likely to fail.
- **No real meeting has been processed.** Every result so far is synthetic speech,
  which has no accents, crosstalk or disfluencies.
- **No quality baseline exists.** There is no gold set, so "the note looks good"
  is an impression, not a measurement.
- **The model is flaky.** A 3B can fail to emit valid JSON; when that happens the
  run fails with no note rather than writing a wrong one.
- **Speaker attribution is weak.** Action items often come back owned by
  "Remote" even when you committed to them.
- **Not implemented**: `mt models fetch`, macOS capture, tray UI, installer,
  code signing.

---

## Documentation

| File | |
|---|---|
| [SPEC.md](SPEC.md) | Product spec, architecture, performance budget, phases |
| [TUNING.md](TUNING.md) | Every speed/quality knob, ranked, with a measurement protocol |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Local vs thin-agent-plus-server vs browser-only |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Develop on Mac, ship on Windows |
| [docs/windows-testing.md](docs/windows-testing.md) | Step-by-step validation on the target laptop |
| [bench/](bench/) | Hardware benchmark kit and results template |
| [.scratch/](.scratch/meeting-transcriber/spec.md) | Implementation tickets and their state |

## Licence

Not yet chosen. Do not assume permissive terms until this section changes.
