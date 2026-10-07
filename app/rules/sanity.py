"""Unit sanity checks.

Catches reports (or extraction mistakes) where a unit does not fit the test,
for example hemoglobin printed in g/L. The result is "ok", "unexpected" or
"unchecked" (the test is not in the table, so nothing is claimed).
"""
from __future__ import annotations

from app.rules.names import normalize_name

_EXPECTED_UNITS = {
    "hemoglobin": {"g/dl"},
    "haemoglobin": {"g/dl"},
    "hb": {"g/dl"},
    "mcv": {"fl"},
    "mch": {"pg"},
    "mchc": {"g/dl", "%"},
    "packed cell volume": {"%"},
    "pcv": {"%"},
    "rdw": {"%"},
    "cholesterol total": {"mg/dl", "mmol/l"},
    "triglycerides": {"mg/dl", "mmol/l"},
    "hdl cholesterol": {"mg/dl", "mmol/l"},
    "ldl cholesterol": {"mg/dl", "mmol/l"},
    "tsh": {"uiu/ml", "miu/l", "mu/l"},  # mU/L is the same unit (seen on drlogy_thyroid)
    "hba1c": {"%", "mmol/mol"},
    # names as printed on real reports (method words kept in the name)
    "ldl cholesterol calculated": {"mg/dl", "mmol/l"},
    "ldl cholesterol direct": {"mg/dl", "mmol/l"},
    "vldl cholesterol calculated": {"mg/dl", "mmol/l"},
    "non hdl cholesterol": {"mg/dl", "mmol/l"},
    "red cell distribution width": {"%"},
    "mean platelet volume": {"fl"},
    "creatinine": {"mg/dl", "umol/l"},
    "urea": {"mg/dl", "mmol/l"},
    "uric acid": {"mg/dl", "umol/l"},
    "total protein": {"g/dl", "g/l"},
    "albumin": {"g/dl", "g/l"},
    "sodium": {"meq/l", "mmol/l"},
    "potassium": {"meq/l", "mmol/l"},
    "chloride": {"meq/l", "mmol/l"},
    "calcium total": {"mg/dl", "mmol/l"},
    "glucose fasting": {"mg/dl", "mmol/l"},
    "t3 total": {"ng/dl", "ng/ml", "nmol/l"},
    "t4 total": {"ug/dl", "nmol/l"},
}


def normalize_unit(unit: str) -> str:
    u = unit.lower().replace(" ", "")
    u = u.replace("µ", "u").replace("μ", "u")  # micro signs
    return u.replace("gm/", "g/").replace("mcg/", "ug/")


def check_unit(test_name: str, unit: str) -> str:
    expected = _EXPECTED_UNITS.get(normalize_name(test_name))
    if expected is None:
        return "unchecked"
    return "ok" if normalize_unit(unit) in expected else "unexpected"
