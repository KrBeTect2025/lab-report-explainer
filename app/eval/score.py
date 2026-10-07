"""Score extracted rows against a hand-written answer key.

Counts, not just percentages. A key row that was not found counts as wrong in every
field, so missing rows cannot inflate accuracy. Extra rows are reported separately.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from app.rules.names import normalize_name
from app.rules.sanity import normalize_unit

FIELDS = ("name", "value", "unit", "range", "flag")


def _norm_range(text: str) -> str:
    t = (text or "").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", "", t).lower()


@dataclass
class Score:
    correct: dict = field(default_factory=lambda: {f: 0 for f in FIELDS})
    total: dict = field(default_factory=lambda: {f: 0 for f in FIELDS})
    errors: list = field(default_factory=list)
    extra_rows: list = field(default_factory=list)

    def add(self, other: "Score") -> None:
        for f in FIELDS:
            self.correct[f] += other.correct[f]
            self.total[f] += other.total[f]
        self.errors += other.errors
        self.extra_rows += other.extra_rows


def _index(rows: list[dict], name_key: str) -> dict:
    """Map (normalised name, occurrence number) to a row, so repeated names work."""
    seen: dict = defaultdict(int)
    out = {}
    for r in rows:
        n = normalize_name(r[name_key])
        out[(n, seen[n])] = r
        seen[n] += 1
    return out


def score_file(extracted_rows: list[dict], key_rows: list[dict], label: str = "") -> Score:
    s = Score()
    got = _index(extracted_rows, "name")
    want = _index(key_rows, "name")
    for ident, k in want.items():
        for f in FIELDS:
            s.total[f] += 1
        g = got.get(ident)
        if g is None:
            s.errors.append(f"{label} MISSING row: {k['name']}")
            continue
        s.correct["name"] += 1
        checks = {
            "value": abs(float(g["value"]) - float(k["value"])) < 1e-9,
            "unit": normalize_unit(g["unit"]) == normalize_unit(k["unit"]),
            "range": _norm_range(g["range_text"]) == _norm_range(k["range"]),
            "flag": g["computed_flag"] == k["flag"],
        }
        for f, ok in checks.items():
            if ok:
                s.correct[f] += 1
            else:
                s.errors.append(
                    f"{label} WRONG {f} for {k['name']}: got "
                    f"{ {'value': g['value'], 'unit': g['unit'], 'range': g['range_text'], 'flag': g['computed_flag']}[f] !r}"
                )
    for ident, g in got.items():
        if ident not in want:
            s.extra_rows.append(f"{label} EXTRA row: {g['name']} = {g['value']}")
    return s
