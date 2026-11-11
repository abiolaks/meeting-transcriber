# 04: Two-channel merge and speaker attribution

**What to build:** Two channel files in, one merged transcript out, with every segment labelled "You" or "Remote", ordered by timestamp, and simultaneous speech interleaved rather than concatenated end to end.

The two channels are transcribed separately on purpose — mixing them would pour the noisy mic signal into the clean loopback stream and make the remote participants harder to hear. This ticket joins them back together without giving up that advantage.

**Blocked by:** 03

**Status:** ready-for-agent

- [ ] Two channel files produce a single transcript with explicit You / Remote labels
- [ ] Segments are ordered by start time; overlapping speech is interleaved by timestamp
- [ ] The same speech appearing on both channels within a small offset is detected, counted once, and reported — this is the speakerphone case
- [ ] Channel identity survives into the note, so quotes still attribute to the right speaker
- [ ] A test with a constructed overlap produces correct interleaving
- [ ] A test with a duplicated echo produces one copy, not two
