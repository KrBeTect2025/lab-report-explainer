"""Generate fake lab-report PDFs with answer keys.

Three layouts:
  A  bordered table, header row, "H"/"L" flags printed inside the result cell
  B  header row, range column BEFORE the unit column, right-aligned results
  C  no header row, no borders, Indian digit grouping (1,50,000)

Every PDF gets a JSON answer key. The key's flag is computed here, with its own
simple logic, and NOT with app.rules, so the extractor is not marked by itself.

All patients are fake. Usage:
    python -m tools.make_synthetic --out data/synthetic --per-template 5
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# panel, name, unit, low, high, decimals
TESTS = [
    ("COMPLETE BLOOD COUNT", "Hemoglobin", "g/dL", 13.0, 17.0, 1),
    ("COMPLETE BLOOD COUNT", "RBC Count", "million/cmm", 4.5, 5.5, 2),
    ("COMPLETE BLOOD COUNT", "Packed Cell Volume (PCV)", "%", 40.0, 50.0, 1),
    ("COMPLETE BLOOD COUNT", "MCV", "fL", 83.0, 101.0, 1),
    ("COMPLETE BLOOD COUNT", "MCH", "pg", 27.0, 32.0, 1),
    ("COMPLETE BLOOD COUNT", "MCHC", "g/dL", 31.5, 34.5, 1),
    ("COMPLETE BLOOD COUNT", "RDW", "%", 11.6, 14.0, 1),
    ("COMPLETE BLOOD COUNT", "Total Leucocyte Count (TLC)", "/cmm", 4000, 10000, 0),
    ("COMPLETE BLOOD COUNT", "Neutrophils", "%", 40, 80, 0),
    ("COMPLETE BLOOD COUNT", "Lymphocytes", "%", 20, 40, 0),
    ("COMPLETE BLOOD COUNT", "Platelet Count", "/cmm", 150000, 410000, 0),
    ("COMPLETE BLOOD COUNT", "Lymphocytes", "/cmm", 1000, 3000, 0),  # repeated name
    ("LIPID PROFILE", "Cholesterol, Total", "mg/dL", None, 200, 0),
    ("LIPID PROFILE", "Triglycerides", "mg/dL", None, 150, 0),
    ("LIPID PROFILE", "HDL Cholesterol", "mg/dL", 40, None, 0),
    ("LIPID PROFILE", "LDL Cholesterol", "mg/dL", None, 100, 0),
    ("THYROID PROFILE", "T3, Total", "ng/dL", 80, 200, 0),
    ("THYROID PROFILE", "T4, Total", "ug/dL", 4.5, 12.5, 1),
    ("THYROID PROFILE", "TSH", "uIU/mL", 0.35, 5.5, 2),
    ("DIABETES", "HbA1c", "%", 4.0, 5.6, 1),
]
EXTRA_PANELS = ["LIPID PROFILE", "THYROID PROFILE", "DIABETES"]
ROWS_PER_PAGE = 16


def indian(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def fmt(x, dec: int, grouping: bool) -> str:
    if dec == 0:
        n = int(round(x))
        return indian(n) if grouping and n >= 1000 else str(n)
    return f"{x:.{dec}f}"


def gen_value(rnd: random.Random, low, high, dec: int, abnormal: bool):
    if low is not None and high is not None:
        width = high - low
        if not abnormal:
            v = rnd.uniform(low + 0.05 * width, high - 0.05 * width)
        elif rnd.random() < 0.5:
            v = low - rnd.uniform(0.05, 0.3) * width
        else:
            v = high + rnd.uniform(0.05, 0.3) * width
    elif high is not None:
        v = rnd.uniform(1.05 * high, 1.5 * high) if abnormal else rnd.uniform(0.5 * high, 0.95 * high)
    else:
        v = rnd.uniform(0.6 * low, 0.95 * low) if abnormal else rnd.uniform(1.1 * low, 1.7 * low)
    v = max(v, 0.01)
    return int(round(v)) if dec == 0 else round(v, dec)


def truth_flag(v, low, high) -> str:
    """Independent ground truth. Two-sided ranges are inclusive, one-sided are strict."""
    if low is not None and high is not None:
        return "low" if v < low else "high" if v > high else "normal"
    if high is not None:
        return "high" if v >= high else "normal"
    return "low" if v <= low else "normal"


def range_text(low, high, dec: int, grouping: bool) -> str:
    if low is not None and high is not None:
        return f"{fmt(low, dec, grouping)} - {fmt(high, dec, grouping)}"
    if high is not None:
        return f"<{fmt(high, dec, grouping)}"
    return f">{fmt(low, dec, grouping)}"


def build_rows(rnd: random.Random, template: str) -> list[dict]:
    grouping = template == "C"
    panels = ["COMPLETE BLOOD COUNT", rnd.choice(EXTRA_PANELS)]
    rows = []
    for panel, name, unit, low, high, dec in TESTS:
        if panel not in panels:
            continue
        v = gen_value(rnd, low, high, dec, abnormal=rnd.random() < 0.3)
        rows.append(
            {
                "panel": panel,
                "name": name,
                "unit": unit,
                "value": float(v),
                "value_text": fmt(v, dec, grouping),
                "range": range_text(low, high, dec, grouping),
                "flag": truth_flag(v, low, high),
            }
        )
    return rows


def paginate(rows: list[dict]) -> list[list[dict]]:
    """Insert panel headings, then split into pages."""
    lines, last = [], None
    for r in rows:
        if r["panel"] != last:
            lines.append({"heading": r["panel"]})
            last = r["panel"]
        lines.append(r)
    return [lines[i : i + ROWS_PER_PAGE] for i in range(0, len(lines), ROWS_PER_PAGE)]


def frame(c, patient: dict, page: int, pages: int) -> None:
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, 800, "SYNTHETIC DIAGNOSTICS LAB")
    c.setFont("Helvetica", 9)
    c.drawString(40, 782, f"Name : {patient['name']}")
    c.drawString(300, 782, f"Age / Sex : {patient['age']} Y / {patient['sex']}")
    c.drawString(40, 768, f"Lab No : {patient['lab_no']}")
    c.drawString(300, 768, f"Collected : {patient['collected']}")
    c.drawString(40, 754, "Report Status : Final")
    c.drawString(40, 40, f"Page {page} of {pages}")
    c.drawString(40, 28, "Test results may show interlaboratory variations. Helpline 011 4988 5050")


def draw(path: Path, template: str, patient: dict, rows: list[dict]) -> None:
    pages = paginate(rows)
    c = canvas.Canvas(str(path), pagesize=A4)
    for pno, lines in enumerate(pages, start=1):
        frame(c, patient, pno, len(pages))
        y = 722
        if template == "A":
            xs = {"name": 40, "value": 270, "unit": 345, "range": 425}
            c.setFont("Helvetica-Bold", 9)
            for label, key in (("Test Name", "name"), ("Result", "value"), ("Unit", "unit"), ("Reference Range", "range")):
                c.drawString(xs[key], y, label)
            c.line(36, y - 6, 560, y - 6)
            y -= 24
        elif template == "B":
            c.setFont("Helvetica-Bold", 9)
            c.drawString(40, y, "Investigation")
            c.drawString(280, y, "Result")
            c.drawString(350, y, "Biological Ref. Interval")
            c.drawString(480, y, "Units")
            y -= 24
        else:
            c.setFont("Helvetica", 9)
            c.drawString(40, y, "Sample collected 12/03/2024 08:15, received 12/03/2024 09:40")
            y -= 24
        for item in lines:
            if "heading" in item:
                c.setFont("Helvetica-Bold", 10)
                c.drawString(40, y, item["heading"])
            else:
                c.setFont("Helvetica", 9)
                if template == "A":
                    flag = {"high": "H ", "low": "L "}.get(item["flag"], "")
                    c.drawString(40, y, item["name"])
                    c.drawString(270, y, flag + item["value_text"])
                    c.drawString(345, y, item["unit"])
                    c.drawString(425, y, item["range"])
                    c.line(36, y - 6, 560, y - 6)
                elif template == "B":
                    c.drawString(40, y, item["name"])
                    c.drawRightString(335, y, item["value_text"])
                    c.drawString(350, y, item["range"])
                    c.drawString(480, y, item["unit"])
                else:
                    c.drawString(40, y, item["name"])
                    c.drawString(280, y, item["value_text"])
                    c.drawString(335, y, item["unit"])
                    c.drawString(420, y, item["range"])
            y -= 22
        c.showPage()
    c.save()


def generate(out_dir: str, per_template: int = 5, seed: int = 7) -> int:
    rnd = random.Random(seed)
    pdf_dir = Path(out_dir) / "pdf"
    key_dir = Path(out_dir) / "answer_keys"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    key_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for template in "ABC":
        for i in range(1, per_template + 1):
            stem = f"syn_{template}_{i:03d}"
            patient = {
                "name": "SYNTHETIC PATIENT",
                "age": rnd.randint(18, 70),
                "sex": rnd.choice(["Male", "Female"]),
                "lab_no": f"SYN-{template}{i:04d}",
                "collected": "12/03/2024 08:15",
            }
            rows = build_rows(rnd, template)
            draw(pdf_dir / f"{stem}.pdf", template, patient, rows)
            key = {
                "file": f"{stem}.pdf",
                "template": template,
                "rows": [
                    {k: r[k] for k in ("name", "value", "unit", "range", "flag")} for r in rows
                ],
            }
            (key_dir / f"{stem}.json").write_text(json.dumps(key, indent=2))
            count += 1
    return count


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/synthetic")
    ap.add_argument("--per-template", type=int, default=5)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    print(f"wrote {generate(a.out, a.per_template, a.seed)} reports to {a.out}")
