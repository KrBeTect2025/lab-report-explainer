# Results log

Record measured results here as counts, per group (synthetic, public samples, consented real reports).

(no real-file scores yet)

## 2026-10-07: extraction on public samples (task 1)

Row counts only. These are not accuracy numbers: no answer keys exist yet.

| Sample | Rows | Low-confidence rows | Unparsed lines | Notes |
|---|---|---|---|---|
| drlal_wm17s | 57 | 2 | 6 | low: BUN/Creatinine Ratio (no unit or range), "Treatment Goals ... 2020" heading |
| drlal_z615 | 3 | 3 | 11 | symbol-font encoded; most results blank (listed as missing_value) |
| drlogy_thyroid | 3 | 0 | 2 | word flag "Normal" after value |
| hod_pk0016 | 71 | 0 | 20 | diagonal watermark; Method column; urine NIL / 1-2 results unparsed |

Fixes, each with a regression test: Method column, rotated watermark, word flags,
symbol-font decoding, unit spellings mcg/dL and mU/L.
