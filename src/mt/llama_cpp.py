"""The real local model adapter: llama.cpp, JSON grammar, no network.

Three jobs, each testable without a model:

- `build_prompt` turns paragraphs into the one instruction the model gets;
- `GRAMMAR` constrains decoding to syntactically valid JSON, so the model cannot
  answer with prose no matter how small it is;
- `parse_draft` turns whatever came back into a `NoteDraft`, or raises.

Only `draft()` genuinely needs a model, and it is the thin part.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Sequence

from .note import ActionItem, Decision, NoteDraft, Section
from .paragraphs import Paragraph
from .transcript import Meeting

# Permissive JSON: guarantees shape, not content. Semantic validation happens in
# parse_draft, and a failure there is retried once by note.build.
GRAMMAR = r"""
root    ::= object
object  ::= "{" ws (pair ("," ws pair)*)? ws "}"
pair    ::= string ws ":" ws value
value   ::= object | array | string | number | "true" | "false" | "null"
array   ::= "[" ws (value ("," ws value)*)? ws "]"
string  ::= "\"" char* "\""
char    ::= [^"\\] | "\\" escape
escape  ::= ["\\/bfnrt] | "u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F]
number  ::= "-"? ("0" | [1-9] [0-9]*) ("." [0-9]+)? ([eE] ("+" | "-")? [0-9]+)?
ws      ::= [ \t\n\r]*
"""

# Deliberately NOT a filled example. Every filled example we tried was copied
# verbatim by the model instead of being used as a shape.
SCHEMA = """{"sections":[{"title":<string>,"start":<seconds>,"end":<seconds>,"summary":<string>}],
 "actions":[{"owner":<string or null>,"action":<string>,"due":<string or null>,
             "quote":<string copied from the transcript>,"start":<seconds>}],
 "decisions":[{"text":<string>,"start":<seconds>}],
 "questions":[<string>]}"""

# What a model copies when it has nothing to say. Never let this reach a note.
PLACEHOLDERS = {"", ".", "...", "\u2026", "-", "n/a", "none"}

TASK = """Write the JSON note for the transcript above.

- Replace every <placeholder> above with real content from the transcript.
- Do not copy the schema text. Do not invent names, dates or quotations.
- quote must be copied word for word from the transcript.
- start and end are seconds from the beginning of the recording.
- sections must cover the whole meeting, in order, with no gaps and no overlaps.
- Three to six sections; at most twenty action items.
- owner is null unless the transcript says who will do it.
- when a speaker says "I will", "I'll" or "I can", the owner is that speaker's
  label: "You" or "Remote".
- If the transcript does not say, omit the item rather than guessing."""

MAX_TRANSCRIPT_CHARS = 24_000


def _clock(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    return f"{total // 60:02d}:{total % 60:02d}"


def build_prompt(meeting: Meeting, paragraphs: Sequence[Paragraph]) -> str:
    lines = [
        f"Meeting transcript: {meeting.title} ({_clock(meeting.duration_s)} long)",
        "",
    ]
    for paragraph in paragraphs:
        lines.append(f"[{_clock(paragraph.start)}] {paragraph.label}: {paragraph.text}")

    body = "\n".join(lines)
    if len(body) > MAX_TRANSCRIPT_CHARS:
        # Truncation is a stopgap; chunked extraction is ticket 05's job.
        body = body[:MAX_TRANSCRIPT_CHARS] + "\n[transcript truncated]"

    return f"{body}\n\n{TASK}\n\nExpected fields:\n{SCHEMA}\n"


def to_seconds(value: Any) -> float:
    """Accept 123.4, "123.4", "03:22" or "01:02:03" — models emit all four."""
    if isinstance(value, bool):
        raise ValueError("boolean is not a timestamp")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        try:
            return float(text)
        except ValueError:
            pass
        parts = text.split(":")
        try:
            numbers = [float(part) for part in parts]
        except ValueError as exc:
            raise ValueError(f"cannot read timestamp {value!r}") from exc
        if len(numbers) == 2:
            return numbers[0] * 60 + numbers[1]
        if len(numbers) == 3:
            return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
    raise ValueError(f"cannot read timestamp {value!r}")


# Models frequently emit the *string* "null" where JSON null was meant, which
# would otherwise render as an owner named null.
NULLISH = {"", "null", "none", "n/a", "na", "unassigned", "-", "unknown"}


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text if text.lower() not in NULLISH else None
    return None


def parse_draft(text: str) -> NoteDraft:
    """Turn model output into a NoteDraft, or raise ValueError.

    Scanning for decodable objects rather than slicing between the first and last
    brace: llama.cpp prints a banner, and a truncated generation ends mid-object.
    Either would corrupt a naive slice.
    """
    decoder = json.JSONDecoder()
    doc = None
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and ("sections" in candidate or "actions" in candidate):
            doc = candidate
            break

    if doc is None:
        raise ValueError("model did not return a JSON object with note fields")

    sections = []
    for raw in doc.get("sections") or []:
        if not isinstance(raw, dict):
            continue
        try:
            sections.append(Section(
                title=str(raw.get("title") or "Untitled").strip(),
                start=to_seconds(raw.get("start")),
                end=to_seconds(raw.get("end")),
                summary=str(raw.get("summary") or "").strip(),
            ))
        except (ValueError, TypeError):
            continue

    actions = []
    for raw in doc.get("actions") or []:
        if not isinstance(raw, dict):
            continue
        quote = str(raw.get("quote") or "").strip()
        action = str(raw.get("action") or "").strip()
        if not action:
            continue
        try:
            start_seconds = to_seconds(raw.get("start"))
        except ValueError:
            continue
        actions.append(ActionItem(
            owner=_optional_str(raw.get("owner")),
            action=action,
            due=_optional_str(raw.get("due")),
            quote=quote,
            start=start_seconds,
        ))

    decisions = []
    for raw in doc.get("decisions") or []:
        if not isinstance(raw, dict):
            continue
        text_value = str(raw.get("text") or "").strip()
        if not text_value:
            continue
        try:
            decisions.append(Decision(text=text_value, start=to_seconds(raw.get("start"))))
        except ValueError:
            continue

    questions = tuple(
        str(q).strip() for q in (doc.get("questions") or []) if str(q).strip()
    )

    draft = NoteDraft(
        sections=tuple(sections),
        actions=tuple(actions),
        decisions=tuple(decisions),
        questions=questions,
    )
    if _looks_like_template(draft):
        raise ValueError(
            "model returned template placeholders instead of content; "
            "the draft says nothing about the meeting"
        )
    return draft


def _looks_like_template(draft: NoteDraft) -> bool:
    def junk(value: str | None) -> bool:
        return (value or "").strip().lower() in PLACEHOLDERS

    if draft.sections and all(junk(s.title) and junk(s.summary) for s in draft.sections):
        return True
    if draft.actions and all(junk(a.action) for a in draft.actions):
        return True
    if draft.decisions and all(junk(d.text) for d in draft.decisions):
        return True
    return False



class LlamaCppLLM:
    """Local llama.cpp backend. No network, no server, one process per draft."""

    name = "llama"

    def __init__(
        self,
        model_path: str | None = None,
        *,
        binary: str = "llama-cli",
        threads: int = 4,
        max_tokens: int = 1200,
        timeout: int = 900,
    ) -> None:
        self.model_path = model_path
        self.binary = binary
        self.threads = threads
        self.max_tokens = max_tokens
        self.timeout = timeout

    def _command(self, prompt: str, grammar_path: Path) -> list[str]:
        return [
            self.binary,
            "-m", str(self.model_path),
            "-p", prompt,
            "-n", str(self.max_tokens),
            "-c", "4096",
            "-t", str(self.threads),
            "--temp", "0.1",
            "--top-k", "20",
            "--no-display-prompt",
            "--log-disable",
            "--simple-io",
            "--no-warmup",
            "-st",
            "--grammar-file", str(grammar_path),
        ]

    def draft(self, meeting: Meeting, paragraphs: Sequence[Paragraph]) -> NoteDraft:
        if not self.model_path:
            raise ValueError("no model path given; pass --model or run `mt models fetch`")

        prompt = build_prompt(meeting, paragraphs)
        with tempfile.TemporaryDirectory() as directory:
            grammar_path = Path(directory) / "note.gbnf"
            grammar_path.write_text(GRAMMAR, encoding="utf-8")
            result = subprocess.run(
                self._command(prompt, grammar_path),
                capture_output=True, text=True, timeout=self.timeout, check=False,
            )

        if result.returncode != 0:
            raise ValueError(
                f"llama.cpp exited {result.returncode}: {result.stderr.strip()[:300]}"
            )
        return parse_draft(result.stdout)
