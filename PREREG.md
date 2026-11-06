# Pre-registration: Data Engineering at Scale Lab

Status: registered before any data was generated or touched. The git history
is the timestamp. Any change after the first data touch is recorded at the
bottom of this file as a protocol deviation with date, reason, and effect on
the conclusion.

Study source: AI Platform Research Programme, Track B2 (Claude verdict pack
08), adopted under the programme charter's ten gates. This file is the
HYPOTHESES.md equivalent for this repository; H1 to H6 below are the
pre-registered hypotheses and Section 1 is the question gate record.

## 1. Research question

RQ1: At what data scale, if any, does local Apache Spark beat a modern
single-node engine (DuckDB) on identical transformations, and what do
incremental dbt models with data-quality gates cost and catch compared with
full-refresh builds?

## 2. Hypotheses (falsifiable, with thresholds)

- H1, Speed at small scale: for SF0.1 to SF1, DuckDB wall-clock is less than
  Spark local-mode wall-clock by at least 2x, because Spark's fixed setup
  and scheduling overhead dominates at small scale.
- H2, Crossover at scale: for a scale point SF10 or above, Spark local mode
  beats DuckDB by at least 1.5x on at least one transformation, once data no
  longer fits comfortably in the single-node engine's working memory.
- H3, Correctness: output checksums are identical across DuckDB, Spark, and
  dbt for every transformation at every scale point. Silent divergence is a
  failure, not noise.
- H4, Incremental correctness: for a late-arriving factor that changes a
  previously computed aggregate, a full-refresh run and a correctly specified
  incremental run produce the same output checksum at every scale point. A
  mismatch fails the study.
- H5, Quality gates: dbt's data quality gates catch at least 50% of injected
  faults, with zero missed critical faults across the fault matrix. The 50%
  threshold is chosen for this first study; it is not a standard or
  benchmark.
- H6, Incremental economics: incremental dbt models are more than 50% lower
  in cost than full-refresh models only where a daily upsert exists, and
  that condition is not met at SF0.1 and SF1. Operational reading for this
  build: the incremental saving (Section 7) exceeds 50% at SF10 and does
  not exceed 50% at SF0.1 or SF1, for the same fixed late-data delta at
  every scale.

Decision rule: the study passes only if every hypothesis holds at its stated
threshold. If H2 fails at every scale point tested, the answer is "no
crossover inside the ladder tested". If H3 fails for any transformation at
any scale point, the study is STOP, do not publish; that is a correctness
failure. If a scale point cannot complete on the machine of record, it is
recorded as "not tested on this machine", which is not the same as the
hypothesis being false.

## 3. Machine of record

This VM: 4 CPU cores, 7.7 GiB total RAM, Linux, local disk. All timings are
from this machine only. No cloud, no cluster, no second machine. Another
workload shares this VM during the build; runs use capped memory settings
(DuckDB memory limit and Spark driver memory, recorded in METHODS.md) and
the run log records the settings with the results.

## 4. Dataset

Data generated locally by DuckDB's tpch extension (call dbgen). The data is
derived from TPC-H. It is not official TPC-H benchmark data and no result in
this repository is comparable to official TPC results. TPC Tools are not
used; no registration is made anywhere. See LICENSES.md.

Tables used: lineitem (6,000,000 x SF rows) and orders (1,500,000 x SF
rows). Generated tables are exported once to Parquet; all three arms read
the identical Parquet files.

Scale ladder for this build: SF0.1, SF1, SF10.

SF30 is cut before preregistration, as a documented machine limit: SF30 is
about 33 GB raw with an estimated 15 to 18 GB generation peak, which the
machine of record (7.7 GiB RAM) cannot hold. The cut is recorded here,
before any data touch, so it is a scope decision, not a result. SF10 data
is generated in split chunks to fit the machine.

## 5. Arms

- Arm A, DuckDB single-node: DuckDB over the shared Parquet files, SQL.
- Arm B, Spark local mode: Apache Spark, local[*] (as many worker threads
  as logical cores), same Parquet files, SQL.
