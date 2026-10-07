# Progress report

As of 2026-10-07.

## Summary

The first half of the pipeline works end to end and was demonstrated on a live server:
a PDF is uploaded, its test rows are read and flagged by plain code, a person reviews
uncertain rows, and the result is stored for 24 hours, then deleted. The LLM half
(explain, verify, translate, deliver) is not started. Tasks 1, 2, 4 and 5 of 11 are done;
task 3 is deferred, so there are no accuracy numbers yet. 52 automated tests pass.

Work so far uses synthetic reports and 4 public lab samples only. Real reports are paused,
so no claim about real-world accuracy can be made.

## Task status

| # | Task | Status | Note |
|---|---|---|---|
| 1 | Extraction on public samples, fix layout failures | Done | 4 fixes, each with a regression test |
| 2 | Draft answer key tool | Done | Drafts for drlal_wm17s and hod_pk0016, marked unverified |
| 3 | Score samples with hand-checked keys | Deferred | Skipped by the owner; no accuracy numbers |
| 4 | Report schema and confirmation step | Done | Accept, correct, reject over the API; flags recomputed by code |
| 5 | FastAPI skeleton with 24-hour deletion | Done | Upload, review rows, get by token, delete; expiry proven by tests |
| 6 | LLM client, English prompt, code verifier | Not started | Next |
| 7 | Narrow LLM check and cause-text rules | Not started | |
| 8 | Hindi, then Hinglish | Not started | Needs a native Hindi reviewer |
| 9 | PDF output, consent screen, deployment | Not started | API already requires consent |
| 10 | Photo and scan path, OCR bake-off | Not started | Scanned PDFs are reported as `no_text_layer` for now |
| 11 | Lipid and thyroid support, glossary | Not started | After CBC passes its tests |

## What was built

Test count went from 30 to 52. Every fix for a real-layout problem has a synthetic
regression test that fails without the fix.

### Task 1: extraction on public samples

| Sample | Problem found | Fix |
|---|---|---|
| hod_pk0016 | A Method column joined the range, so almost every flag was unknown | Method is now its own column |
| hod_pk0016 | A diagonal "Sample Report" watermark put letters into cells (55.5 read as a55.5) | Text drawn at a different angle from the page is dropped |
| drlogy_thyroid | Flag word after the value ("150.00 Normal"); all rows rejected | High / Low / Normal read and checked against the code flag |
| drlal_z615 | Symbol-font encoding; 0 rows and no warning | Decoded; rows marked low confidence (a micro sign could read as m) |
| all | Shell redirect broke the encoding of µ | New `--out` option writes UTF-8 |

Rows found: wm17s 57, hod 71, z615 3, drlogy 3. No false result rows seen on inspection;
every unparsed line was reviewed.

### Task 2: draft answer keys

`tools/draft_key.py` writes a key marked `"verified": false`. `tools/evaluate.py` refuses
to score unverified keys, so the extractor is never scored against an unchecked copy of
itself.

### Task 4: confirmation step

Low-confidence rows stay out of explanations until a person accepts or corrects them. Any
row can be rejected. A correction carries only printed facts (name, value, unit, range);
the flag is recomputed by code.

### Task 5: web API

| Endpoint | What it does |
|---|---|
| `POST /reports` | Upload a PDF. Needs `consent=true`; PDF only; 10 MB and 30 pages max |
| `GET /reports/{token}` | Read the result |
| `POST /reports/{token}/rows/{index}` | Accept, reject or correct one row |
| `DELETE /reports/{token}` | Delete the result now |

- The uploaded PDF is deleted right after extraction; its file name is never stored.
- Results expire at 24 hours, checked on every read and by an hourly cleanup job.
  Editing a row does not extend the 24 hours.
- Every response carries the safety disclaimer (draft wording, owner may change it).
- A scanned PDF with no text returns `no_text_layer` per page instead of nothing.

### Gaps found in a self-review and closed the same day

The first version of tasks 4 and 5 was called done too early. A check against CLAUDE.md
found four gaps, now fixed and tested: no API endpoint for the confirmation step, scanned
PDFs returned nothing silently, no disclaimer in responses, no page limit.

## Decisions made (2026-10-07)

| Decision | Effect |
|---|---|
| Real reports paused | Synthetic and public samples only; no real-world accuracy claim until they return |
| Public samples count as development files | Draft answer keys allowed for them, checked by a person |
| Manual key check skipped for now | Task 3 deferred; evaluate scores 0 rows |
| Uploaded PDF not stored | Stricter than the 24-hour rule: only structured values are kept, for 24 hours |

## Unproven or not built

- **No accuracy numbers.** Needs the two draft keys checked by hand (task 3).
- **No real reports tested.** Public samples come from 3 labs; other layouts may differ.
- **Untested layouts:** side-by-side two-column pages, test names that wrap onto two lines.
- **Non-numeric results** such as "NIL", "Negative" or "1-2" go to unparsed, not rows.
- **Not built:** LLM calls, verifier, translation, PDF output, consent screen, deployment,
  photo and scan path, glossary.
- **Deprecation warnings** from the installed FastAPI on Python 3.14; harmless now.

## Next steps

- [ ] Task 6a: LLM client wrapper. Official `anthropic` SDK, model from `CLAUDE_MODEL`, key from `.env`, mocked in every test.
- [ ] Task 6b: `prompts/explain_en_v1.md`. Plain English, hedged wording, "please discuss this with your doctor" on every abnormal value. Sees only usable rows.
- [ ] Task 6c: code verifier, layer 1. Every number, unit and flag word must match the report. Acceptance: `tests/verifier_cases.json`, wrong sentences rejected 100%, correct ones accepted.
- [ ] Task 6d: fallback. Failed verification retries once, then shows only the values table with code flags and the disclaimer.
- [ ] (owner) Add `ANTHROPIC_API_KEY` and `CLAUDE_MODEL` to `.env` before the first live run.
- [ ] Task 7: narrow LLM safety check and cause-text rules, with a test file of unsafe sentences that must be rejected.
- [ ] (owner, when ready) Task 3: check the two draft keys, set `verified` to true, run evaluate.
- [ ] (owner, before task 8) Find a native Hindi reviewer.

## How to run the demo

```
pip install -r requirements.txt
python -m uvicorn app.api.main:app --reload
```

Open http://127.0.0.1:8000/docs, use `POST /reports` with a PDF from
`data\public_samples\pdf\` and `consent` set to true, then copy the token into the other
endpoints.
