"""Write a DRAFT answer key from extraction output, for a person to check.

    python -m tools.draft_key data\\public_samples\\pdf\\hod_pk0016.pdf

A draft copies what the extractor read, so scoring against it unchecked would prove
nothing (the extractor would agree with itself). To stop that, the key is written
with "verified": false and tools.evaluate refuses to score it. The owner checks every
line against the PDF, fixes mistakes, adds missed rows, deletes non-results, and
only then sets "verified": true.

Allowed only for development files (see CLAUDE.md section 9).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.extract.pdf_rows import extract_pdf

WARNING = (
    "DRAFT made from extraction output. Check EVERY line against the PDF: name, value, "
    "unit, range exactly as printed, and flag worked out by hand from the printed range "
    "(low / normal / high, or unknown if the range cannot be read). Add result rows the "
    "extractor missed (see unparsed_to_review and the PDF itself). Delete rows that are "
    "not results. Remove the review_hint fields. Then set verified to true."
)


def draft_key(pdf_path: str) -> dict:
    result = extract_pdf(pdf_path)
    rows = []
    for r in result["rows"]:
        row = {
            "name": r["name"],
            "value": r["value"],
            "unit": r["unit"],
            "range": r["range_text"],
            "flag": r["computed_flag"],
            "page": r["page"],
        }
        if r["confidence"] == "low":
            row["review_hint"] = f"low confidence: {r['review_reason']}"
        rows.append(row)
    return {
        "verified": False,
        "warning": WARNING,
        "source_pdf": Path(pdf_path).name,
        "rows": rows,
        "unparsed_to_review": result["unparsed"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Write a draft answer key to check by hand")
    ap.add_argument("pdf")
    ap.add_argument("--keys-dir", default="data/public_samples/answer_keys")
    a = ap.parse_args()
    out = Path(a.keys_dir) / f"{Path(a.pdf).stem}.json"
    if out.exists():
        # It may already be hand-checked; overwriting would lose that work.
        raise SystemExit(f"refusing to overwrite {out}; delete it first if you mean to")
    key = draft_key(a.pdf)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(key, indent=2, ensure_ascii=False), encoding="utf-8")
    low = sum("review_hint" in r for r in key["rows"])
    print(f"wrote {out}: {len(key['rows'])} rows ({low} low confidence), "
          f"{len(key['unparsed_to_review'])} unparsed lines")
    print("WARNING:", WARNING)


if __name__ == "__main__":
    main()
