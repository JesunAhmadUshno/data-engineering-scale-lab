# Decisions

Options considered, verdicts, and reasons. Dated 2026-11-06 unless stated.

## D1. Dataset source: DuckDB tpch extension, not TPC Tools

Verdict: generate locally with DuckDB's tpch extension. The research
pack left the dataset open (its U-01 and U-03). Generating with the
extension closes both: no TPC download, no registration, licence
position stated in LICENSES.md ("TPC-H tools not used; DuckDB tpch
extension used instead"). Cost: the data is DBGEN data through DuckDB's
generator rather than the reference tools; every output is labelled
"derived from TPC-H" and no comparability to official results is claimed.

## D2. Java runtime: Temurin 21 tarball under ~/workspace/tools

Spark 4.0.1 needs a JVM and none was installed. No package manager route
was used; Eclipse Temurin 21.0.13+9 was installed from the official
Adoptium binary endpoint into ~/workspace/tools/jdk-21, outside the
repository, and recorded in results/versions.json. Spark 4.0.1 supports
Java 17 and 21; 21 is the current LTS.

## D3. Spark task results returned directly (maxDirectResultSize 512MB)

Problem: with default settings, every Spark job on this VM that went
past a trivial scan stalled. The driver failed to fetch task result
blocks through the block manager; each fetch sat quiet for exactly the
120 s shuffle connection timeout, retried three times, and killed the
job (about 500 s per attempt).
Evidence: thread dump during a stall showed the executor's task thread
idle, one thread parked in BlockManager.fetchRemoteManagedBuffer via
BlockTransferService.fetchBlockSync, and the error sequence in the
driver log (TransportChannelHandler "quiet for 120000 ms",
RetryingBlockTransferor "Failed to fetch block taskresult_2").
Attribution test: adding only spark.task.maxDirectResultSize=512MB, with
every other setting at the failing values, made the same join complete
in 11.7 s. The timeout knob alone was not the fix; a shortened timeout
test without the result-size change was not needed once attribution was
clean.
Verdict: the runner sets spark.task.maxDirectResultSize=512MB, so task
results return directly and the block fetch leaves the path. This is
framework plumbing: the SQL, the timing definition, and the outputs do
not change. Recorded here and in the runner's comments so a reviewer can
reproduce the failure by removing the line.

## D4. Co-tenant load and the restarted VM are recorded, not hidden

During the first Spark attempts the VM carried another heavy workload
(load average 4.86 on 4 cores; the Spark JVM received 0.12 core-seconds
in a 10 second window at one measurement) and the VM later restarted,
wiping /tmp. Early Spark timings from that window were discarded as
measurement conditions, not results; the protocol runs were re-taken on
a quiet box (load under 1.0 at start). The discarded run log is not kept
because those runs never completed a cell; the stall evidence is in D3.

## D5. dbt-duckdb unique_key: confirmed by test, no strategy switch

The pack marked dbt-duckdb's incremental unique_key support unverified
(N-08). Before building on it, a throwaway dbt project ran an
incremental model with unique_key='order_date' twice: after the source
changed one value and added one key, the second run replaced the changed
value, added the new key, and produced no duplicates. Verdict: H4 and H6
are tested against unique_key as designed; no substitute strategy was
needed. (If it had failed, the fallback was a delete-and-reload model on
the affected dates, documented the same way.)

## D6. Staging models are views; intermediates and marts are tables

Staging as views costs nothing to rebuild when the late delta arrives
(the view definition is recreated with the delta variables), which is
what scenarios S2 and S3 exercise. Intermediates and marts are tables so
dbt's per-model execution times measure real work and so the checksum
exports read materialized outputs.

## D7. The dbt dependency hint for delta_dates

dbt cannot statically infer a ref() inside an is_incremental() block; on
the first true incremental run, compilation of daily_sales and
ranked_sales failed with that exact error. The fix is dbt's documented
one: a "-- depends_on: {{ ref('delta_dates') }}" hint at the top of both
models. The SQL logic is unchanged; the parity script strips the hint
before diffing, and parity still passes.

## D8. Repository licence is Apache-2.0

The research chat proposed MIT. The programme standard is Apache-2.0,
which binds; the repository is Apache-2.0.
