"""Extracted report schema and the confirmation step.

Rows the extractor is unsure about (confidence "low") stay out of explanations until a
person accepts or corrects them. A person may also correct or reject any other row.

A correction gives only what is printed on the report (name, value, unit, range). The
flag is always recomputed by code from the range; nobody types a flag in.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.extract.pdf_rows import Row, make_row


class Unparsed(BaseModel):
    page: int
    text: str
    reason: str


class Report(BaseModel):
    file: str
    rows: list[Row]
    unparsed: list[Unparsed] = []


class Correction(BaseModel):
    name: str = Field(min_length=1)
    value: float = Field(allow_inf_nan=False)
    unit: str = ""
    range_text: str = ""


def needs_review(row: Row) -> bool:
    return row.confidence == "low" and row.status == "unreviewed"


def pending(report: Report) -> list[int]:
    """Indexes of rows a person still has to accept, correct or reject."""
    return [i for i, r in enumerate(report.rows) if needs_review(r)]


def accept(report: Report, i: int) -> None:
    report.rows[i].status = "confirmed"


def reject(report: Report, i: int) -> None:
    """For lines that are not results, for example a heading read as a row."""
    report.rows[i].status = "rejected"


def correct(report: Report, i: int, fix: Correction) -> None:
    old = report.rows[i]
    # make_row recomputes flag, lab-flag mismatch and unit check by plain code.
    # The lab's own H/L is kept, so a corrected value that disagrees with it still shows.
    new = make_row(
        fix.name, old.reported_flag, repr(fix.value), fix.unit, fix.range_text,
        old.page, old.raw,
    )
    new.status = "corrected"
    report.rows[i] = new


def usable_rows(report: Report) -> list[Row]:
    """Rows allowed into an explanation."""
    return [
        r for r in report.rows
        if r.status in ("confirmed", "corrected")
        or (r.status == "unreviewed" and r.confidence == "high")
    ]
