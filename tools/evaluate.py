"""Run extraction on every PDF that has an answer key and print counts.

    python -m tools.evaluate --pdf-dir data/synthetic/pdf --keys-dir data/synthetic/answer_keys

Answer key file name must match the PDF: report1.pdf -> report1.json
Key format: {"rows": [{"name", "value", "unit", "range", "flag"}, ...]}
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.eval.score import FIELDS, Score, score_file
from app.extract.pdf_rows import extract_pdf


def evaluate(pdf_dir: str, keys_dir: str, verbose: bool = True) -> tuple[Score, list[dict]]:
    total = Score()
    all_unparsed = []
    for pdf in sorted(Path(pdf_dir).glob("*.pdf")):
        key_path = Path(keys_dir) / f"{pdf.stem}.json"
        if not key_path.exists():
            if verbose:
                print(f"skip {pdf.name}: no answer key")
            continue
        key = json.loads(key_path.read_text(encoding="utf-8"))
        if key.get("verified") is False:
            # A draft copies extractor output; scoring against it would be circular.
            print(f"skip {pdf.name}: draft key not verified by a person")
            continue
        result = extract_pdf(str(pdf))
        s = score_file(result["rows"], key["rows"], label=pdf.name)
        total.add(s)
        for u in result["unparsed"]:
            all_unparsed.append({"file": pdf.name, **u})
    return total, all_unparsed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--keys-dir", required=True)
    ap.add_argument("--show", type=int, default=15, help="max error lines to print")
    a = ap.parse_args()
    total, unparsed = evaluate(a.pdf_dir, a.keys_dir)
    print("\nField results (correct / total):")
    for f in FIELDS:
        c, t = total.correct[f], total.total[f]
        pct = f"{100 * c / t:.1f}%" if t else "n/a"
        print(f"  {f:<6} {c}/{t}  ({pct})")
    print(f"Extra rows (not in key): {len(total.extra_rows)}")
    print(f"Unparsed lines flagged for review: {len(unparsed)}")
    for line in (total.errors + total.extra_rows)[: a.show]:
        print("  -", line)
    for u in unparsed[: a.show]:
        print(f"  ? {u['file']} p{u['page']} [{u['reason']}] {u['text']}")


if __name__ == "__main__":
    main()
