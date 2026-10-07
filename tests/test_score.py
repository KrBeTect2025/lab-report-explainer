from app.eval.score import score_file


def _row(name, value, unit="g/dL", rng="13.0 - 17.0", flag="normal"):
    return {"name": name, "value": value, "unit": unit, "range_text": rng,
            "computed_flag": flag}


def _key(name, value, unit="g/dL", rng="13.0 - 17.0", flag="normal"):
    return {"name": name, "value": value, "unit": unit, "range": rng, "flag": flag}


def test_perfect_match():
    s = score_file([_row("Hemoglobin", 14.5)], [_key("Hemoglobin", 14.5)])
    assert s.correct == s.total and not s.errors


def test_wrong_decimal_is_caught():
    s = score_file([_row("Hemoglobin", 145.0)], [_key("Hemoglobin", 14.5)])
    assert s.correct["value"] == 0 and s.correct["name"] == 1


def test_missing_row_counts_as_wrong_everywhere():
    s = score_file([], [_key("Hemoglobin", 14.5)])
    assert all(s.correct[f] == 0 and s.total[f] == 1 for f in s.total)


def test_extra_row_is_reported():
    s = score_file([_row("Hemoglobin", 14.5), _row("Page", 1.0)], [_key("Hemoglobin", 14.5)])
    assert len(s.extra_rows) == 1
