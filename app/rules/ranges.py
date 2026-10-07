"""Reference range parsing and low / normal / high flagging.

This is plain code on purpose. No model decides whether a value is high or low.
When a range cannot be understood, the flag is "unknown" and nothing is guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# A number as printed on Indian reports. Commas are allowed (1,50,000).
NUM = r"\d[\d,]*(?:\.\d+)?"


def to_float(text: str) -> float:
    return float(text.replace(",", ""))


@dataclass(frozen=True)
class Range:
    low: Optional[float] = None
    high: Optional[float] = None
    low_inclusive: bool = True
    high_inclusive: bool = True


_BETWEEN = re.compile(rf"^({NUM})\s*(?:-|to)\s*({NUM})$")
_UPPER = re.compile(rf"^(<=|<|[Uu]p\s*to|[Uu]pto)\s*({NUM})$")
_LOWER = re.compile(rf"^(>=|>)\s*({NUM})$")
# A unit sometimes follows the range, for example "<200.00 mg/dL".
_TRAILING_UNIT = re.compile(r"\s+[A-Za-z%µμ][^\s]*$")


def _clean(text: str) -> str:
    t = text.strip()
    t = t.replace("–", "-").replace("—", "-")  # en dash, em dash
    t = t.replace("≤", "<=").replace("≥", ">=")  # less/greater or equal
    return re.sub(r"\s+", " ", t)


def _match(candidate: str) -> Optional[Range]:
    m = _BETWEEN.match(candidate)
    if m:
        low, high = to_float(m.group(1)), to_float(m.group(2))
        return Range(low=low, high=high) if low <= high else None
    m = _UPPER.match(candidate)
    if m:
        op = m.group(1)
        inclusive = op == "<=" or op.lower().startswith("up")
        return Range(high=to_float(m.group(2)), high_inclusive=inclusive)
    m = _LOWER.match(candidate)
    if m:
        return Range(low=to_float(m.group(2)), low_inclusive=(m.group(1) == ">="))
    return None


def parse_range(text: Optional[str]) -> Optional[Range]:
    """Return a Range, or None when the text is not a simple range.

    Descriptive ranges such as "Desirable: <200 Borderline: 200-239" return None
    on purpose. Refusing to guess is safer than picking one band.
    """
    if not text:
        return None
    t = _clean(text)
    for candidate in (t, _TRAILING_UNIT.sub("", t)):
        found = _match(candidate)
        if found:
            return found
    return None


def flag_value(value: float, rng: Optional[Range]) -> str:
    """Return "low", "normal", "high" or "unknown"."""
    if rng is None:
        return "unknown"
    if rng.low is not None:
        if value < rng.low or (not rng.low_inclusive and value == rng.low):
            return "low"
    if rng.high is not None:
        if value > rng.high or (not rng.high_inclusive and value == rng.high):
            return "high"
    return "normal"
