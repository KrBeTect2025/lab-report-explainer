# CLAUDE.md: Indic Lab Report Explainer

Read this file fully before changing anything. Then read `docs/plan.md` (the full plan,
schedule, and safety wording). When this file and a chat message disagree, ask the owner.

## 1. Working with the owner

- The owner is a data architect learning backend engineering. Goal: backend systems that
  serve ML/LLM features through their own API. This project is for a CV and hackathons.
- When explaining, teach from scratch: short pieces, plain words, one small example. Do not
  assume prior knowledge of Python internals, PDFs, or web APIs.
- Be critical about decisions. If a requested approach is risky or weak, say so plainly,
  give the reason and a better option, then do what the owner decides.
- Never use emojis in any reply, code comment, commit message, or file.
- Do the coding work here. Do not turn a coding task into a long essay. After a task: what
  changed, what you tested, what is still unproven, one next step.
- Do not expand scope silently. If a task needs something not listed here, stop and ask.
- Research (dataset hunting, reading sources, writing the glossary text, planning) happens in
  the owner's claude.ai chat. Results arrive as files in `docs/research/`. Treat them as
  input, check them, and cite their sources in code or data files.

## 2. What the product is

A web service. A user uploads a lab report (PDF first, photo later). The service extracts the
test rows, flags each as low / normal / high using plain code, has an LLM write a plain,
simple explanation in English, Hindi (Devanagari) or Hinglish (Roman script), verifies every
claim against the extracted values, and returns text plus a downloadable PDF.

The selling point is the verification layer. Numbers, units and flags in the text are
checked by code against the report. Nothing unverified reaches the user.

## 3. Hard rules (never break these)

Safety
1. No diagnosis, no treatment, no medicine, supplement or dose advice.
2. Never write "you have X". Use wording like "this value is above the range printed on your
   report; please discuss it with your doctor".
3. Use the reference range printed on the report. Never substitute a generic range.
4. Every abnormal value ends with "please discuss this with your doctor". Every screen and
   PDF carries the safety disclaimer.
