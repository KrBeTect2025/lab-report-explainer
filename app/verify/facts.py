"""Verifier layer 1: check generated text against the extracted rows, in plain code.

Each text entry belongs to one row. An entry passes only when:
- every number in it is the row's value or a number from the row's printed range,
- the value appears, followed by the row's unit,
- no number is followed by a different unit,
- its low / normal / high words agree with the code flag (none at all when the flag is
  "unknown"), and the expected flag is actually stated,
- a low or high row ends with "please discuss this with your doctor" (hard rule 4),
- it does not say "you have" (hard rule 2).

Checks are per row on purpose: a number from another row (for example a platelet count
inside the hemoglobin sentence) is rejected, not accepted because it exists somewhere.

When unsure, this rejects. A rejected text is never shown; the user gets the values table.
Problem strings carry a row id and a code, never a value, so they are safe to log.
"""
from __future__ import annotations

import re
from typing import Sequence

from pydantic import BaseModel

from app.extract.pdf_rows import Row, looks_like_unit
from app.rules.ranges import NUM, to_float

DOCTOR_LINE = "please discuss this with your doctor"

# A digit run anywhere, even inside a word such as "T3". Only the row's own name is
# removed first, so a digit from another test's name ("B12") still counts as a number.
_NUMBER = re.compile(NUM)
_WORD = re.compile(r"[a-z]+")
_NEXT_TOKEN = re.compile(r"\s*(\S+)")
_DIAGNOSTIC = re.compile(r"\byou\s+have\b", re.I)

# Which flags each word may be used with. "abnormal" fits low and high but not normal.
_FLAG_WORDS: dict[str, set[str]] = {
    **{w: {"high"} for w in ("high", "higher", "above", "raised", "elevated", "increased")},
    **{w: {"low"} for w in ("low", "lower", "below", "reduced", "decreased")},
    **{w: {"normal"} for w in ("normal", "within")},
    "abnormal": {"low", "high"},
}


class Entry(BaseModel):
    id: int
    text: str


def _unit_pattern(unit: str) -> re.Pattern:
    """The unit as printed, allowing spaces between characters and any micro sign."""
    parts = []
    for ch in unit.replace(" ", ""):
        parts.append("[µμu]" if ch in "µμu" else re.escape(ch))
    return re.compile(r"\s*" + r"\s*".join(parts), re.I)


def _looks_like_unit_token(token: str) -> bool:
    t = token.rstrip(".,;:)")
    return bool(t) and (looks_like_unit(t) or t.lower() in {"percent", "per"})


def _blank_name(text: str, name: str) -> str:
    """Replace the row's own test name with spaces (same length keeps positions)."""
    if not name:
        return text
    return re.sub(re.escape(name), lambda m: " " * len(m.group()), text, flags=re.I)


def check_entry(row: Row, text: str) -> list[str]:
    problems: list[str] = []
    t = _blank_name(text, row.name)
    allowed = {row.value} | {to_float(n) for n in _NUMBER.findall(row.range_text)}
    unit_re = _unit_pattern(row.unit) if row.unit.strip() else None

    value_with_unit = False
    pos = 0
    while (m := _NUMBER.search(t, pos)) is not None:
        number = to_float(m.group())
        pos = m.end()
        unit_m = unit_re.match(t, pos) if unit_re else None
        if unit_m:
            pos = unit_m.end()  # skip the unit, so the 3 in "10^3/uL" is not a number
            if number == row.value:
                value_with_unit = True
        else:
            nxt = _NEXT_TOKEN.match(t, pos)
            if nxt and _looks_like_unit_token(nxt.group(1)):
                problems.append("wrong_unit")
            elif number == row.value and unit_re is None:
                value_with_unit = True  # the row has no unit, so a bare value is right
        if number not in allowed:
            problems.append("unknown_number")
    if not value_with_unit:
        problems.append("value_missing_or_without_unit")

    flag = row.computed_flag
    words = set(_WORD.findall(t.lower()))
    used = [w for w in words if w in _FLAG_WORDS]
    if any(flag not in _FLAG_WORDS[w] for w in used):
        problems.append("flag_word_mismatch")
    if flag in ("low", "high", "normal") and not any(
        _FLAG_WORDS[w] == {flag} for w in used
    ):
        problems.append("flag_not_stated")

    if flag in ("low", "high") and DOCTOR_LINE not in " ".join(text.lower().split()):
        problems.append("doctor_line_missing")
    if _DIAGNOSTIC.search(text):
        problems.append("diagnostic_wording")
    return sorted(set(problems))


def verify(rows: Sequence[Row], entries: Sequence[Entry]) -> list[str]:
    """Every row gets exactly one entry and every entry passes. Returns problem codes."""
    problems: list[str] = []
    seen: set[int] = set()
    for e in entries:
        if not 0 <= e.id < len(rows):
            problems.append(f"entry {e.id}: no_such_row")
            continue
        if e.id in seen:
            problems.append(f"row {e.id}: duplicate_entry")
            continue
        seen.add(e.id)
        problems += [f"row {e.id}: {p}" for p in check_entry(rows[e.id], e.text)]
    problems += [f"row {i}: missing_entry" for i in range(len(rows)) if i not in seen]
    return problems
