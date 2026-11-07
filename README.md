# Data Engineering at Scale Lab

Live dashboard: https://jesunahmadushno.github.io/data-engineering-scale-lab/

Derived from TPC-H. Not official TPC-H results; no comparability to
official TPC-H results is claimed. See LICENSES.md.

## Problem

"Just use DuckDB" and "you need Spark" are both common advice for batch
transformation work, and both are usually given without numbers. The
question this study measures is where the crossover sits for a fixed,
realistic transformation workload on one machine: at what scale does a
single-node embedded engine stop dominating a local-mode distributed
engine, and what do correctness gates and incremental processing cost on
top of each?

## Purpose

Track B2 of a portfolio gap-closure programme. The gap register entry it
addresses is hands-on data engineering at scale: Spark and dbt work with
measured evidence, not tutorial familiarity. The study is the evidence.

## Research question and verdict

RQ1 and H1 to H6 were registered in PREREG.md before any data was
generated (commit order in git history proves it). The verdicts are
computed from the generated result files by src/make_results.py and are
printed in RESULTS.md and results/results.md. In one paragraph:

H1 is supported: the total workload ratio (DuckDB time divided by Spark
time) is 0.125 at SF0.1 and 0.162 at SF1, both at most 0.5. H2 is
refuted: at SF10 no transformation reaches a 1.5 ratio (the best is
0.467), so no crossover is observed inside the ladder tested. H3 is
supported: 18 of 18 (scale, transformation) cells agree across all
three arms on run 1, and run 5 determinism holds everywhere. H4 is
supported: every late-data scenario checksum equals the full-refresh
comparator at every tested scale. H5 is supported: 10 of 10 faults
caught, zero missed critical faults. H6 is partially supported: the
incremental saving is 87.1% at SF10, but SF1 also exceeds 50% (70.5%),
where H6 predicted small scales stay below it; SF0.1 is 23.2%.

## Results table

Sum of the six transformation means per scale, seconds. Full per-cell
tables with SD and CV are in results/results.md.

| Scale | DuckDB total s | Spark total s | Ratio D/S | Bootstrap 95% interval |
| --- | --- | --- | --- | --- |
| SF0.1 | 1.48 | 11.86 | 0.125 | 0.115 to 0.136 |
| SF1 | 16.27 | 100.59 | 0.162 | 0.158 to 0.166 |
| SF10 | 351.62 | 1417.89 | 0.248 | 0.228 to 0.270 |

The intervals resample the five measured runs per cell (src/make_results.py,
results/verdicts.json); at n=5 they describe run-to-run spread on this
machine, not a population.

Setup overhead is reported separately from query time (Spark session
start: 16.82 s at SF0.1, 19.41 s at SF1, 20.43 s at SF10; DuckDB connect
and views: 0.49 s, 0.27 s, 0.21 s). dbt model times are dbt
execution_time and are not ratioed against engine times.

## Architecture

- Data: data/gen/generate.py (DuckDB tpch extension, call dbgen) writes
  Parquet once per scale; data/gen/synth.py writes the synthetic late
  delta by fixed arithmetic. SF10 is generated in ten split chunks
  (dbgen children and step).
- Canonical SQL: sql/t1 to t6, one file per transformation, run as
  written by Arms A and B and wrapped by Arm C.
- Arm A: src/run_duckdb.py. Arm B: src/run_spark.py. Arm C:
  src/run_dbt.py driving the dbt project in sql/dbt/ (staging views,
  intermediate tables, mart tables; incremental models with unique_key;
  dbt tests wired as promotion gates by src/gates.py).
- Correctness: src/checksum.py exports ordered output through one fixed
  CSV writer and hashes it; src/collect_checksums.py compares arms, row
  counts, and run-to-run determinism.
- Late data: src/run_incremental.py runs the full-refresh comparator and
  scenarios S1, S2, S3, S3b per scale. Faults: src/inject.py builds the
  F01 to F10 fixtures; src/gates.py scores promotion blocking.
- Reports: src/make_results.py generates RESULTS.md, results/results.md,
  run_log.md, and the per-arm checksum files. Nothing numeric in them is
  hand-typed.

## Reproduction

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
# Spark needs a JVM (Java 17 or 21) on PATH or as JAVA_HOME.
python data/gen/generate.py --sf 0.1
python data/gen/synth.py --sf 0.1
python src/run_duckdb.py --sf 0.1 --runs 5
python src/run_spark.py --sf 0.1 --runs 5
python src/run_dbt.py --sf 0.1 --runs 5
python src/gates.py
python src/run_incremental.py --sf 0.1
python src/collect_checksums.py --sf 0.1
python src/check_expected.py --sf 0.1
```

`make ci-check` runs the same SF0.1 gate end to end; GitHub Actions runs
it on Python 3.11 and 3.12 and fails on any checksum difference.

`make check` runs the SQL parity and decision-rule checks in seconds with
no data. `python src/make_results.py` rebuilds RESULTS.md,
results/results.md, run_log.md and results/verdicts.json from the logs.

The dashboard builds with `cd site && npm ci && npm run build`; the build
first runs site/src/results.check.mjs, which recomputes the verdicts,
totals and intervals in JavaScript and fails if they differ from
results/verdicts.json.

## Limitations

- One machine (4 cores, 7.7 GiB RAM), shared with other work during the
  build; warm-up passes and five-run means mitigate, not cure.
- Spark is local mode only. Nothing here measures a cluster.
- SF30 was cut before preregistration as a machine limit; the ladder
  stops at SF10, and no claim extends past it.
- One dataset family and one six-transformation workload.
- The freshness gate checks the generated data's own 1992 to 1998
  calendar; it tests the mechanism, not a production policy.
- Five runs per timing cell, one run per late-data scenario and per
  setup measurement; intervals are bootstrap percentiles over n=5.
- Two sub-150 ms DuckDB cells at SF0.1 and SF1 exceed the 30% CV line
  (PREREG.md Deviation 2), and three DuckDB cells at SF10 do too, under
  co-tenant load (AUDIT.md).
- No second reviewer yet: REVIEW.md is open, and the study carries the
  research pack's UNVERIFIED label for review status until it is filled.

## Citations and provenance

- Research base: Claude Project chat pack 08 (coordinator-verified);
  its full source map is in RESEARCH.md. A rubric review of the study's
  rigor, with the compute each open gap needs, is docs/research-review.md.
- TPC-H benchmark: Transaction Processing Performance Council. The data
  here is generated by DuckDB's tpch extension; see LICENSES.md.
- DuckDB, Apache Spark, and dbt documentation for version behaviour;
  exact versions are pinned in requirements-lock.txt and
  results/versions.json.