- Arm C, dbt on DuckDB: dbt project with staging, intermediate, and mart
  models over the same DuckDB engine as Arm A. Incremental models use
  is_incremental() and unique_key. The dbt arm tests the framework, not a
  second engine; that asymmetry is intentional and stated.

Versions (Spark, dbt, DuckDB, Java) are pinned in the lockfile and recorded
in the run log before the first measured run.

## 6. Transformations (frozen)

All column names are the tpch extension's names. line_amount means
l_extendedprice * (1 - l_discount). All monetary arithmetic is decimal
arithmetic on the generated DECIMAL columns.

- T1 Filter: filtered_lineitem. All lineitem columns where l_shipdate is on
  or after DATE '1995-01-01' and before DATE '1996-01-01'.
- T2 Join: lineitem_orders. lineitem joined to orders on
  l_orderkey = o_orderkey. Output columns, in order: l_orderkey, l_partkey,
  l_suppkey, l_linenumber, l_quantity, l_extendedprice, l_discount, l_tax,
  l_returnflag, l_linestatus, l_shipdate, l_commitdate, l_receiptdate,
  l_shipinstruct, l_shipmode, l_comment, o_custkey, o_orderstatus,
  o_totalprice, o_orderdate, o_orderpriority.
- T3 Aggregate: daily_sales. From lineitem joined to orders, grouped by
  o_orderdate as order_date: orders_count = COUNT(DISTINCT l_orderkey),
  line_count = COUNT(*), gross_revenue = SUM(line_amount),
  net_revenue = SUM(line_amount * (1 + l_tax)).
- T4 Window: ranked_sales. From lineitem_orders: order_date (from
  o_orderdate), l_orderkey, l_linenumber, line_amount, and
  rnk = RANK() OVER (PARTITION BY order_date ORDER BY line_amount DESC).
- T5 Type conversion: converted. From lineitem joined to orders:
  l_orderkey, l_linenumber, quantity_int = CAST(l_quantity AS INTEGER),
  extended_price = CAST(l_extendedprice AS DECIMAL(18,2)),
  total_price = CAST(o_totalprice AS DECIMAL(18,2)),
  shipdate_text = CAST(l_shipdate AS VARCHAR),
  orderdate_text = CAST(o_orderdate AS VARCHAR),
  discount_pct = CAST(l_discount * 100 AS INTEGER).
- T6 Sort and limit: top_10_daily. From daily_sales joined to ranked_sales
  on order_date with rnk = 1: order_date, orders_count, gross_revenue,
  top_line_amount = MAX(line_amount), grouped by order_date, orders_count,
  gross_revenue, ordered by gross_revenue DESC, order_date ASC, LIMIT 10.

The SQL logic is identical in all three arms. Arm-specific wrappers
(temporary views in Spark, ref() and source() in dbt) do not change the
logic; the canonical SQL lives in sql/ and each arm's copy is generated or
checked against it.

## 7. Measurement and correctness protocol

- Five runs per measured cell (arm x scale x transformation). Report mean,
  standard deviation, and coefficient of variation (CV) per cell. Above 30%
  CV a run set is unusable and is re-run after the cause is found.
- Spark setup overhead (JVM and session start) is measured and reported
  separately from query time. DuckDB open time is reported the same way.
- Speedup = Time_DuckDB / Time_Spark for the same transformation at the
  same scale point.
- Incremental saving = (full-refresh cost - incremental cost) /
  full-refresh cost, in percent, where cost is wall-clock time of the dbt
  build for the affected models (T3 and T4). Dollar cost is 0 everywhere in
  this local study and is kept as a column, not a charged amount.
- Gate catch rate = faults caught / faults injected, per gate and overall.
- Checksums: SHA256 over the ordered output (ORDER BY all output columns),
  computed from a canonical text export, stored under
  results/checksums/<arm>/<scale>/<transformation>.sha256.
- Row-count balance: rows in = rows out + rows rejected + rows routed to
  quarantine, for every run. If it does not balance, the run is invalid.
