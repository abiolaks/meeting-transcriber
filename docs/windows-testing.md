# Testing on the Windows laptop

Everything below runs on the target machine. Nothing here has been executed on
Windows yet — it was built and tested on macOS. Treat first contact as a test, not
a formality.

## 1. Preflight (5 minutes)

```cmd
winget install Python.Python.3.12
winget install Gyan.FFmpeg
py -3 -m pip install soundcard numpy
```

Get the binaries and models into the repo (they are gitignored, so they do not
travel with a clone):

| What | Where |
|---|---|
| `whisper-cli.exe` | whisper.cpp release, `*-bin-win-avx2-x64.zip` |
| `llama-cli.exe` | llama.cpp release, `*-bin-win-avx2-x64.zip` |
| `ggml-small.en-q5_1.bin` | <https://huggingface.co/ggerganov/whisper.cpp> |
| `ggml-base.en-q5_1.bin` | same |
| a 3B GGUF, `Q4_K_M` | any instruct model |

Then confirm Python can see the code:

```cmd
cd <repo>
set PYTHONPATH=src
py -3 -m mt --help
```

You should see `note`, `transcribe`, `merge`, `run`, `eval`.

## 2. Does it hear the meeting? (10 minutes)

This is the riskiest unknown. Run during a real call, with headphones on.

```cmd
py -3 -c "import soundcard as sc; s=sc.default_speaker(); print(repr(s.name)); print(sc.get_microphone(id=str(s.name), include_loopback=True))"
```

If that raises, stop — the loopback identifier is wrong on this machine and the
capture module needs a device-selection change before anything else works.

Then:

```cmd
py -3 -m mt capture --seconds 30 --out-dir samples\smoke
```

While it records, have someone talk in the call and speak yourself. Then play back
`samples\smoke\loopback.wav` and `samples\smoke\mic.wav`:

- **loopback** should contain the other people, and **not** you;
- **mic** should contain you, and **not** them.

If they overlap, you are on laptop speakers, not headphones. That is the
speakerphone case: still usable, but expect echo removal and a warning.

## 3. The whole path on one meeting (30–60 minutes)

Record a real meeting, then process it:

```cmd
py -3 -m mt capture --seconds 3600 --out-dir sessions\q3-sync
py -3 -m mt run sessions\q3-sync\mic.wav sessions\q3-sync\loopback.wav ^
      --asr-model models\ggml-small.en-q5_1.bin ^
      --asr-binary path\to\whisper-cli.exe ^
      --model models\qwen2.5-3b-instruct-q4_k_m.gguf ^
      --binary path\to\llama-cli.exe ^
      --out sessions\q3-sync\note.md
```

Record the printed timings in [bench/RESULTS.md](../bench/RESULTS.md). The number
that matters is **stop → note**.

What to judge, in order of importance:

1. **Nothing invented.** Every action item quotes something that was really said.
   Anything under "Unverified" should look like a model guess.
2. **Sections make sense.** A person who was in the meeting should recognise the
   headings and the order.
3. **Action items are right.** Owner, action, date. A missed item is a nuisance; a
   fabricated owner is a failure.
4. **Then speed.** 35–45 minutes for an hour-long meeting is the current estimate.

## 4. Known weak points

| Risk | What you would see |
|---|---|
| Loopback device name mismatch | `capture` raises at start, or writes a silent `loopback.wav` |
| Meeting app on a non-default device | Everything is silent, or only one side is captured — Windows defaults must match the app's device |
| Model too large for 16 GB | Swap thrash, or the run takes hours |
| 3B returns unparseable JSON | `error: ... no note was written`; retry once by hand |
| Echo on speakers | Duplicated lines, warning on stderr |
| Thermal throttling | First 10 minutes fast, then it crawls |

## 5. What "ready to ship" means

- [ ] `mt capture` produces two genuinely separate files on this laptop
- [ ] `mt run` produces a note from a real meeting, offline
- [ ] the note contains no invented action items
- [ ] stop → note is recorded in `bench/RESULTS.md`
- [ ] the person who attended the meeting says the note is usable

Until every box is ticked, treat this as a prototype that happens to run.
