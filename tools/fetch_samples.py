"""Download public sample reports listed in a CSV and write SOURCES.md.

Run this on your own computer (it needs normal internet access).

    python -m tools.fetch_samples --csv data/public_samples/sources.csv

CSV columns: id, lab, url, terms_checked, notes
It skips files that already exist, records a SHA-256 hash of each file, and
rewrites SOURCES.md so every file has its source and the date you fetched it.
Setting terms_checked to "yes" is YOUR statement that you read the site's terms.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import urllib.request
from datetime import date
from pathlib import Path

UA = "Mozilla/5.0 (lab-report-explainer research; contact: project owner)"


def fetch(url: str, dest: Path) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    if not data.startswith(b"%PDF"):
        raise ValueError("not a PDF (does not start with %PDF)")
    dest.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="data/public_samples/sources.csv")
    ap.add_argument("--out", default="data/public_samples")
    a = ap.parse_args()

    out = Path(a.out)
    pdf_dir = out / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Sources of public sample reports",
        "",
        "Files are used privately for layout and extraction testing only.",
        "They are not redistributed. Check each site's terms before any other use.",
        "",
        "| id | lab | url | fetched | terms checked | sha256 | notes |",
        "|---|---|---|---|---|---|---|",
    ]
    with open(a.csv, newline="") as fh:
        for row in csv.DictReader(fh):
            dest = pdf_dir / f"{row['id']}.pdf"
            status, digest = date.today().isoformat(), ""
            try:
                if dest.exists():
                    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
                    status = "already had"
                else:
                    digest = fetch(row["url"], dest)
            except Exception as exc:  # report and continue with the other files
                status = f"FAILED: {exc}"
            print(f"{row['id']}: {status}")
            lines.append(
                f"| {row['id']} | {row['lab']} | {row['url']} | {status} | "
                f"{row.get('terms_checked', 'no')} | {digest[:12]} | {row.get('notes', '')} |"
            )
    (out / "SOURCES.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {out / 'SOURCES.md'}")


if __name__ == "__main__":
    main()
