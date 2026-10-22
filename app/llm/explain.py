"""Explain step: structured rows -> LLM text -> verifier -> verified text or fallback.

What leaves the machine (hard rule 9): for each usable row only id, name, value, unit,
printed range and code flag. Never the raw line, the page, or the file name.

Hard rule 8: if verification fails, generate once more; if that also fails, return no
text at all. The caller then shows only the values table with code flags and the
disclaimer. Failure reasons are logged as codes, without values.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from app.extract.pdf_rows import Row
from app.llm.client import LLMClient, LLMError
from app.schema import Report, usable_rows
from app.verify.facts import Entry, verify

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
DEFAULT_PROMPT = "explain_en_v1"
MAX_ATTEMPTS = 2  # first try plus one retry (hard rule 8)
log = logging.getLogger("explain")

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "text": {"type": "string"}},
                "required": ["id", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["rows"],
    "additionalProperties": False,
}


class _Output(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[Entry]


class TableRow(BaseModel):
    name: str
    value: float
    unit: str
    range_text: str
    flag: str


class ExplainedRow(TableRow):
    text: str


class Explanation(BaseModel):
    # "verified": rows carry text that passed the verifier.
    # "fallback": no text; show the values table only.
    status: Literal["verified", "fallback"]
    prompt: str
    attempts: int
    rows: list[ExplainedRow] = []
    table: list[TableRow] = []
    failure: list[str] = []  # codes only, for the log and for debugging


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def build_payload(rows: list[Row]) -> str:
    """The only report data the LLM ever sees."""
    return json.dumps(
        [
            {
                "id": i,
                "name": r.name,
                "value": r.value,
                "unit": r.unit,
                "range": r.range_text,
                "flag": r.computed_flag,
            }
            for i, r in enumerate(rows)
        ],
        ensure_ascii=False,
    )


def _attempt(client: LLMClient, system: str, user: str, rows: list[Row]) -> tuple[list[Entry], list[str]]:
    try:
        raw = client.complete(system, user, OUTPUT_SCHEMA)
    except LLMError as exc:
        return [], [f"llm:{exc}"]
    try:
        entries = _Output.model_validate_json(raw).rows
    except ValidationError:
        return [], ["unparseable_output"]  # unparseable counts as a rejection
    return entries, verify(rows, entries)


def _table(rows: list[Row]) -> list[TableRow]:
    return [
        TableRow(name=r.name, value=r.value, unit=r.unit, range_text=r.range_text, flag=r.computed_flag)
        for r in rows
    ]


def explain(report: Report, client: LLMClient, prompt: str = DEFAULT_PROMPT) -> Explanation:
    rows = usable_rows(report)
    table = _table(rows)
    if not rows:
        return Explanation(status="fallback", prompt=prompt, attempts=0, table=table, failure=["no_usable_rows"])

    system, user = load_prompt(prompt), build_payload(rows)
    problems: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        entries, problems = _attempt(client, system, user, rows)
        if not problems:
            by_id = {e.id: e.text for e in entries}
            explained = [ExplainedRow(**t.model_dump(), text=by_id[i]) for i, t in enumerate(table)]
            return Explanation(status="verified", prompt=prompt, attempts=attempt, rows=explained, table=table)
        log.warning("explanation rejected (attempt %d): %s", attempt, "; ".join(problems[:20]))
    return Explanation(status="fallback", prompt=prompt, attempts=MAX_ATTEMPTS, table=table, failure=problems)

