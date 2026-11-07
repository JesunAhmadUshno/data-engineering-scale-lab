# Research review

A review of this repository against a doctoral-level research rubric,
dated 2026-11-07 and regraded the same day after the SF10 runs landed on
the default branch (DECISIONS.md D14 to D18). Grades: A (meets the bar), B (meets it with stated
gaps), C (a gap that weakens a conclusion). Every gap that could be fixed
without new compute, paid services or long runs was fixed in the same
change as this file; each remaining gap names the exact compute or data
it needs.

## Summary

| Criterion | Grade | One line |
| --- | --- | --- |
| Research question | A | RQ1 is specific, scoped to one machine and answerable |
| Hypotheses | A | H1 to H6 are falsifiable with numeric thresholds, registered before data |
| Method | A | Three arms, identical inputs and SQL, parity check, frozen transformations |
| Baselines and comparators | B | Spark vs DuckDB is head to head; dbt uses a different timing base |
| Statistics and uncertainty | B | Mean, SD, CV over n=5 plus bootstrap intervals at all three scales; no tests, small n, SF10 cells under co-tenant load |
| Reproducibility | A | Lockfile, CI checksum gate, generated results, decision-rule checks |
| Threats to validity | A | Stated in METHODS.md, PREREG.md and on the dashboard |
| Related work | B | RESEARCH.md cites primary docs and DuckDB's SIGMOD paper; thin on prior benchmarks |
| Limitations and completeness | B | Every hypothesis has a verdict up to SF10 (H2 refuted, H6 partially supported); SF30, a cluster and a second reviewer remain |

## Criteria in detail

### Research question (A)

RQ1 names the engines, the variable (data scale), the outcomes (speed,
cost and catch rate of incremental dbt models) and the machine. PREREG.md
Section 10 lists what is out of scope.

### Hypotheses (A)

