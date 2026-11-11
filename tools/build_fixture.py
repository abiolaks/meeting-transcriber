"""Generate the transcript fixture for ticket 01.

A hand-written two-channel meeting of about ten minutes, with plausible speech,
natural pauses between turns, and word-level timings.

It is synthetic on purpose: a stable, inspectable input for the pipeline, and a
deterministic input for tests. It says nothing about real WER — a gold set of real
meetings replaces it in ticket 05.

    python3 tools/build_fixture.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# (channel, text) — ch0 is "You", ch1 is "Remote"
SCRIPT: list[tuple[str, str]] = [
    ("ch1", "Thanks for joining. Let's start with the billing migration and where we actually are."),
    ("ch0", "Sure. My understanding is we're behind. How far behind are we?"),
    ("ch1", "About two weeks at this point. The retry queue is the only thing that can still bite us."),
    ("ch0", "What is the failure rate on retries?"),
    ("ch1", "Roughly four percent fail on the third attempt, and then they are dropped entirely."),
    ("ch1", "Nobody gets told. The customer just does not get charged, and no invoice is raised."),
    ("ch0", "That is worse than a failed payment, because it is invisible."),
    ("ch1", "Exactly. That is why I would rather slip the date than ship it as it stands."),
    ("ch1", "Sam has been looking at the queue behaviour. Do you want to take that part?"),
    ("ch1", "The backoff is linear right now. Retries go out at one minute, two minutes, three minutes."),
    ("ch1", "By the time the fourth retry lands, Stripe has already given up on the event."),
    ("ch0", "So we should move to exponential backoff with jitter?"),
    ("ch1", "Yes. And add a dead letter queue so nothing is dropped silently."),
    ("ch0", "Who owns that piece of work?"),
    ("ch1", "I will fix the backoff and add the dead letter queue by Friday."),
    ("ch0", "Good. Does that push the launch?"),
    ("ch1", "It pushes it a week. Not because of the code, because of the soak test afterwards."),
    ("ch0", "How long does the soak test need?"),
    ("ch1", "Five working days, minimum. I do not want to discover a queue problem in production."),
    ("ch0", "Agreed. Let us call the launch the twentieth and freeze feature work until then."),
    ("ch1", "I will update the release calendar today and tell support what changed."),
    ("ch0", "Speaking of support, they need a runbook for replaying a dead lettered event."),
    ("ch1", "That is the part nobody has thought about. Who writes it?"),
    ("ch0", "Can you draft it? You know the queue better than anyone."),
    ("ch1", "I can draft it, but I need sandbox access to Stripe first, and I do not have it."),
    ("ch0", "I will chase that with finance today. It is usually a billing owner approval."),
    ("ch1", "Then I will write the runbook once I have access, probably early next week."),
    ("ch0", "What is the rollout going to look like? Big bang or gradual?"),
    ("ch1", "Gradual. Ten percent of accounts for a day, then fifty, then everything."),
    ("ch1", "That way if the dead letter queue fills up we find out while it is still small."),
    ("ch0", "Do we have a way to see the queue filling up?"),
    ("ch1", "Not really. There is a dashboard for throughput but nothing for failures."),
    ("ch0", "So we need metrics on the queue depth and the failure count."),
    ("ch1", "I will add both. It is a small change if I do it at the same time as the backoff."),
    ("ch0", "What about alerting? I do not want to find out from a customer."),
    ("ch1", "An alert if the dead letter queue is non empty for more than fifteen minutes."),
    ("ch0", "That sounds about right. Where does the alert go?"),
    ("ch1", "The billing on call channel. I will add the rotation to the runbook as well."),
    ("ch0", "Good. What else could surprise us?"),
    ("ch1", "The invoice date uses server time, which is UTC, and customers in Lagos complain."),
    ("ch0", "How bad is that?"),
    ("ch1", "It is a day out for anyone billing near midnight. We had four complaints last month."),
    ("ch0", "Is that in scope for this launch or separate?"),
    ("ch1", "Separate, but it should be the next thing we do. It is a one line change plus a test."),
    ("ch0", "Can you raise it as a ticket today so it does not get lost?"),
    ("ch1", "I will raise it before the end of the day."),
    ("ch0", "And the migration script itself? Has it run against a production sized copy?"),
    ("ch1", "No. That is the other risk. It has only run against the sample database."),
    ("ch0", "Who is doing that?"),
    ("ch1", "Sam will, once the sandbox is available. It takes about four hours to run."),
    ("ch0", "Four hours of blocking work or can it run in the background?"),
    ("ch1", "Background, mostly. It is a batch job with a progress table."),
    ("ch0", "Then that is fine. Let us run it Thursday night so we have the results Friday."),
    ("ch1", "I will put it in the calendar. Do you want a rollback plan written down?"),
    ("ch0", "Yes. If the migration fails halfway we need to know exactly what to restore."),
    ("ch1", "I will write it with the runbook. Same audience, same document probably."),
    ("ch0", "Good. So the critical path is sandbox access, then the backoff fix, then the soak test."),
    ("ch1", "That is right. Everything else can happen in parallel."),
    ("ch0", "One more thing. Do support need to tell customers anything in advance?"),
    ("ch1", "Only if we slip the date publicly. Internally I will send a note to the sales channel."),
    ("ch0", "Let us do that once the freeze is confirmed, not before."),
    ("ch1", "Agreed. I will draft it and hold it until you say go."),
    ("ch0", "Perfect. Let us regroup Thursday. I will send the calendar hold."),
    ("ch1", "Sounds good. Thanks everyone."),
]

# Pause inserted after each turn, in seconds. Varies so the transcript is not
# metronomically even.
PAUSES = [1.2, 0.8, 1.5, 0.6, 1.1, 0.7, 0.9, 1.4, 1.0, 0.8, 1.6, 0.6]
WORDS_PER_SECOND = 2.0
PAUSE_SCALE = 3.15  # thinking time, not dead air


def word_timings(text: str, start: float, end: float) -> list[dict[str, Any]]:
    """Spread words across the segment, weighted by word length."""
    words = text.split()
    if not words:
        return []
    weights = [len(word) + 1 for word in words]
    total = sum(weights)
    span = end - start

    timings = []
    cursor = start
    for word, weight in zip(words, weights):
        duration = span * weight / total
        timings.append({
            "w": word,
            "start": round(cursor, 3),
            "end": round(cursor + duration, 3),
        })
        cursor += duration
    return timings


def build() -> dict[str, Any]:
    segments = []
    cursor = 0.0
    for index, (channel, text) in enumerate(SCRIPT, start=1):
        speech = len(text.split()) / WORDS_PER_SECOND
        end = cursor + speech
        segments.append({
            "id": f"s{index:02d}",
            "start": round(cursor, 3),
            "end": round(end, 3),
            "channel": channel,
            "text": text,
            "words": word_timings(text, cursor, end),
        })
        cursor = end + PAUSES[index % len(PAUSES)] * PAUSE_SCALE

    return {
        "version": 1,
        "meeting": {
            "title": "Billing migration weekly",
            "date": "2026-11-11",
            "duration_s": round(cursor, 3),
        },
        "channels": [
            {"id": "ch0", "label": "You"},
            {"id": "ch1", "label": "Remote"},
        ],
        "segments": segments,
    }


def main() -> None:
    doc = build()
    out = Path(__file__).resolve().parents[1] / "fixtures" / "transcript-sample.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    words = sum(len(s["text"].split()) for s in doc["segments"])  # type: ignore[index]
    minutes = doc["meeting"]["duration_s"] / 60  # type: ignore[index]
    print(f"wrote {out} — {len(doc['segments'])} turns, {words} words, {minutes:.1f} min")


if __name__ == "__main__":
    main()
