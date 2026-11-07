# Audit

What was checked, by whom, and what is still open. make_results.py,
results/results.md and REVIEW.md point here. The repeatable checks come
first; the build-close audit follows.

## Repeatable checks

| Check | How | Result |
| --- | --- | --- |
| SQL parity (U-07) | `python src/check_sql_parity.py`: normalises the six dbt models back to canonical form and diffs them against sql/ | all six match |
| CI checksum gate (U-10) | `make ci-check` in .github/workflows/ci.yml: regenerates SF0.1, runs every arm once, compares run-1 checksums with results/expected_checksums.json | matches on every arm (CI on Python 3.11 and 3.12) |
| Cross-arm agreement (H3) | results/checksums.json verdicts, produced by src/collect_checksums.py | 18 of 18 cells (SF0.1, SF1, SF10) agree on run 1; run 5 reproduces run 1 everywhere |
| Decision rules | `python src/check_results.py`: recomputes H1 to H6 from the logs, asserts the committed verdicts and totals, and drives every rule through its other branches with synthetic inputs | passes |
| Generated results | `python src/make_results.py` rebuilds RESULTS.md, results/results.md, run_log.md, results/verdicts.json and results/checksums/ from the logs | committed outputs are its output |
| Dashboard numbers | `npm run build` in site/ first runs site/src/results.check.mjs, which recomputes the site's verdicts, totals, savings and bootstrap intervals in JavaScript and asserts they equal results/verdicts.json | passes |

## Build-close audit

Author's audit of this build against the programme charter and the
research pack. The independent second review (pack U-12) is still open;
see REVIEW.md.

## Charter gates

1. Preregistration before data. PREREG.md was the first content commit
   (0e0c035), before any generator or runner existed and before any data
   was generated on this machine. Git history shows the order.
2. Identical inputs, identical SQL. One Parquet file set per scale read
   by all three arms; one canonical SQL set; the dbt parity script
   (src/check_sql_parity.py) diffs every dbt model against the canonical
   SQL after normalization and passes for all six transformations
   (U-07 receipt). The only model-level addition is the registered
   is_incremental() filter in the two incremental models.
3. Numbers come from scripts. Every number in RESULTS.md,
   results/results.md, and run_log.md is computed by src/make_results.py
   from results/*.jsonl and results/checksums.json. No hand-typed result
   appears in any generated file.
4. Correctness before speed. No timing result is reported for a cell
   whose checksums were not collected; the collector exits non-zero if
   run-1 checksums disagree across arms, and it did not.
5. Overclaim guard. The words "official TPC-H" appear in this repository
   only inside sentences that deny the claim. No crossover claim extends
   past SF10. No gap-closed claim is made anywhere; the README says the
   study is evidence toward the register entry, nothing more.
6. Gates are gates. The gate harness builds the downstream models only
   when every error-severity test passes; the promotion decision is in
   code (src/gates.py), not in a report. F10 is warn severity by design
   and is scored as flagged, not blocked, matching its semantics.
7. Incremental honesty. H4 is scored on checksum equality against a
   full-refresh comparator built in the same harness run, per scale,
   for scenarios S1, S2, S3, and S3b. H6 uses dbt's own model times from
   the same runs.
8. Fault scoring. Every fault in the matrix has a gate log row naming
   the test that fired, or the row says missed. F08 is scored by the
   incremental protocol, as registered.
9. Reproducibility. requirements-lock.txt pins every package;
   results/versions.json records the runtime versions including Java;
   CI reproduces the SF0.1 cell on Python 3.11 and 3.12 and compares
   against results/expected_checksums.json. CI run 42295558072 is green.
10. Spend and credentials. Zero spend: every tool is local and open
    source; the JDK is a free tarball; the DuckDB extension is a free
    download. No credential was created or used; the repository is
    public and contains no secrets (one push was blocked by GitHub push
    protection over a binary temp file pattern match; see DECISIONS.md
    D9; nothing was uploaded).

## Deviations and incidents on record

- PREREG.md Deviation 1: one uncounted warm-up pass per arm per scale,
  added after the first Spark run set showed first-run JVM costs
  inflating cell CVs to 34 to 145 percent. The pre-refinement log is
  kept at results/run_log_pre_warmup.jsonl.
- DECISIONS.md D9: the .gitignore rule that hid the generator sources,
  found by CI, fixed, and the temp-file push block.
- DECISIONS.md D10: the SF10 false alarm (single-call launch mistaken
  for a slicing failure), the controlled slicing test, and the relaunch
  with --children 10.
- DECISIONS.md D3: the Spark block-manager result-fetch stall on this
  VM and the maxDirectResultSize setting that removes it, with the
  attribution test.
- DECISIONS.md D14 to D17: the dbt SF10 settings change, one process
  per run, per-phase incremental rows, and the restart and load log.
- DECISIONS.md D18: checksum collection disk pressure failure, the
  scratch cleanup, and the per-arm persistence patch.

## Close checks (filled at build close, 2026-11-07)

- SF10 completion state: complete. All three arms ran five runs at
  SF10; checksums were collected under the registered protocol (full
  ordered checksums for runs 1 and 5, row counts plus 100,000-row
  ordered checksums for runs 2 to 4); the incremental protocol ran all
  four scenarios against the SF10 full-refresh comparator. Nothing at
  SF10 is recorded as untested.
- H2 verdict: refuted. The best SF10 per-transformation ratio is 0.467
  (T1); no transformation reaches 1.5, so no crossover is observed
  inside the ladder tested. The claim stops at the ladder, as the
  overclaim guard requires.
- H6 verdict: partially supported. The saving is 87.1% at SF10 (above
  the 50% line), but SF1 also exceeds 50% (70.5%), where H6 predicted
  small scales stay below it; SF0.1 is 23.2%.
- SF10 variation: three DuckDB cells carry CVs above 30% (T4 47%, T3
  36%, T5 33%). Cause on record: a co-tenant workload on the same VM
  (load average peaks of 28 on 4 cores) and seven VM restarts across
  the SF10 sequence (DECISIONS.md D12, D13, D17, D18). Means are over
  five runs; the verdicts do not turn on these cells (H2's margin is
  wide, and H1 is judged at SF0.1 and SF1).
- Jev claim_check: routed REVIEW. Model jev-1.13.0, question id
  supported, noul 0.66 (band: clear at 0.85 or above, block at 0.10 or
  below, review between); 1,035 input tokens, 20 output tokens. Per the
  gate rule, the headline claim was then hand-verified line by line
  against the generated files (RESULTS.md, results/results.md,
  results/checksums.json): every figure in the claim traces to a
  generated value, including the six SF10 ratios, the 18 of 18 checksum
  verdicts, the three savings, and the 10 of 10 gate matrix. The claim
  stands as written.
- Final grade: 7,250 of 10,000, floored and itemized. Deductions:
  SF30 cut as a machine limit, -400; Spark local mode only, no
  cluster, -500; co-tenant load during SF10 with three cell CVs above
  30%, -500; seven VM restarts across the SF10 sequence, -250; dbt
  SF10 thread and memory settings changed under D14, -200; warm-up
  pass deviation from the original preregistration text (Deviation 1,
  disclosed, pre-refinement log kept), -150; checksum collection took
  three attempts and a persistence patch (D18), -150; no second
  reviewer, U-12 still open, -600.