Six hypotheses with thresholds, a study-level decision rule (pass only if
all hold) and a stated reading for each failure mode ("no crossover
inside the ladder tested", "not tested on this machine"). The numeric
operationalisation is in METHODS.md and src/make_results.py.

Fixed in this change: H6 was reported only as "Not yet measured", which
hid that the SF1 saving (70.5%) already breaks the pre-registered clause
that the saving stays at or below 50% at SF1. make_results.py, RESULTS.md
and the dashboard now say so, and that the best possible H6 verdict is
Partially supported. The rule itself is unchanged. With SF10 now
measured, that is the verdict H6 received: 87.1% at SF10 meets the
large-scale clause, SF1's 70.5% breaks the small-scale one.

### Method (A)

Identical Parquet inputs, canonical SQL with a parity script for the dbt
copies, one fixed CSV writer for checksums, a warm-up pass registered as
Deviation 1 with the discarded runs kept. The fault matrix and late-data
scenarios follow PREREG.md Sections 8 and 9.

### Baselines and comparators (B)

DuckDB against Spark is a fair head-to-head on execution plus write.
Arm C (dbt) uses dbt's execution_time, a different basis, and is
correctly never ratioed. Gap that remains: fault attribution per gate is
not analysed. F02 also trips the relationships test and F09 also errors
gate_no_duplicate_rows; the dashboard now flags this, but separating the
designed gate from side effects needs a re-run of the gate harness with
one test enabled at a time (src/gates.py on SF0.1, about ten dbt builds,
minutes on the machine of record; needs duckdb and dbt installed, which
this review machine does not have).

### Statistics and uncertainty (B)

Fixed in this change:

- Bootstrap 95% percentile intervals (2,000 resamples of the five runs,
  seed 20261106) for every D/S ratio and the total, in make_results.py,
  results/verdicts.json and the dashboard. The H1 totals are 0.125
  (0.115 to 0.136) at SF0.1 and 0.162 (0.158 to 0.166) at SF1, far from
  the 0.5 line. At SF10 the total is 0.248 (0.228 to 0.270), and the
  highest single ratio, T1 at 0.467 (0.432 to 0.506), is far from H2's
  1.5 line, so the H2 refutation does not hinge on run-to-run spread.
- The two DuckDB cells over the pre-registered 30% CV line (SF0.1 T3,
  SF1 T6) are now recorded as PREREG.md Deviation 2 instead of only
  being explained in METHODS.md.

Remaining, with what each needs:

- H6 and H4 rest on one incremental cycle per scale. Five repeated S3
  cycles per scale (src/run_incremental.py at SF0.1 and SF1, with duckdb
  and dbt-duckdb installed; well under an hour on the machine of record)
  would put a spread on the savings (ROADMAP item 3).
- Setup overhead is one measurement per scale. Five setup measurements
  per arm and scale need the same environment and minutes of runtime.
- Three DuckDB cells at SF10 (T3 36%, T4 47%, T5 33%) are over the 30%
  CV line. The cause on record is co-tenant load and VM restarts during
  the SF10 sequence (AUDIT.md, DECISIONS.md D17), not timer jitter, so
  they are reported with that cause rather than under Deviation 2.
  Re-running them needs SF10 regenerated, DuckDB installed and a quiet
  machine (no co-tenant workload); a full DuckDB pass of the six
  transformations at SF10 averaged about 350 s on the machine of record.
  No verdict turns on them.
- The SF0.1 and SF1 over-30% CV cells were not re-run as the protocol asks. Re-running
  them needs the SF0.1 and SF1 data regenerated and DuckDB installed; a
  higher run count for sub-150 ms cells would be the better fix.
- With n=5 a bootstrap interval is rough. No significance tests are
  reported; given ratios of 0.125 and 0.162 against a 0.5 threshold,
  more runs would not change H1, so this is noted, not prioritised.

### Reproducibility (A)

requirements-lock.txt, results/versions.json, an SF0.1 end-to-end CI
gate against committed checksums, and make targets for each step.

Fixed in this change:

- The generated outputs promised by PREREG.md Section 7 and referenced by
  METHODS.md were missing. RESULTS.md, results/results.md, run_log.md and
  results/checksums/<arm>/<scale>/<transformation>.sha256 are now
  committed, plus results/verdicts.json.
- make_results.py and REVIEW.md referred to an AUDIT.md that did not
  exist. AUDIT.md now lists the checks run and what is open.
- No test covered the decision rules. src/check_results.py asserts the
  committed verdicts and totals and drives each rule through its other
  branches; it runs in `make check` and in CI. The dashboard build runs a
  JavaScript known-answer check against results/verdicts.json.
- Hygiene: sql/dbt/logs/dbt.log and sql/dbt/.user.yml are no longer
  tracked; dbt logs, target/ and the site build outputs are ignored.
- After the SF10 merge, make_results.py printed a stale "SF10 was not
  run" section and labelled the SF10 high-CV cells as sub-150 ms timer
  jitter. Both are now driven by the data: the status section names
  whichever hypotheses lack a verdict (none at present), and SF10 cells
  cite their own cause. src/check_results.py pins the SF10 known answers
  (H2 best 0.467, SF10 total 0.248, H6 87.1%) and still exercises the
  Not yet measured branches by dropping the SF10 rows.
- There was no README. README.md now gives the question, arms, results,
  reproduction commands, limitations and the dashboard link.

### Threats to validity (A)

METHODS.md lists the single machine with co-tenant load, local-mode
Spark, one dataset family, mixed timing bases and the synthetic
freshness calendar. DECISIONS.md D3 and D4 document the Spark stall and
the discarded early runs. The dashboard shows these beside the results.

### Related work (B)

RESEARCH.md grounds the study in official documentation, DuckDB's SIGMOD
2019 paper and labelled vendor benchmark claims. Gap that remains: no
peer-reviewed single-node versus distributed engine comparisons beyond
DuckDB's own paper are discussed. Closing it needs a literature search
and reading time, no compute; it is left for the second reviewer pass so
the reading is independent of the author.

### Limitations and completeness (B)

Regraded from C. The gap that set the C, SF10 not run, is closed: all
three arms ran five times at SF10, checksums agree in 18 of 18 cells,
and the SF10 incremental cycle ran (DECISIONS.md D14 to D18). Every
hypothesis now has a verdict: H1, H3, H4 and H5 supported, H2 refuted
(no crossover inside the ladder tested), H6 partially supported. Under
PREREG.md Section 2 the study therefore does not pass as a whole; that
is a measured outcome, not an incomplete one. The SF10 sequence carried
costs that are disclosed rather than hidden: dbt thread and memory
settings changed (D14), one process per dbt run (D15), VM restarts and
co-tenant load (D17), and a checksum collection that needed a
persistence patch (D18).

Remaining, with what each needs:

- The H2 claim stops at SF10. SF30 needs a machine with about 32 GB of
  RAM (ROADMAP item 1), the same code and protocol, and several hours.
- Spark is local mode only. A cluster comparison needs a multi-node
  Spark deployment, which is outside this study's zero-spend scope.
- An independent reviewer named in REVIEW.md (research pack U-12).
  Needs a person who is not the author; until then the study is
  UNVERIFIED for review status by its own rule.
