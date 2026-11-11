# 07: Windows end-to-end with live capture

**What to build:** The product, on the target laptop: press start before a real meeting, press stop after it, and receive a `note.md` — entirely offline, no manual steps, no second machine involved.

This is the milestone that proves or disproves the whole premise. Everything before it is necessary but none of it is sufficient.

**Blocked by:** 05, 06

**Status:** ready-for-agent

- [ ] Full run on the i7-8650U: capture → transcription → note, unattended
- [ ] The note is produced entirely offline after the model fetch
- [ ] Total time from stop to note is recorded in `bench/RESULTS.md`, broken down by stage
- [ ] Works with headphones; the speakerphone case either works or produces an explicit warning rather than a silently degraded transcript
- [ ] The person who attended the meeting judges the note usable — sections recognisable, action items correct, no invented content
- [ ] Any resource problem during the run (thermal throttle, memory pressure) is logged rather than silently absorbed
- [ ] The recording is retained, so the same meeting can be reprocessed later if the note disappoints
