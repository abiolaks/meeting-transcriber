# Phase 0 results

Fill this in as you go. It is the go/no-go record for the whole project: if the
numbers here do not clear the gates in [../SPEC.md](../SPEC.md) §17, the answer is
a different machine or `DEPLOYMENT.md` Mode B — not more code.

Keep it honest. An optimistic number written down here gets believed later.

---

## Environment

| | |
|---|---|
| Date | |
| Laptop | |
| CPU | Intel Core i7-8650U, 4C/8T, 15 W |
| RAM | 15.9 GiB usable (16 GB) |
| OS build | |
| Power | AC, scheme: |
| Sustained clock measured | GHz (`check-power.ps1`) |

## 1. Capture — can we hear the meeting?

Run `capture-test.py` during a real call.

| Platform | Loopback works | Mic works | Channels separate | Notes |
|---|---|---|---|---|
| Zoom | | | | |
| Teams | | | | |
| Google Meet (browser) | | | | |

Headphones: ______   Speakerphone echo present: yes / no

Anything unusual (permissions, Bluetooth, device switching): ______

**Verdict:** PASS / FAIL

---

## 2. ASR speed

`whisper.cpp`, `-t 4`, word timestamps on. Audio: ______ minutes.

| Model | Run 1 (s) | Run 2 (s) | RTF | 60-min ETA | WER |
|---|---|---|---|---|---|
| `ggml-base.en-q5_1` | | | | | |
| `ggml-small.en-q5_1` | | | | | |
| `ggml-small.en` (f16) | | | | | |
| `ggml-small.en-q8_0` | | | | | |
| `ggml-medium.en-q5_0` | | | | | |

Thread sweep on the winner (4 / 6 / 8): ______

Beam size 5 vs 1 on the winner: ______ (and: did `-bs 1` introduce repetition?)

**Chosen configuration:** ______
**Reason:** ______

---

## 3. LLM speed

`llama-bench`, `-t 4`, `-p 512 -n 128`.

| Model | Prompt tok/s | Generation tok/s | Estimated note time (60 min meeting) |
|---|---|---|---|
| 1.7B Q4_K_M | | | |
| 3B Q4_K_M | | | |
| 4B Q4_K_M | | | |

Does the 3B produce schema-valid JSON on a real 1,500-token chunk? yes / no
Time for one chunk: ______ s

---

## 4. End-to-end

One real 60-minute meeting, full pipeline:

| Stage | Time |
|---|---|
| ASR (both channels) | |
| Merge / align | |
| LLM synthesis | |
| **Total, stop → note** | |

---

## 5. Verdict against the gates

| Gate | Threshold | Measured | Pass? |
|---|---|---|---|
| G1 | `small.en` 60-min file ≤ 35 min | | |
| G2 | `base.en` ≥ 3× realtime (live pane) | | |
| G3 | 3B emits valid note from 1.5k chunk < 45 s | | |
| G4 | End-to-end ≤ 55 min | | |

**Decision:** proceed to Phase 1 / change hardware / Mode B / stop

**Reasoning (two or three sentences, written now while it is still true):**

>
