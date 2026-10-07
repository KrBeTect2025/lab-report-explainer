import json
from pathlib import Path

from app.eval.score import FIELDS, score_file
from app.extract.pdf_rows import extract_pdf
from tools.make_synthetic import generate


def test_synthetic_reports_extract_perfectly_and_without_noise(tmp_path):
    n = generate(str(tmp_path), per_template=3, seed=11)
    assert n == 9
    for pdf in sorted((tmp_path / "pdf").glob("*.pdf")):
        key = json.loads((tmp_path / "answer_keys" / f"{pdf.stem}.json").read_text())
        result = extract_pdf(str(pdf))
        s = score_file(result["rows"], key["rows"], label=pdf.name)
        for f in FIELDS:
            assert s.correct[f] == s.total[f], (pdf.name, s.errors[:5])
        assert not s.extra_rows, (pdf.name, s.extra_rows)  # no footer text as rows
        assert not result["unparsed"], (pdf.name, result["unparsed"])


def test_repeated_test_names_are_kept_apart(tmp_path):
    generate(str(tmp_path), per_template=1, seed=3)
    result = extract_pdf(str(tmp_path / "pdf" / "syn_A_001.pdf"))
    lymph = [r for r in result["rows"] if r["name"] == "Lymphocytes"]
    assert [r["unit"] for r in lymph] == ["%", "/cmm"]


def test_lab_flag_disagreement_is_detected(tmp_path):
    generate(str(tmp_path), per_template=1, seed=3)
    rows = extract_pdf(str(tmp_path / "pdf" / "syn_A_001.pdf"))["rows"]
    # Template A prints H/L flags itself; they must agree with the plain-code flag.
    assert not any(r["flag_mismatch"] for r in rows)
    assert any(r["reported_flag"] for r in rows)


def test_column_by_column_drawing_order_still_pairs_rows(tmp_path):
    """Some PDFs store all names first, then all values. Rows must still line up."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    data = [
        ("Creatinine", "1.00", "mg/dL", "0.70 - 1.30"),
        ("Urea", "40.00", "mg/dL", "13.00 - 43.00"),
        ("Uric Acid", "7.00", "mg/dL", "3.50 - 7.20"),
        ("Albumin", "4.00", "g/dL", "3.20 - 4.80"),
    ]
    path = tmp_path / "scrambled.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica", 9)
    y0 = 700
    for x, label in ((40, "Test Name"), (270, "Results"), (345, "Units"), (425, "Bio. Ref. Interval")):
        c.drawString(x, y0, label)
    for x, idx in ((40, 0), (270, 1), (345, 2), (425, 3)):  # one column at a time
        for i, row in enumerate(data):
            c.drawString(x, y0 - 22 * (i + 1), row[idx])
    c.save()

    rows = extract_pdf(str(path))["rows"]
    assert [(r["name"], r["value"], r["unit"], r["range_text"]) for r in rows] == [
        (n, float(v), u, rg) for n, v, u, rg in data
    ]


def _table_pdf(path, rows, extra=None):
    """Small helper: header + rows (name, value, unit, range); extra = loose text items."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica", 9)
    y0 = 700
    for x, label in ((40, "Test Name"), (270, "Results"), (345, "Units"), (425, "Bio. Ref. Interval")):
        c.drawString(x, y0, label)
    y = y0 - 22
    for name, value, unit, rng in rows:
        c.drawString(40, y, name)
        c.drawString(270, y, value)
        c.drawString(345, y, unit)
        c.drawString(425, y, rng)
        y -= 22
    for x, text in extra or []:
        c.drawString(x, y, text)
    c.save()


def test_heading_ending_in_a_year_is_marked_low_confidence(tmp_path):
    """Seen on a real report: 'Treatment Goals ... Lipid Association of India 2020'."""
    path = tmp_path / "heading.pdf"
    _table_pdf(
        path,
        [("Creatinine", "1.00", "mg/dL", "0.70 - 1.30")],
        extra=[(40, "Treatment Goals as per Lipid Association of India"), (270, "2020")],
    )
    rows = {r["name"]: r for r in extract_pdf(str(path))["rows"]}
    assert rows["Creatinine"]["confidence"] == "high"
    bad = rows["Treatment Goals as per Lipid Association of India"]
    assert bad["confidence"] == "low" and bad["review_reason"]


