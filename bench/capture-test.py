#!/usr/bin/env python3
"""
Capture smoke test: record the meeting channel and the mic channel separately.

This answers the question the benchmark cannot: can we actually HEAR a Zoom /
Teams / Meet call from inside a normal user process, with the two sources kept
apart? If this fails, no amount of ASR speed matters.

It records two WAVs simultaneously:
    loopback.wav  - what the speakers are playing (the remote participants)
    mic.wav       - your microphone (you)

Both at 48 kHz mono; convert to 16 kHz for whisper with ffmpeg afterwards.

Setup (one time):
    py -3 -m pip install soundcard numpy

Run:
    py -3 capture-test.py --list                 # show devices, then exit
    py -3 capture-test.py --seconds 30           # record 30 s of both

While it records:
    1. Play any video with people talking -> that should appear in loopback.
    2. Count out loud to ten        -> that should appear in mic.
    3. Then check the two WAVs are separate: loopback should NOT contain you.

NOTE: written but not run on Windows by its author. If a device lookup fails,
paste the error - the fix is usually a different device name in --loopback.
"""

import argparse
import sys
import time
import wave
import threading

import numpy as np

RATE = 48000          # record at 48k and downsample later; 16k is not always
BLOCK = RATE // 10    # offered by WASAPI shared mode
WARN_DB = -55.0       # below this, treat the channel as effectively silent


def list_devices():
    import soundcard as sc
    print("Speakers:")
    for s in sc.all_speakers():
        print(f"  - {s.name}")
    print("\nMicrophones:")
    for m in sc.all_microphones(include_loopback=False):
        print(f"  - {m.name}")
    print("\nLoopback devices (what the speakers are playing):")
    for m in sc.all_microphones(include_loopback=True):
        print(f"  - {m.name}")


def resolve(loopback_name):
    import soundcard as sc

    if loopback_name:
        # Accept either a loopback device name or a speaker name.
        for m in sc.all_microphones(include_loopback=True):
            if loopback_name.lower() in m.name.lower():
                return m
        for s in sc.all_speakers():
            if loopback_name.lower() in s.name.lower():
                return sc.get_microphone(id=str(s.name), include_loopback=True)
        raise SystemExit(f"No loopback device matching {loopback_name!r}. Try --list.")

    spk = sc.default_speaker()
    if spk is None:
        raise SystemExit("No default speaker. Pass --loopback explicitly.")
    return sc.get_microphone(id=str(spk.name), include_loopback=True)


def record(device, path, seconds, label, stats, stop_event):
    chunks = []
    t0 = time.time()
    try:
        with device.recorder(samplerate=RATE, channels=1) as rec:
            while time.time() - t0 < seconds and not stop_event.is_set():
                data = rec.record(numframes=BLOCK)
                if data is None or len(data) == 0:
                    continue
                chunks.append(data)
                rms = float(np.sqrt(np.mean(np.square(data))))
                if rms > 0:
                    stats[label].append(20.0 * np.log10(rms))
    except Exception as exc:                      # noqa: BLE001 - report and continue
        stats['errors'].append(f"{label}: {exc}")
        return

    if not chunks:
        stats['errors'].append(f"{label}: recorded nothing")
        return

    audio = np.concatenate(chunks, axis=0)[:, 0]
    pcm16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm16.tobytes())

    duration = len(audio) / RATE
    print(f"  {label:<9} wrote {path}  ({duration:.1f}s)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=int, default=30)
    ap.add_argument('--list', action='store_true', help='list audio devices and exit')
    ap.add_argument('--loopback', default=None, help='speaker/loopback device name fragment')
    ap.add_argument('--mic', default=None, help='microphone device name fragment')
    ap.add_argument('--outdir', default='.')
    args = ap.parse_args()

    if args.list:
        list_devices()
        return

    import soundcard as sc

    loop = resolve(args.loopback)
    if args.mic:
        mic = next((m for m in sc.all_microphones(include_loopback=False)
                    if args.mic.lower() in m.name.lower()), None)
        if mic is None:
            raise SystemExit(f"No microphone matching {args.mic!r}. Try --list.")
    else:
        mic = sc.default_microphone()
        if mic is None:
            raise SystemExit("No default microphone. Pass --mic explicitly.")

    print(f"Loopback : {loop.name}")
    print(f"Mic      : {mic.name}")
    print(f"Rate     : {RATE} Hz mono, {args.seconds}s")
    print()
    print("RECORDING. Play speech on the speakers, and talk into the mic.")
    print()

    stats = {'loopback': [], 'mic': [], 'errors': []}
    stop_event = threading.Event()

    threads = [
        threading.Thread(target=record, args=(loop, f"{args.outdir}/loopback.wav",
                                              args.seconds, 'loopback', stats, stop_event)),
        threading.Thread(target=record, args=(mic, f"{args.outdir}/mic.wav",
                                              args.seconds, 'mic', stats, stop_event)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print()
    if stats['errors']:
        for e in stats['errors']:
            print(f"ERROR {e}")
        sys.exit(1)

    print("Levels (peak dBFS):")
    silent = []
    for label in ('loopback', 'mic'):
        levels = stats[label]
        if not levels:
            silent.append(label)
            print(f"  {label:<9} no samples")
            continue
        peak = max(levels)
        print(f"  {label:<9} peak {peak:6.1f} dBFS   median {np.median(levels):6.1f} dBFS")
        if peak < WARN_DB:
            silent.append(label)

    print()
    if silent:
        print(f"WARNING: {', '.join(silent)} looked silent. Nothing was captured there.")
        print("  - Nothing playing / muted? Was the meeting actually running?")
        print("  - Wrong device? Re-run with --list and --loopback <name>.")
        print("  - Bluetooth headsets often expose no loopback at all. Try wired.")
        sys.exit(2)

    print("Both channels captured audio.")
    print()
    print("Now verify they are SEPARATE - this is the point of the test:")
    print("  loopback.wav should contain the other people, and not your voice")
    print("  mic.wav      should contain you, and not the other people")
    print()
    print("  py -3 -m pip install soundfile   # optional, or just open them")
    print()
    print("Convert for whisper:")
    print("  ffmpeg -i loopback.wav -ar 16000 -ac 1 -c:a pcm_s16le loopback16k.wav")
    print("  ffmpeg -i mic.wav      -ar 16000 -ac 1 -c:a pcm_s16le mic16k.wav")
    print()
    print("Then listen to mic.wav on headphones: if you can hear the remote")
    print("participants in it, they are leaking into your mic (speakerphone /")
    print("echo cancellation off) and SPEC section 6-C3 becomes a real feature.")


if __name__ == '__main__':
    main()
