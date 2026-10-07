import pytest

from app.rules.ranges import Range, flag_value, parse_range
from app.rules.sanity import check_unit


@pytest.mark.parametrize(
    "text,expected",
    [
        ("13.0 - 17.0", Range(13.0, 17.0)),
        ("13.0-17.0", Range(13.0, 17.0)),
        ("4.00 – 5.60", Range(4.0, 5.6)),  # en dash
        ("1,50,000 - 4,10,000", Range(150000.0, 410000.0)),  # Indian grouping
        ("<5.7", Range(high=5.7, high_inclusive=False)),
        ("< 200.00 mg/dL", Range(high=200.0, high_inclusive=False)),
        ("<=2", Range(high=2.0, high_inclusive=True)),
        (">40", Range(low=40.0, low_inclusive=False)),
        ("up to 200", Range(high=200.0, high_inclusive=True)),
    ],
)
def test_parse_range(text, expected):
    assert parse_range(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        None,
        "2 0 - 5.10",  # typo seen in a real sample report
        "Desirable : <200 Borderline : 200-239",  # several bands, refuse to guess
        "17 - 13",  # reversed
        "Negative",
    ],
)
def test_unparseable_ranges_return_none(text):
    assert parse_range(text) is None


def test_flags_at_boundaries():
    r = parse_range("13.0 - 17.0")
    assert flag_value(13.0, r) == "normal"  # inclusive
    assert flag_value(17.0, r) == "normal"
    assert flag_value(12.9, r) == "low"
    assert flag_value(17.1, r) == "high"


def test_one_sided_ranges_are_strict():
    assert flag_value(200, parse_range("<200")) == "high"
    assert flag_value(199, parse_range("<200")) == "normal"
    assert flag_value(40, parse_range(">40")) == "low"
    assert flag_value(41, parse_range(">40")) == "normal"


def test_unknown_when_no_range():
    assert flag_value(5.0, None) == "unknown"


def test_unit_sanity_catches_the_g_per_l_trap():
    assert check_unit("Hemoglobin (Photometry)", "g/L") == "unexpected"
    assert check_unit("Hemoglobin", "g/dL") == "ok"
    assert check_unit("Some Rare Test", "xyz") == "unchecked"


def test_unit_aliases_seen_on_real_reports():
    assert check_unit("LDL Cholesterol, Calculated", "mg/dL") == "ok"
    assert check_unit("Red Cell Distribution Width (RDW)", "%") == "ok"
    assert check_unit("T4, Total", "µg/dL") == "ok"
    assert check_unit("TSH", "µIU/mL") == "ok"
    assert check_unit("Sodium", "mg/L") == "unexpected"