def test_row_without_unit_or_range_needs_confirmation(tmp_path):
    path = tmp_path / "ratio.pdf"
    _table_pdf(path, [("BUN/Creatinine Ratio", "19", "", "")])
    row = extract_pdf(str(path))["rows"][0]
    assert row["confidence"] == "low"  # a person must confirm it before it is used
    assert row["computed_flag"] == "unknown"


def _custom_pdf(path, header, rows, after_draw=None):
    """header and each row: list of (x, text). after_draw(canvas) adds extra marks."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica", 9)
    y = 700
    for cells in [header, *rows]:
        for x, text in cells:
            c.drawString(x, y, text)
        y -= 22
    if after_draw:
        after_draw(c)
    c.save()


def test_method_column_is_kept_out_of_the_range(tmp_path):
    """Seen on hod_pk0016: 'Method' text joined the range, so every flag was unknown."""
    path = tmp_path / "method.pdf"
    _custom_pdf(
        path,
        [(40, "Observation"), (220, "Result"), (265, "Unit"), (320, "Biological Ref. Interval"), (445, "Method")],
        [[(40, "Hemoglobin"), (220, "13.6"), (265, "gm/dL"), (320, "13.0 - 17.0"), (445, "Photometric Measurement")]],
    )
    row = extract_pdf(str(path))["rows"][0]
    assert (row["range_text"], row["computed_flag"]) == ("13.0 - 17.0", "normal")


def test_rotated_watermark_letters_do_not_enter_cells(tmp_path):
    """Seen on hod_pk0016: a diagonal 'Sample Report' watermark turned 55.5 into 'a55.5'."""

    def watermark(c):
        c.saveState()
        c.setFont("Helvetica", 55)
        c.setFillGray(0.8)
        c.translate(190, 633)  # merges with the first result into "a55.5"
        c.rotate(45)
        c.drawString(0, 0, "a")
        c.restoreState()

    path = tmp_path / "watermark.pdf"
    _custom_pdf(
        path,
        [(40, "Observation"), (220, "Result"), (265, "Unit"), (320, "Biological Ref. Interval")],
        [[(40, "RDW-SD"), (220, "55.5"), (265, "fL"), (320, "39 - 46")]],
        after_draw=watermark,
    )
    result = extract_pdf(str(path))
    assert [(r["value"], r["range_text"]) for r in result["rows"]] == [(55.5, "39 - 46")]
    assert not result["unparsed"]


def test_word_flag_after_value_and_range_before_unit(tmp_path):
    """Seen on drlogy_thyroid: '150.00 Normal 80.00 - 200.00 ng/dL'."""
    path = tmp_path / "wordflag.pdf"
    _custom_pdf(
        path,
        [(40, "Investigation"), (200, "Result"), (320, "Reference Value"), (450, "Unit")],
        [
            [(40, "T3, TOTAL"), (200, "150.00"), (250, "Normal"), (320, "80.00 - 200.00"), (450, "ng/dL")],
            [(40, "TSH"), (200, "5.10"), (250, "Normal"), (320, "0.40 - 4.00"), (450, "mU/L")],
        ],
    )
    t3, tsh = extract_pdf(str(path))["rows"]
    assert (t3["value"], t3["unit"], t3["reported_flag"], t3["flag_mismatch"]) == (150.0, "ng/dL", "N", False)
    # The lab says Normal but the value is above its own printed range: must be caught.
    assert (tsh["computed_flag"], tsh["flag_mismatch"]) == ("high", True)
    assert tsh["unit_check"] == "ok"


def test_symbol_font_text_is_decoded_only_when_most_of_the_page_uses_it():
    """Seen on drlal_z615: every character stored as U+F000 + ASCII."""
    from app.extract.pdf_rows import decode_symbol_font

    page = [{"text": chr(0xF000 + ord(ch))} for ch in "TSH 2.5 mg/dL"]
    assert decode_symbol_font(page)
    assert "".join(c["text"] for c in page) == "TSH 2.5 mg/dL"

    # One Symbol-font micro sign (U+F06D) in normal text must not become "m".
    mixed = [{"text": ch} for ch in "T4 7.0 "] + [{"text": ""}] + [{"text": ch} for ch in "g/dL"]
    assert not decode_symbol_font(mixed)
    assert mixed[7]["text"] == ""
