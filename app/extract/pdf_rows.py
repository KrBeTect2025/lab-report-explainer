"""Read a digital lab-report PDF and rebuild its table rows.

Why this exists: plain "extract text" output can list all test names first and all
values later, so rows no longer line up. Here every word keeps its position on the
page (x, y). Words on the same horizontal line form a row. Columns come from the
header row (Test / Result / Unit / Reference) when there is one, and from a
pattern match when there is not.

Nothing is dropped silently. Lines that look like results but cannot be parsed are
returned in "unparsed" so a person can look at them.

Limits (by design, for now): digital PDFs only (no OCR), one test per line (no
side-by-side two-column layouts), numeric results only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict
from typing import Literal, Optional

import pdfplumber
from pydantic.dataclasses import dataclass

from app.rules.ranges import NUM, flag_value, parse_range, to_float
from app.rules.sanity import check_unit

LINE_TOL = 3.0  # points: words this close vertically are on one line
COL_TOL = 14.0  # points: a word may sit this far left of its column start

VALUE_RE = re.compile(
    rf"^(?:(?P<flag>[HL])\s+)?(?P<value>{NUM})(?:\s+(?P<word>High|Low|Normal))?$", re.I
)
LINE_RE = re.compile(
    rf"^(?P<name>[A-Za-z].*?)\s+(?:(?P<flag>[HL])\s+)?(?P<value>{NUM})\s+"
    rf"(?P<unit>[^\s\d<>=≤≥\-–][^\s]*)\s+"
    rf"(?P<range>(?:<=|>=|<|>|≤|≥|[Uu]p\s*to\s*)?\s*{NUM}"
    rf"(?:\s*(?:-|–|to)\s*{NUM})?)\s*$"
)
# Used only to decide whether an unmatched line deserves a warning.
UNIT_HINT = re.compile(
    r"(g/dl|mg/dl|mmol|%|\bfl\b|\bpg\b|/cmm|/ul|mm3|iu/|u/l|ng/|pg/|meq)", re.I
)
NUM_RE = re.compile(NUM)

# Letter-only units that are real. Anything with "/" or "%" is also accepted.
_PLAIN_UNITS = {
    "fl", "pg", "g", "mg", "ug", "mcg", "ng", "iu", "u", "sec", "secs", "seconds",
    "ratio", "index", "cumm", "cmm", "mm", "lakhs", "mmol", "meq", "ml", "dl",
}


def looks_like_unit(text: str) -> bool:
    """True for g/dL, %, fL, thou/mm3 ... False for words like "of" or "Male"."""
    t = text.strip().lower()
    if not t:
        return False
    return "/" in t or "%" in t or t in _PLAIN_UNITS


_HDR_NAME = {"test", "investigation", "parameter", "observation", "analyte"}
_HDR_VALUE = {"result", "results"}
_HDR_UNIT = {"unit", "units"}
_HDR_RANGE = {"reference", "ref.", "ref", "bio.", "biological", "range", "interval"}
# Known so its text gets its own cell instead of joining the range (seen on hod_pk0016).
_HDR_METHOD = {"method"}

# Some PDFs store plain ASCII as U+F020..U+F07E, a Windows symbol-font encoding
# (seen on drlal_z615). Subtracting 0xF000 gives the real character back.
_PUA = {c: c - 0xF000 for c in range(0xF020, 0xF07F)}
DECODED_REASON = "text decoded from symbol-font encoding; check unit (µ may read as m)"


@dataclass
class Row:
    name: str
    value: float
    unit: str
    range_text: str
    computed_flag: str  # low / normal / high / unknown, from plain code
    reported_flag: Optional[str]  # H / L / N if the lab printed one
    flag_mismatch: bool  # lab flag disagrees with computed flag
    unit_check: str  # ok / unexpected / unchecked
    page: int
    raw: str
    confidence: str = "high"  # "low" rows must be confirmed by a person
    review_reason: str = ""
    # What a person decided (see app/schema.py). Kept apart from confidence, which is
    # the extractor's own opinion and does not change.
    status: Literal["unreviewed", "confirmed", "corrected", "rejected"] = "unreviewed"


def group_lines(words: list[dict]) -> list[list[dict]]:
    """Group words into horizontal lines using their vertical position."""
    lines: list[list] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(w["top"] - lines[-1][0]) <= LINE_TOL:
            lines[-1][1].append(w)
        else:
            lines.append([w["top"], [w]])
    return [sorted(ws, key=lambda w: w["x0"]) for _, ws in lines]


def detect_header(line: list[dict]) -> Optional[dict[str, float]]:
    """Return column start positions if this line is a table header."""
    toks = [(w["text"].lower().strip(":"), w["x0"]) for w in line]
    if not any(t in _HDR_VALUE for t, _ in toks):
        return None
    if not any(t in _HDR_UNIT for t, _ in toks):
        return None
    cols: dict[str, float] = {}
    for t, x in toks:  # line is sorted left to right, so first hit is leftmost
        for key, vocab in (
            ("name", _HDR_NAME),
            ("value", _HDR_VALUE),
            ("unit", _HDR_UNIT),
            ("range", _HDR_RANGE),
            ("method", _HDR_METHOD),
        ):
            if t in vocab and key not in cols:
                cols[key] = x
    if "range" not in cols:
        return None
    cols.setdefault("name", 0.0)
    return cols


def assign_columns(line: list[dict], cols: dict[str, float]) -> dict[str, str]:
    order = sorted(cols.items(), key=lambda kv: kv[1])
    out: dict[str, list[str]] = {k: [] for k in cols}
    for w in line:
        key = order[0][0]
        for k, x in order:
            if w["x0"] >= x - COL_TOL:
                key = k
        out[key].append(w["text"])
    return {k: " ".join(v).strip() for k, v in out.items()}


def make_row(
    name: str,
    reported_flag: Optional[str],
    value_text: str,
    unit: str,
    range_text: str,
    page: int,
    raw: str,
) -> Row:
    value = to_float(value_text)
    computed = flag_value(value, parse_range(range_text))
    reasons = []
    if not parse_range(range_text) and not looks_like_unit(unit):
        reasons.append("no unit and no readable range (could be a heading or note)")
    if len(name.split()) > 6:
        reasons.append("very long name (could be a sentence)")
    expected = {"H": "high", "L": "low", "N": "normal"}.get(reported_flag or "")
    mismatch = bool(
        expected and computed != "unknown" and computed != expected
    )
    return Row(
        name=name.strip(),
        value=value,
        unit=unit,
        range_text=range_text.strip(),
        computed_flag=computed,
        reported_flag=reported_flag,
        flag_mismatch=mismatch,
        unit_check=check_unit(name, unit),
        page=page,
        raw=raw,
        confidence="low" if reasons else "high",
        review_reason="; ".join(reasons),
    )


def parse_by_columns(line, cols, page, raw):
    cells = assign_columns(line, cols)
    name = cells.get("name", "")
    value_text = cells.get("value", "")
    unit = cells.get("unit", "")
    range_text = cells.get("range", "")
    if not name:
        return None, None  # continuation text, nothing to read
    if not value_text:
        if looks_like_unit(unit) and parse_range(range_text):
            return None, "missing_value"
        return None, None  # heading or note
    m = VALUE_RE.match(value_text)
    if not m:
        # Only warn when the rest of the line really looks like a result row.
        if looks_like_unit(unit) or parse_range(range_text):
            return None, "non_numeric_value"
        return None, None
    if unit and not looks_like_unit(unit):
        return None, None  # numbers in a text line, for example an address
    flag = m.group("flag") or (m.group("word") or "")[:1].upper() or None
    return make_row(name, flag, m.group("value"), unit, range_text, page, raw), None


def parse_by_regex(text, page):
    m = LINE_RE.match(text)
    if not m or not looks_like_unit(m.group("unit")):
        return None, None  # for example "Page 1 of 2" must never become a result
    return make_row(
        m.group("name"),
        m.group("flag"),
        m.group("value"),
        m.group("unit"),
        m.group("range"),
        page,
        text,
    ), None


def _angle(obj: dict) -> tuple[float, float]:
    return (round(obj["matrix"][1], 2), round(obj["matrix"][2], 2))


def drop_rotated_text(page):
    """Keep only characters drawn at the page's main angle.

    Why: a diagonal "Sample Report" watermark drops single letters into table cells
    ("e2.0", "a55.5"), which breaks values and ranges (seen on hod_pk0016).
    """
    counts = Counter(_angle(c) for c in page.chars)
    if not counts:
        return page
    main = counts.most_common(1)[0][0]
    return page.filter(lambda o: o.get("object_type") != "char" or _angle(o) == main)


def decode_symbol_font(chars: list[dict]) -> bool:
    """Shift U+F0xx characters back to ASCII, in place. Returns True if it did.

    Only when most characters use that encoding. A lone U+F0xx inside normal text may
    be a real symbol (Symbol-font µ is U+F06D, which would become "m"), so it stays.
    """
    pua = sum(ord(c["text"][:1] or " ") in _PUA for c in chars)
    if pua * 2 <= len(chars):
        return False
    for c in chars:
        c["text"] = c["text"].translate(_PUA)
    return True


class TooManyPages(ValueError):
    pass


def extract_pdf(path: str, max_pages: Optional[int] = None) -> dict:
    rows: list[Row] = []
    unparsed: list[dict] = []
    cols: Optional[dict[str, float]] = None
    table_top = 0.0  # height on the page where the last header row was seen
    with pdfplumber.open(path) as pdf:
        if max_pages is not None and len(pdf.pages) > max_pages:
            raise TooManyPages(f"{len(pdf.pages)} pages, limit {max_pages}")
        for pno, page in enumerate(pdf.pages, start=1):
            carried = cols is not None  # columns came from an earlier page
            page = drop_rotated_text(page)
            decoded = decode_symbol_font(page.chars)
            words = page.extract_words(
                x_tolerance=1.5, y_tolerance=2, keep_blank_chars=False
            )
            if not words:
                # A scan or photo inside a PDF: no text to read. Say so instead of
                # returning nothing (the OCR path is not built yet).
                unparsed.append({"page": pno, "text": "", "reason": "no_text_layer"})
            for line in group_lines(words):
                text = " ".join(w["text"] for w in line)
                header = detect_header(line)
                if header:
                    cols, carried, table_top = header, False, line[0]["top"]
                    continue
                row, reason = (None, None)
                # Carried-over columns only apply below where the table began, so a
                # patient block above the table is not read as table rows.
                if cols and (not carried or line[0]["top"] >= table_top):
                    row, reason = parse_by_columns(line, cols, pno, text)
                if row is None and reason is None:
                    row, reason = parse_by_regex(text, pno)
                if row and decoded:
                    row.confidence = "low"
                    row.review_reason = "; ".join(
                        r for r in (row.review_reason, DECODED_REASON) if r
                    )
                if row:
                    rows.append(row)
                elif reason:
                    unparsed.append({"page": pno, "text": text, "reason": reason})
                elif NUM_RE.search(text) and UNIT_HINT.search(text):
                    unparsed.append(
                        {"page": pno, "text": text, "reason": "looks_like_result"}
                    )
    return {"file": str(path), "rows": [asdict(r) for r in rows], "unparsed": unparsed}


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract lab rows from a digital PDF")
    ap.add_argument("pdf")
    # Writing the file here keeps it UTF-8. Shell redirects on Windows change the
    # encoding and break characters such as "µ".
    ap.add_argument("--out", help="write JSON to this file instead of the screen")
    args = ap.parse_args()
    text = json.dumps(extract_pdf(args.pdf), indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)


if __name__ == "__main__":
    main()
