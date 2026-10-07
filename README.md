# Lab report extraction toolkit (first piece of the Indic Lab Report Explainer)

Reads a digital lab-report PDF, rebuilds its table rows from word positions,
computes low / normal / high with plain code, and scores the result against an
answer key. No AI model is involved in this part.

## Setup
    pip install -r requirements.txt

## Try it
    python -m tools.make_synthetic --out data/synthetic --per-template 5
    python -m tools.evaluate --pdf-dir data/synthetic/pdf --keys-dir data/synthetic/answer_keys
    python -m app.extract.pdf_rows some_report.pdf        # prints rows as JSON
    python -m pytest -q

## Use public sample reports (run on your own computer)
1. Edit `data/public_samples/sources.csv`. Set `terms_checked` to yes only after reading the site's terms.
2. `python -m tools.fetch_samples`  (downloads PDFs, writes `SOURCES.md` with URL, date and hash)
3. `python -m app.extract.pdf_rows data/public_samples/pdf/drlal_wm17s.pdf`
4. Write an answer key by hand for any file you want to score (same JSON format as `data/synthetic/answer_keys`).

## Output fields per row
name, value, unit, range_text, computed_flag (plain code), reported_flag (H/L if the lab
printed one), flag_mismatch, unit_check (ok / unexpected / unchecked), page, raw.
Lines that look like results but cannot be parsed are returned in `unparsed`.

## Known limits
- Digital PDFs only. Photos and scans need the OpenCV + OCR path (not built yet).
- One test per line. Side-by-side two-column layouts are not handled.
- Numeric results only. Values shown as chart images, or text like "Negative", are not read.
- Synthetic scores (100%) only show the code works on layouts the generator draws.
  They say nothing about real labs. Real-report numbers must be reported separately.
- Private reports go in `data/real_samples/` (git-ignored). Never commit them.