5. The owner chose to include LLM-written "likely causes" for abnormal values. Controls:
   only for values flagged low/high by code; hedged wording only ("can be associated
   with"); no named disease as the explanation for this person; lead with common non-disease
   factors (diet, hydration, altitude, medicines, recent illness); no serious-disease lists;
   no treatment. Causes are NOT verified against the report, so the README must say that.

Correctness
6. Flags (low / normal / high) are computed by code in `app/rules/`. An LLM never decides a
   flag, a number, a unit or a range.
7. Never guess. Unreadable range -> flag "unknown". Row that might be a heading or note ->
   `confidence="low"`, shown to the user for confirmation, excluded from explanations until
   confirmed. Lines that look like results but cannot be parsed go in `unparsed`.
8. Unverified text never reaches the user. If verification fails: retry generation once; if
   it fails again, show only the extracted values table with code-computed flags and the
   disclaimer. Log the failure reason without personal data.

Privacy and data
9. Only structured values (test name, value, unit, printed range, flag) are sent to the
   hosted LLM. Never the raw file, never names, ages, IDs, phone numbers, addresses.
10. Never commit: `data/real_samples/`, `data/public_samples/pdf/`, `.env`, API keys.
    `.gitignore` already lists them. Check before every commit.
11. Uploaded reports, extracted values and generated PDFs are deleted automatically after
    24 hours. No user accounts. Results are reached by a long random token. Users can delete
    their data at any time. A consent screen comes before upload.
12. Do not print, log or put into test fixtures any real patient detail. Test data is
    synthetic or redacted.

## 4. Locked decisions

| Topic | Decision |
|---|---|
| Output languages | Plain simple English, Hindi (Devanagari, test names kept in English), Hinglish. User picks one. Build English first, then Hindi, then Hinglish. |
| Report types | CBC first, then lipid profile, then thyroid profile. Finish one fully before starting the next. |
| LLM | Claude API, hosted, official `anthropic` SDK. Model name from the env var `CLAUDE_MODEL`, never hard-coded. API key from `.env`. Check docs.claude.com for current SDK usage and model names. |
| Prompts | Versioned files in `prompts/` (for example `explain_en_v1.md`). They are API system prompts, not Claude app skills. A prompt only requests behaviour; code enforces it. |
| Verifier | Layer 1 (required, code): every number in the text must exist in the structured data; units and low/normal/high words must match the code flag for that test. Layer 2 (extra, narrow LLM check): returns a fixed JSON verdict for invented claims, certain-cause wording, treatment advice, diagnostic phrasing. Unparseable verdict = reject. |
| Extraction | Digital PDF: read words with positions (pdfplumber). Photo or scan: OpenCV cleanup, then an OCR engine chosen by a bake-off (Tesseract, EasyOCR, PaddleOCR). OpenCV alone is not an OCR engine. Always show extracted values to the user to confirm. |
| Output | Text on screen plus downloadable PDF built only from text that passed verification. No audio. |
| API | FastAPI. Storage with a 24-hour deletion job. |

## 5. Pipeline

Upload -> Extract -> Flag (plain code) -> Explain (LLM) -> Verify -> Translate -> Verify again -> Deliver

The LLM only ever sees structured rows. Translation output is verified again, because
numbers can change in translation.

## 6. Repo layout

```
CLAUDE.md                  this file
docs/plan.md               full plan, schedule, safety wording
docs/progress.md           progress report
docs/research/             research notes handed over from claude.ai chat
app/extract/pdf_rows.py    PDF words -> rows (done, digital PDFs only)
app/rules/ranges.py        range parsing and flags (done)
app/rules/sanity.py        unit sanity checks (done, ~35 tests covered)
app/rules/names.py         test-name normalisation (done)
app/schema.py              report schema and confirmation step (done)
app/eval/score.py          scoring against answer keys, counts not percentages (done)
tools/make_synthetic.py    fake reports in 3 layouts with answer keys (done)
tools/evaluate.py          run extraction on a folder and score it (done)
tools/fetch_samples.py     download public samples, write SOURCES.md (done)
data/public_samples/       sources.csv; pdf/ is git-ignored
data/real_samples/         owner's consented, redacted reports; git-ignored
tests/                     pytest
app/api/                   FastAPI app and 24-hour store (done)
(planned) app/llm/  app/verify/  prompts/  glossary/
```

Row fields: name, value, unit, range_text, computed_flag, reported_flag, flag_mismatch,
unit_check, page, raw, confidence, review_reason.

## 7. Commands (owner uses Windows and PowerShell, Python 3.14)

```
pip install -r requirements.txt
python -m pytest -q
python -m tools.make_synthetic --out data/synthetic --per-template 5
python -m tools.evaluate --pdf-dir data/synthetic/pdf --keys-dir data/synthetic/answer_keys
python -m tools.fetch_samples
python -m uvicorn app.api.main:app --reload
python -m tools.draft_key data\public_samples\pdf\hod_pk0016.pdf
python -m app.extract.pdf_rows data\public_samples\pdf\drlal_wm17s.pdf
python -m app.extract.pdf_rows data\public_samples\pdf\hod_pk0016.pdf --out hod_pk0016.json
```

Use `python -m ...` from the repo root. Give Windows paths with backslashes in instructions
for the owner. Never leave placeholder file names in commands.

## 8. Code conventions

- Python, type hints, small functions, dataclasses for records. Comments explain why.
- Every new rule or bug fix gets a test, including a regression test for any bug found on a
  real report (build a tiny synthetic PDF that reproduces it; never commit real reports).
- Tests never use the network and never call the LLM. Mock the LLM client.
- Synthetic generators use fixed seeds. The synthetic answer key must not be computed with
  the code under test.
- Report results as counts ("142 of 150 fields correct"), per group, never one blended
  percentage. A missing row counts as wrong in every field.
- Prefer refusing over guessing. New heuristics must say what they do when unsure.

## 9. Evaluation rules

- Groups are reported separately: synthetic, public samples, consented real reports.
- Consented real reports (11): 4 development, 7 locked. Do not open, print or debug against
  the locked 7. Run them once at the end of a stage and record the counts. If code changes
  after seeing locked results, say that the set is no longer a clean test.
- Real reports come from only 1 to 2 labs, so real-world numbers are optimistic. Say so.
- 2026-10-07: real reports are paused. Work uses synthetic and public samples only. Until
  real reports return, no claim of accuracy on real reports may be made.
- 2026-10-07: public samples count as development files, so draft keys are allowed for them
  (still checked line by line by the owner).
- Answer keys for real and public files are typed by a person from the PDF. A draft key
  generated from extraction output is allowed only for development files and must be
  checked line by line by the owner.
- Public samples are used privately for testing only. Terms of use are NOT yet confirmed for
  any of them. Record URL, date and hash in `SOURCES.md`. Do not republish them.
  Excluded: the Sterling Accuris sample (shows a full name and date of birth) and anything
  from document-sharing sites such as Scribd.

## 10. Current status (2026-10-07)

Done and tested (52 tests pass): coordinate-based PDF row extraction with header-driven
columns (including a Method column) and a pattern fallback; rotated watermark text removed;
symbol-font (U+F0xx) pages decoded, their rows marked low confidence; word flags after the
value (High / Low / Normal); range parsing including Indian digit grouping (1,50,000);
plain-code flags; unit sanity checks; low-confidence marking; scorer; synthetic generator;
sample downloader. `--out` writes UTF-8 JSON.
Task 2 done: `tools/draft_key.py` writes draft keys to `data/public_samples/answer_keys/`
(git-ignored) with "verified": false; `tools/evaluate.py` refuses to score unverified keys.
Drafts exist for drlal_wm17s and hod_pk0016, waiting for the owner's line-by-line check.
Task 3 deferred by the owner (2026-10-07): keys not checked, so no accuracy numbers exist.
Task 4 done: `app/schema.py` (pydantic Report, Correction; accept / correct / reject;
`usable_rows` keeps low-confidence rows out until a person decides). Row has a `status`.
Task 5 done: `app/api/` (FastAPI). POST /reports (needs consent=true, PDF only, 10 MB max),
GET and DELETE /reports/{token}. The uploaded PDF is deleted right after extraction; only
structured values are stored, in STORE_DIR (default data/store, git-ignored), for 24 hours.
Expiry is checked on every read and by an hourly cleanup loop. POST
/reports/{token}/rows/{index} accepts, rejects or corrects a row. Every response carries the
disclaimer (draft wording). 30-page limit. Scanned PDFs report `no_text_layer`.
Progress report for humans: `docs/progress.md`.

Task 1 on all 4 public samples (2026-10-07): wm17s 57 rows, z615 3 rows, drlogy 3 rows, hod
71 rows; no false result rows seen on inspection; every unparsed line reviewed (prose notes,
blank results, non-numeric urine results). No answer keys yet, so no accuracy numbers.
Known safe refusals: "7-5 - 12.0" (typo in hod) and "150 - 410 x 10³/µL" (range followed
by a multi-word unit) give flag "unknown".

Not built: photo/scan path, LLM calls, verifier, API, deletion job, PDF output, glossary,
prompts, answer keys for real files, side-by-side two-column layouts, wrapped test names,
non-numeric results (for example "Negative", "G1").

Known gotchas: Windows shell redirects change the encoding and break "µ" (use `--out`);
Firecrawl's PDF reading can differ from pdfplumber's, so trust pdfplumber on the real file.

## 11. Next tasks, in order

1. Run extraction on the other public samples (`drlal_z615`, `drlogy_thyroid`, `hod_pk0016`).
   Fix layout failures. Acceptance: no false result rows, every `unparsed` line reviewed, a
   regression test for each fix. (Real development reports are paused, see section 9.)
2. `tools/draft_key.py`: print a draft answer key from extraction output with a clear
   warning that a person must verify every line against the PDF.
3. Score the public samples that have real values (`drlal_wm17s`, `hod_pk0016`) with keys
   typed by the owner from the PDF. Record counts in `docs/results.md`. (Was: the 4
   development reports; paused 2026-10-07.)
4. Structured schema (pydantic) for an extracted report, plus a confirmation step where low
   confidence rows must be accepted or corrected.
5. FastAPI skeleton: upload, get result by token, delete; storage with the 24-hour deletion
   job and a test that proves expired data is gone.
6. LLM client wrapper (mock in tests), `prompts/explain_en_v1.md`, and the code verifier.
   Acceptance: `tests/verifier_cases.json` holds deliberately wrong sentences (wrong number,
   wrong unit, wrong flag word, flag stated on a normal value, invented number); the
   verifier rejects 100% and accepts the correct set.
7. Narrow LLM check plus the cause-text rules. Acceptance: a test file of unsafe cause
   sentences (certain cause, treatment, named diagnosis) that must be rejected, and hedged
   sentences that must pass.
8. Hindi, then Hinglish prompts; verify numbers again after translation. A native Hindi
   speaker must review a sample before any claim of Hindi support.
9. PDF output, consent screen, deployment.
10. Photo and scan path: OpenCV preprocessing and an OCR bake-off on the same files. Keep
    the numbers. Lower priority because most reports so far are digital PDFs.
11. Lipid and thyroid report support after CBC passes its tests; glossary entries written
    in the owner's own words from cited public sources, reviewed by a doctor or trusted
    reviewer.

## 12. Open items (owner decides)

- Who reviews Hindi and Hinglish output.
- Which OCR engine (decided by the bake-off).
- Terms-of-use check for each public sample before any use beyond private testing.

## 13. Handoff protocol between claude.ai (research) and Claude Code (coding)

- Research chat writes findings to `docs/research/<topic>.md` with source URLs and dates.
- Code work records decisions and measured results in `docs/results.md` and, for changed
  decisions, in a short dated line at the end of `docs/plan.md`.
- Start of a Claude Code session: read this file, `docs/plan.md`, `docs/results.md`, and run
  `python -m pytest -q`. End of a session: tests pass, status in section 10 updated.
