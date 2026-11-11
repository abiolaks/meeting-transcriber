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

## Comments

**2026-11-11 — complete.** `mt merge` combines per-channel transcripts onto one
timeline, keeping both channels and their labels.

Both reviews found the same concurrency bug: echo detection depended on arrival
order. Sorting by `(start, channel)` put ch0 first, so on equal start times the
mic copy entered the kept list and the loopback copy was never compared — both
survived. Resolution is now by role, never by order, and there is a test for the
equal-start case.

Also from review:
- channels that share a label are made distinct (You / Remote), because two
  transcripts transcribed without `--label` both default to "You"
- a short utterance is never treated as echo — two people saying "yes" at once is
  crosstalk, and dropping one loses speech
- similarity threshold raised 0.70 → 0.85 for the same reason
- speakerphone echo now warns on stderr, not just a stdout count
- `--mic-channel` exposed, so the echo rule cannot silently break on relabelled
  channels

Known limitations:
- interleaving is at *segment* granularity: overlapping utterances stay whole and
  are ordered by start, not split word by word
- `echoes_removed` is reported to the user but is not persisted in the transcript
  or the note
- more than two channels are accepted, but duplicate copies between two non-mic
  channels are not deduplicated
- a silent channel yields no transcript at all (the ASR adapter raises), so
  "one channel plus silence" merges nothing
