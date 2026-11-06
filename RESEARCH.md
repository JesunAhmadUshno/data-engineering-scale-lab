# Research base

Systematic base for this study, from the AI Platform Research Programme
Track B2 research pack (Claude verdict pack 08, 2026-11-06), checked by the
coordinator on receipt. Search and inclusion rule for the pack: official
documentation first, then primary papers, then credible public benchmark
repositories. Vendor and secondary benchmark claims are labelled as such
and are never used as study results.

## Past

- TPC-H has been the standard decision-support benchmark shape for three
  decades: scale factors multiply a fixed schema, and results are only
  comparable under the TPC's own rules, which is why this study labels
  every output "derived from TPC-H" and claims no comparability.
- Single-node analytical engines (DuckDB, SIGMOD 2019, DOI
  10.1145/3299869.3320212) closed much of the gap that once made a
  distributed engine the default answer for gigabyte-scale analytics.
- dbt moved transformation logic into versioned SQL with tests; its
  incremental models document that without unique_key an incremental
  model is append-only and inserts all rows returned by the model's SQL
  (dbt documentation, grade A in the pack's evidence table).

## Present

- Apache Spark local mode runs on a laptop without a cluster; the Spark
  documentation presents it as a development and testing mode, and states
  that for small datasets, reading and writing Parquet is expensive and
  data movement can negate parallelism benefits (grade A). That documented
  overhead is exactly what H1 prices.
- DuckDB's tpch extension generates DBGEN data into persistent tables and
  can split generation to save memory; its published resource table
  reports SF100 at 17 minutes and 71 GB single-step memory on a 128
  thread machine (DuckDB documentation, grade A). Those figures set this
  study's scale ladder against the machine of record.
- Secondary benchmark repositories report large single-node wins over
  DuckDB on derived from TPC-H Parquet data (DataFusion benchmarks
  README: DataFusion 2.89x faster in a specific run; Polars PDS README:
  Polars 1.35.3 25.29x faster in a specific run). Both are vendor-side
  claims about other engines, recorded here as context only (grade B).
  They show why a controlled, identical-SQL comparison on one machine is
  worth publishing: headline multipliers travel without their conditions.

## Future

- The crossover question moves as single-node engines add out-of-core
  execution and as Spark reduces local startup cost. This study's ladder
  (SF0.1, SF1, SF10 on 4 cores and 7.7 GiB) is one dated point on that
  curve, not the curve.
- Incremental correctness under late data is the part of this study most
  likely to stay true: checksums do not care which engine produced them.

## What was not verified

- The TPC fair-use PDF itself was not read. The study avoids the question:
  TPC Tools are not used (see LICENSES.md).
- The DataFusion and Polars figures were not reproduced. They are
  labelled vendor claims and are not inputs to any hypothesis.
- dbt-duckdb's support for incremental models with unique_key was marked
  unverified in the pack (N-08). This build verified it directly: see
  DECISIONS.md for the test and its result.
