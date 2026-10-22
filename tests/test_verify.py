import json
from pathlib import Path

import pytest

from app.extract.pdf_rows import make_row
from app.verify.facts import Entry, check_entry, verify

CASES = json.loads((Path(__file__).parent / "verifier_cases.json").read_text(encoding="utf-8"))


def _row(key):
    r = CASES["rows"][key]
    row = make_row(r["name"], None, r["value"], r["unit"], r["range_text"], 1, "synthetic")
    # The fixture states the flag itself, so a change in the flag code cannot quietly
    # turn a "wrong flag" case into a right one.
    assert row.computed_flag == r["flag"]
    return row


@pytest.mark.parametrize("case", CASES["accept"], ids=lambda c: f"{c['row']}: {c['why']}")
def test_correct_sentences_pass(case):
    assert check_entry(_row(case["row"]), case["text"]) == []


@pytest.mark.parametrize("case", CASES["reject"], ids=lambda c: f"{c['row']}: {c['kind']}")
def test_wrong_sentences_are_rejected_for_the_right_reason(case):
    assert case["code"] in check_entry(_row(case["row"]), case["text"])


def test_case_file_covers_every_required_kind():
    # Task 6 acceptance: these kinds of wrong sentence must all be present.
    codes = {c["code"] for c in CASES["reject"]}
    assert {"unknown_number", "wrong_unit", "flag_word_mismatch"} <= codes
    kinds = " ".join(c["kind"] for c in CASES["reject"])
    for kind in ("wrong number", "wrong unit", "wrong flag word", "flag stated on a normal value", "invented number"):
        assert kind in kinds


def _two_rows():
    return [_row("hb"), _row("mcv")]


def _good(i):
    return Entry(id=i, text=next(c["text"] for c in CASES["accept"] if c["row"] == ["hb", "mcv"][i]))


def test_every_row_needs_exactly_one_entry():
    rows = _two_rows()
    assert verify(rows, [_good(0), _good(1)]) == []
    assert verify(rows, [_good(0)]) == ["row 1: missing_entry"]
    assert "row 0: duplicate_entry" in verify(rows, [_good(0), _good(0), _good(1)])
    assert "entry 5: no_such_row" in verify(rows, [_good(0), _good(1), Entry(id=5, text="x")])


def test_entry_checked_against_its_own_row_only():
    # The mcv sentence is correct for mcv, but wrong when given the hemoglobin id.
    rows = _two_rows()
    assert verify(rows, [Entry(id=0, text=_good(1).text), Entry(id=1, text=_good(0).text)])


def test_problem_codes_never_contain_values():
    rows = _two_rows()
    bad = Entry(id=0, text="Your result is 99.9 g/dL.")
    for p in verify(rows, [bad, _good(1)]):
        assert "99.9" not in p and "11.2" not in p
