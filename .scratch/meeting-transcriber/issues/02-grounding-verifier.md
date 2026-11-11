# 02: Grounding verifier

**What to build:** Every action item and decision in the note must be traceable to a verbatim quote from the transcript. Items whose quote cannot be found are demoted to an "Unverified" list and kept out of the main table. Owners are classified as stated, inferred or unassigned, and only stated owners appear as fact.

The point is that the note may be incomplete but must never be confidently wrong. An invented owner destroys trust faster than a missed action.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Each action item carries a quote that is a normalised substring of the transcript
- [ ] A failed match moves the item to "Unverified" and out of the main action-item table
- [ ] Owner confidence is recorded as stated / inferred / unassigned
- [ ] Inferred owners are grouped under a "Suspected, confirm" heading rather than presented as fact
- [ ] A test with a deliberately fabricated action item proves it is caught
- [ ] A test with a real item differing only in case or punctuation proves normalisation does not cause a false rejection
- [ ] The note reports how many items were demoted, so silent loss is visible
