# Phase 0 benchmark kit

Purpose: replace the estimates in `SPEC.md` §4 with real numbers from the actual
**i7-8650U** machine, in about an hour, before any product code is written.

Everything here is throwaway. It runs on Windows only and touches nothing else on
the machine.

## What you need

- The target Windows laptop, **plugged in**, on the "Balanced" or "Best
  performance" power plan. Battery mode halves the numbers and lies to us.
- ~7 GB free disk.
- `ffmpeg` + `ffprobe` on PATH (from winget: `winget install Gyan.FFmpeg`).
- One **real meeting recording**, 20–40 minutes, ideally from Teams or Zoom,
  containing accents, crosstalk and at least two speakers. Synthetic audio or a
  podcast gives numbers that are too good.
  Zoom: *Record → Record on this computer*. Teams: *Start recording*.
  A phone recording of the room also works — it is closer to worst case.

## 1. Assemble the tools

Create this layout:

```
bench/
  tools/
    whisper-cli.exe      (or main.exe)
    llama-bench.exe
  models/
    ggml-base.bin
    ggml-small.bin
    ggml-medium.bin
    ggml-large-v3-turbo.bin
    <one>.gguf
  sample.wav
```

Downloads:

| Item | Where |
|---|---|
| whisper.cpp Windows x64 build | <https://github.com/ggml-org/whisper.cpp/releases> — asset `whisper-bin-x64.zip` |
| whisper models | <https://huggingface.co/ggerganov/whisper.cpp/tree/main> — `ggml-base.bin`, `ggml-small.bin`, `ggml-medium.bin`, `ggml-large-v3-turbo.bin` |
| llama.cpp Windows AVX2 build | <https://github.com/ggml-org/llama.cpp/releases> — asset `llama-b####-bin-win-avx2-x64.zip` (`llama-bench.exe` is inside) |
| A 3B GGUF | any Q4_K_M 3B, e.g. `Llama-3.2-3B-Instruct` Q4_K_M |
| A 4B GGUF | any Q4_K_M 4B, e.g. `Qwen3-4B` Q4_K_M |

Release asset names change between builds; if a name does not match, take the
closest `win-avx2-x64` zip from the latest release and check that
`whisper-cli.exe` / `llama-bench.exe` exist inside it.

You do **not** need every model to start. `base` + `small` + one GGUF answers 80%
of the question. Add `medium` and `turbo` afterwards if you want the full picture.

## 2. Make the test audio

```cmd
ffmpeg -i "meeting.m4a" -ar 16000 -ac 1 -c:a pcm_s16le sample.wav
```

Mono, 16 kHz — the same format the product will feed the model, so the numbers
transfer.

## 3. Run it

```powershell
cd bench
powershell -ExecutionPolicy Bypass -File .\bench.ps1 -Wav .\sample.wav
```

The script runs every model it finds, twice:

- **Run 1** is cold — CPU still boosting.
- **Run 2** is the number that matters — throttled, sustained.

It prints a table and writes `bench-results.txt`. Send that file back.

`-Threads 4` is the default. If you want to know whether hyperthreading helps,
re-run with `-Threads 8`.

### Measure it the way the product will run it

Word timestamps are not free — they cost roughly 10–20% on top of a plain
transcription. A benchmark without them will understate the real cost and make
the spec's time budget look better than it is. Run it twice:

```cmd
:: plain, for a like-for-like comparison against public numbers
powershell -ExecutionPolicy Bypass -File .\bench.ps1 -Wav .\sample.wav

:: what the product will actually do
powershell -ExecutionPolicy Bypass -File .\bench.ps1 -Wav .\sample.wav -ExtraArgs "-ml 1 -sow"
```

Check `whisper-cli.exe --help` first — the word-timestamp flags have moved between
releases. If `-ml 1 -sow` is rejected, use whatever that build calls word-level
output. **The second number is the one that goes into the plan.**

## 4. Read the result against the gates

From `SPEC.md` §17:

| Gate | Pass condition | If it fails |
|---|---|---|
| G1 | `small` clears a 60-min file in ≤ 35 min | Product not viable on this laptop |
| G2 | `base` ≥ 3× realtime (live pane) | No live transcript; record-then-process only |
| G3 | 3B emits a valid note from a 1.5k-token chunk in < 45 s | Drop to 1.7B, or template-fill instead of generate |
| G4 | End-to-end 60-min meeting ≤ 55 min | Renegotiate A3 to "overnight", or change hardware |

A useful rule of thumb while reading: **RTF** is the ratio of processing time to
audio time. RTF 0.5 means a 60-minute meeting takes 30 minutes. Lower is better;
anything above 1.0 is slower than realtime.

## 5. Capture test (do this first — 15 minutes, no models needed)

Speed is worth nothing if we cannot hear the meeting. This test needs no downloads
beyond Python packages, so run it before the benchmark:

```cmd
py -3 -m pip install soundcard numpy
py -3 capture-test.py --list
py -3 capture-test.py --seconds 30
```

While it records, play any video with speech (that should land in `loopback.wav`)
and count to ten out loud (that should land in `mic.wav`).

Pass conditions:

1. Both files contain audio, and neither is silent.
2. **They are separate** — `loopback.wav` must not contain your voice, and
   `mic.wav` must not contain the other people. This is the whole reason the
   architecture uses two channels.
3. With headphones, repeat during a real Zoom / Teams / Meet call. Record which
   of the three needed anything unusual — Meet in a browser is usually fine,
   Bluetooth headsets are the worst case and often expose no loopback at all.

If `mic.wav` turns out to contain the remote participants, you were on
speakerphone and echo cancellation was off. That makes SPEC §6-C3 a required
feature rather than a nicety.

Record the outcome in [RESULTS.md](RESULTS.md).

## 6. Record the results

[RESULTS.md](RESULTS.md) is the go/no-go record. Fill it in as you measure, and
write the decision down while the numbers are fresh. If the gates in SPEC §17 are
not met, the answer is different hardware or `DEPLOYMENT.md` Mode B — not more
tuning.
