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

## Explanations (LLM part)
Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY` and `CLAUDE_MODEL`. Then
`POST /reports/{token}/explain` asks Claude for a plain-English explanation of each row.

- Only the test name, value, unit, printed range and code-computed flag are sent. Never
  the file, names, ages, IDs or the raw report lines.
- Code checks every sentence before it is shown: each number must be that row's value or
  a number from its printed range, the unit must match, the low / normal / high words must
  match the code flag, and every low or high value must end with "please discuss this
  with your doctor". If the check fails twice, no text is shown, only the values table.
- "Likely causes" are not generated yet. When they are, they will not be verifiable
  against the report, and this README will say so.

## Known limits
- Digital PDFs only. Photos and scans need the OpenCV + OCR path (not built yet).
- One test per line. Side-by-side two-column layouts are not handled.
- Numeric results only. Values shown as chart images, or text like "Negative", are not read.
- Synthetic scores (100%) only show the code works on layouts the generator draws.
  They say nothing about real labs. Real-report numbers must be reported separately.
- Private reports go in `data/real_samples/` (git-ignored). Never commit them.
