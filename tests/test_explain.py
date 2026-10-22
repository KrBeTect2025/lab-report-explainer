import json
from types import SimpleNamespace

import pytest

from app.extract.pdf_rows import make_row
from app.llm.client import ClaudeClient, LLMError
from app.llm.explain import MAX_ATTEMPTS, build_payload, explain
from app.schema import Report

HB = "Hemoglobin carries oxygen in your blood. Your result is 11.2 g/dL. This is below the range printed on your report. Please discuss this with your doctor."
MCV = "MCV shows the average size of your red blood cells. Your result is 88 fL. This is within the range printed on your report."


def _report():
    rows = [
        make_row("Hemoglobin", "L", "11.2", "g/dL", "13.0 - 17.0", 1, "Hemoglobin L 11.2 g/dL 13.0 - 17.0 Ravi Kumar"),
        make_row("MCV", None, "88", "fL", "83 - 101", 1, "MCV 88 fL 83 - 101"),
    ]
    heading = make_row("Treatment Goals 2020", None, "2020", "", "", 2, "Treatment Goals 2020")
    assert heading.confidence == "low"  # stays out until a person decides
    return Report(file="upload.pdf", rows=rows + [heading])


def _answer(*texts):
    return json.dumps({"rows": [{"id": i, "text": t} for i, t in enumerate(texts)]})


class FakeLLM:
    """Returns canned answers in order and records what it was sent."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def complete(self, system, user, schema):
        self.calls.append(user)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def test_verified_text_is_returned_after_one_call():
    llm = FakeLLM(_answer(HB, MCV))
    out = explain(_report(), llm)
    assert (out.status, out.attempts, len(llm.calls)) == ("verified", 1, 1)
    assert [r.text for r in out.rows] == [HB, MCV]
    assert out.rows[0].flag == "low"  # flag comes from code, carried next to the text


def test_only_structured_fields_of_usable_rows_are_sent():
    llm = FakeLLM(_answer(HB, MCV))
    explain(_report(), llm)
    sent = json.loads(llm.calls[0])
    assert [r["name"] for r in sent] == ["Hemoglobin", "MCV"]  # low-confidence heading left out
    assert all(set(r) == {"id", "name", "value", "unit", "range", "flag"} for r in sent)
    assert "Ravi" not in llm.calls[0] and "upload.pdf" not in llm.calls[0]


def test_failed_verification_is_retried_once():
    wrong = HB.replace("11.2", "12.2")
    llm = FakeLLM(_answer(wrong, MCV), _answer(HB, MCV))
    out = explain(_report(), llm)
    assert (out.status, out.attempts) == ("verified", 2)


@pytest.mark.parametrize("bad", [
    _answer(HB.replace("below", "above"), MCV),  # wrong flag word
    _answer(HB),  # a row left out
    "this is not json",
    json.dumps({"rows": [{"id": 0, "text": HB}], "extra": 1}),
    LLMError("stop_reason:refusal"),
])
def test_two_failures_give_the_table_and_no_text(bad):
    llm = FakeLLM(bad, bad)
    out = explain(_report(), llm)
    assert out.status == "fallback" and out.rows == []
    assert len(llm.calls) == MAX_ATTEMPTS
    assert [(t.name, t.flag) for t in out.table] == [("Hemoglobin", "low"), ("MCV", "normal")]
    assert out.failure


def test_no_usable_rows_means_no_call():
    llm = FakeLLM()
    report = _report()
    for r in report.rows:
        r.status = "rejected"
    out = explain(report, llm)
    assert out.status == "fallback" and out.failure == ["no_usable_rows"] and not llm.calls


def test_payload_is_the_same_for_the_same_rows():
    rows = _report().rows[:2]
    assert build_payload(rows) == build_payload(rows)


# --- client wrapper, with a fake SDK object (no network) ---

def _sdk(stop_reason="end_turn", text='{"rows": []}'):
    calls = []

    def create(**kw):
        calls.append(kw)
        return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)])

    return SimpleNamespace(messages=SimpleNamespace(create=create)), calls


def test_model_name_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("CLAUDE_MODEL", "model-from-env")
    sdk, calls = _sdk()
    assert ClaudeClient(sdk=sdk).complete("sys", "user", {"type": "object"}) == '{"rows": []}'
    assert calls[0]["model"] == "model-from-env" and calls[0]["system"] == "sys"
    assert calls[0]["output_config"]["format"]["schema"] == {"type": "object"}


def test_missing_model_name_is_an_error(monkeypatch):
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    with pytest.raises(LLMError):
        ClaudeClient(sdk=_sdk()[0])


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_refused_or_cut_off_answers_are_errors(monkeypatch, stop):
    monkeypatch.setenv("CLAUDE_MODEL", "m")
    with pytest.raises(LLMError, match=stop):
        ClaudeClient(sdk=_sdk(stop_reason=stop)[0]).complete("s", "u", {})
