import pytest
from pydantic import ValidationError

from app.extract.pdf_rows import extract_pdf, make_row
from app.schema import Correction, Report, accept, correct, pending, reject, usable_rows


def _report():
    return Report(
        file="synthetic.pdf",
        rows=[
            make_row("Hemoglobin", None, "13.6", "g/dL", "13.0 - 17.0", 1, "Hemoglobin 13.6 g/dL 13.0 - 17.0"),
            # A heading ending in a year: low confidence (no unit, no range).
            make_row("Treatment Goals as per Lipid Association of India", None, "2020", "", "", 1, "..."),
        ],
    )


def test_low_confidence_row_is_excluded_until_accepted():
    rep = _report()
    assert pending(rep) == [1]
    assert [r.name for r in usable_rows(rep)] == ["Hemoglobin"]
    accept(rep, 1)
    assert pending(rep) == []
    assert len(usable_rows(rep)) == 2


def test_rejected_row_never_reaches_explanations():
    rep = _report()
    reject(rep, 0)
    reject(rep, 1)
    assert pending(rep) == [] and usable_rows(rep) == []


def test_correction_recomputes_flag_by_code():
    """A digit error (7.2 read as 72): the person fixes the value, code redoes the flag."""
    rep = Report(file="x", rows=[make_row("MCHC", "H", "72", "g/dL", "", 1, "raw")])
    assert pending(rep) == []  # unit present, so high confidence, but flag unknown
    correct(rep, 0, Correction(name="MCHC", value=7.2, unit="g/dL", range_text="31.5 - 34.5"))
    row = rep.rows[0]
    assert (row.value, row.computed_flag, row.status) == (7.2, "low", "corrected")
    assert row.flag_mismatch  # the lab printed H, code says low: still shown
    assert row in usable_rows(rep)


@pytest.mark.parametrize(
    "bad", [{"name": "", "value": 1}, {"name": "Hb", "value": float("nan")}, {"name": "Hb", "value": "abc"}]
)
def test_bad_corrections_are_refused(bad):
    with pytest.raises(ValidationError):
        Correction(**bad)


def test_extractor_output_fits_the_schema(tmp_path):
    from tools.make_synthetic import generate

    generate(str(tmp_path), per_template=1, seed=3)
    pdf = sorted((tmp_path / "pdf").glob("*.pdf"))[0]
    rep = Report.model_validate(extract_pdf(str(pdf)))
    assert rep.rows and all(r.status == "unreviewed" for r in rep.rows)