- Re-run determinism: the same input, code, and versions give identical
  checksums on re-run. At SF10, full ordered checksums are computed for
  runs 1 and 5 of every transformation; runs 2 to 4 are verified by row
  count and by an ordered checksum of the first 100,000 output rows. This
  SF10 limit is registered here, before any run.
- dbt per-model times for Arm C come from dbt's run_results.json, not from
  hand timing.

## 8. Late-arriving data and incremental protocol (Arm C)

The late delta is a small fixed set of synthetic rows (labelled synthetic,
generated; fixed seed; see data/gen/synth.py): new orders and lineitems on
existing order dates, plus one update row that changes the l_extendedprice
of an existing lineitem (fault F08's shape). Staging merges base and delta
with the delta winning on (l_orderkey, l_linenumber) for lineitem and on
o_orderkey for orders.

T3 and T4 are incremental models with unique_key (order_date for T3;
(order_date, l_orderkey, l_linenumber) for T4). On an incremental run, the
models recompute only the order dates present in the delta and replace
those keys.

Three timing scenarios, each tested at every scale point:
- S1: the late file exists before the run; it is processed as normal data.
- S2: the late file arrives after the staging model has run but before the
  mart models; the incremental run must pick it up.
- S3: the late file arrives after the run finished and a fresh run is
  attempted, including the variant where the late rows are appended to the
  existing staging input.
Requirement: in every scenario, the incremental output checksum for T3 and
T4 equals the full-refresh output checksum computed on base plus delta.

Scenario S1 is the control: incremental and full-refresh both see the same
merged staging input from the start.

## 9. Fault matrix and gate semantics (Arm C)

Faults are injected into copies of the SF0.1 staging inputs. dbt tests are
configured as promotion gates: staging models build first, the gate tests
run, and mart models are built only if every error-severity gate test
passes. A failed gate blocks promotion and is recorded in the gate log. A
post-hoc test report without the block does not count as a gate.

- F01 Duplicate primary key (orderkey): unique test on o_orderkey. Critical.
- F02 Null primary key: not_null test on o_orderkey. Critical.
- F03 Orphan foreign key: relationships test, staging lineitem l_orderkey
  to staging orders o_orderkey. Critical.
- F04 Negative quantity: singular test, no l_quantity below 0. Critical.
- F05 Bad date format: singular test, every l_shipdate parses as a date.
  Critical.
- F06 Price stored as a string: schema check, l_extendedprice has a numeric
  type in staging. Critical.
- F07 Duplicate whole row: singular test, no fully duplicated lineitem row.
  Not critical. Caught means the gate blocks promotion, or the row is
  deduplicated and logged.
- F08 Late-arriving row with a changed price: the checksum equality gate of
  Section 8. Caught means the incremental run matches the full-refresh
  checksum exactly (the update is applied once, with the new price).
  Critical.
- F09 Missing column (partkey): schema check, l_partkey exists in staging.
  Critical.
- F10 Stale file (old shipdates): freshness check with warn severity.
  Not critical. Caught means the run is flagged in the gate log as stale
  while promotion is allowed.

Critical faults are F01, F02, F03, F04, F05, F06, F08, F09. H5 fails if any
critical fault is missed.

## 10. What stays out

Distributed Spark clusters, cloud warehouses, BigQuery, streaming,
dashboards, Airflow, Kubernetes, ML modelling, a second dataset family,
tuning experiments beyond the stated arms. Nothing in this study supports a
claim about production Spark or any cloud system.

## 11. Overclaim guard (binds all prose in this repository)

- No "Spark is faster" or "DuckDB is faster" claim without the scale point,
  the transformation, and the number of runs named beside it.
- If H2 fails at every scale point tested, the verdict is "no crossover
  observed inside the ladder tested", not a proof that no crossover exists.
- No gate claim without the fault matrix numbers: how many of F01 to F10
  were caught, by which gate, and how many critical faults were missed.
- No claim of comparability to official TPC results. The label is "derived
  from TPC-H".
- No claim that this study alone closes the portfolio gap. It adds one
  Spark, dbt, and warehouse-target artifact to the record.

## Protocol deviations

None at registration time. Deviations will be appended here with date,
reason, and effect on the conclusion.
