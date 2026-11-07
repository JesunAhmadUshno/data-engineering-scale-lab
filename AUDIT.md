# Audit

What was checked, by whom, and what is still open. make_results.py,
results/results.md and REVIEW.md point here.

## Checks run

| Check | How | Result |
| --- | --- | --- |
| SQL parity (U-07) | `python src/check_sql_parity.py`: normalises the six dbt models back to canonical form and diffs them against sql/ | all six match |
| CI checksum gate (U-10) | `make ci-check` in .github/workflows/ci.yml: regenerates SF0.1, runs every arm once, compares run-1 checksums with results/expected_checksums.json | matches on every arm (CI on Python 3.11 and 3.12) |
| Cross-arm agreement (H3) | results/checksums.json verdicts, produced by src/collect_checksums.py | 12 of 12 cells agree on run 1; run 5 reproduces run 1 everywhere |
| Decision rules | `python src/check_results.py`: recomputes H1 to H6 from the logs, asserts the committed verdicts and totals, and drives every rule through its other branches with synthetic inputs | passes |
| Generated results | `python src/make_results.py` rebuilds RESULTS.md, results/results.md, run_log.md, results/verdicts.json and results/checksums/ from the logs | committed outputs are its output |
| Dashboard numbers | `npm run build` in site/ first runs site/src/results.check.mjs, which recomputes the site's verdicts, totals, savings and bootstrap intervals in JavaScript and asserts they equal results/verdicts.json | passes |

## Open

- Independent review (U-12): none yet. REVIEW.md stays open and the study
  is UNVERIFIED for review status. Every check above is the author's.
- SF10 was not run, so H2 and H6 are Not yet measured and the study does
  not yet pass its own decision rule (PREREG.md Section 2).
- H6 small-scale clause: SF1 saving is 70.5 percent, above the 50 percent
  ceiling, so H6 can at best be Partially supported once SF10 runs.
- Two DuckDB cells above 30 percent CV (PREREG.md Deviation 2).
