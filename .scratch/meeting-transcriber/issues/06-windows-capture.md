# 06: Windows capture — loopback and mic to two WAVs

**What to build:** A recorder that captures the meeting audio and the microphone as two separate files during a live call on Windows, showing per-channel input levels while it records so silence is visible during the meeting rather than discovered afterwards.

This is the only part of the project that cannot be verified anywhere except the target laptop, so it stays deliberately independent of the pipeline tickets.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Two files written simultaneously: loopback (remote participants) and mic (local user)
- [ ] Per-channel level visible during recording; sustained silence on either channel warns before the user stops
- [ ] The two outputs are genuinely separate — the loopback file does not contain the local user's voice when headphones are used
- [ ] 30-minute continuous capture with no dropouts; file duration matches wall-clock within 1%
- [ ] Verified against Zoom and Teams on the target laptop, and against Meet running in a browser
- [ ] Plugging in or removing a headset mid-recording does not stop or corrupt the capture
- [ ] The speakerphone case is either handled or explicitly warned about
