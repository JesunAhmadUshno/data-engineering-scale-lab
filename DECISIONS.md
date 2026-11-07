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

## D9. The .gitignore data/ rule hid the generator sources; CI caught it

The first .gitignore excluded the whole data/ tree, which silently kept
data/gen/generate.py and data/gen/synth.py out of every commit. Local
runs were unaffected, so the gap surfaced only in CI, where the SF0.1
gate failed with "can't open file data/gen/generate.py". The rule now
ignores only the generated scale directories (data/sf*/, data/faults/).
The same fix commit first swept in a DuckDB write-ahead log from the
SF10 generator's temp directory; GitHub push protection blocked that
push (a scanner pattern match inside a binary temp file, not a real
credential; nothing was uploaded). The temp patterns (data/.tmp*/,
*.duckdb.wal) are ignored now, and the commit was amended before push.
CI run 42295558072 is green on Python 3.11 and 3.12.

## D17. Restart and load log for the SF10 dbt sequence

The host restarted at about 22:09, 02:08, 04:00, and 06:03 UTC during
this build (and once earlier in the programme), and the co-tenant
workload peaked at load average 28 on the 4-core machine during build
4's first attempt, which the 06:03 restart then killed at 3.6 GB of
4.15 GB written. Build 4 was relaunched alone. Completed builds 1 to 3
were already verified in the run log and are unaffected. None of this
changes any measurement definition; it is recorded because the dbt
SF10 model times carry visibly larger spread than the other arms for
exactly these reasons, and AUDIT.md names it as the cause.

## D16. Incremental harness: phases selectable, rows written per phase

The incremental harness originally appended all of a scale's rows only
after its last phase, so a host restart (four so far in this build)
would have discarded hours of completed SF10 phases. It now accepts
--only with a phase subset (the phases are independent given the delta
files) and writes each phase's row to results/incremental_log.jsonl as
the phase completes. What is measured does not change; when a phase is
recorded changes, and the SF10 phases can run as separate processes
like the dbt runs (D15).

## D15. dbt SF10 runs execute one per process; earlier dbt SF10 rows reset

The VM restarted a fourth time at about 04:00 UTC on 2026-11-07,
killing the D14 build 1 after the largest model had completed (its
database file reached 2.71 GB). Long chains do not survive this host's
restart pattern, so the dbt runner gained a --start-run option and the
five SF10 builds run as five separate processes, each verified in the
run log before the next starts. A restart can now cost at most one
build. Before the sequence started, every dbt SF10 row from the
incomplete attempts (D13) was removed from results/run_log.jsonl and
the partial build files and exports were deleted, so the log will hold
exactly one set of five runs, all under the D14 settings. This
supersedes the removal procedure described in D13; the reason for the
removals is the same and is recorded in both places.

## D14. dbt SF10 runs use one thread and a 1.8 GB cap, by environment

After the D13 relaunch, the dbt process died silently a second time
during the same model (int_lineitem_orders, the 60 million row join) in
its first build, with the same leaked-semaphore warning and no error
message. Two silent kills in the same model under memory contention
(load 10 to 18, a co-tenant workload holding gigabytes) are treated as
an out-of-memory pattern, not chance. The profile now takes threads and
memory_limit from the environment with the original values as defaults
(threads 2, 2.2 GB, the settings SF0.1 and SF1 were measured under).
The SF10 dbt runs and the SF10 incremental harness run with
DBT_THREADS=1 and DBT_MEMORY_LIMIT=1.8GB. Why this does not bend the
study: dbt times are never ratioed against engine times or across
scales; H4 is checksums, which settings cannot change; H6 compares
full-refresh and incremental model times inside SF10, both under the
new settings. The change and its reason are recorded here and in
METHODS.md; the settings in force are part of the run record.

## D13. Third VM restart during dbt SF10 build 3; dbt arm relaunched whole

The VM restarted a third time at about 02:08 UTC on 2026-11-07, during
dbt build 3 of 5 at SF10 (its database file had reached 3.86 GB of a
4.15 GB final size; no run 3 row was logged). The partial build file and
its write-ahead log were deleted. The dbt runner rebuilds every run
from scratch by design, so the arm was relaunched whole. The relaunch
then lost its own build 3 at 03:20 UTC: the dbt process died silently
during the int_lineitem_orders model with only a multiprocessing
leaked-semaphore warning in its log, which fits a kernel out-of-memory
kill during a contention peak (the dbt profile caps DuckDB at 2.2 GB;
disk had 63 GB free; the co-tenant workload was at load 13 to 18 in
that window). The arm was relaunched a second time. When a complete
five-run dbt SF10 set exists, every dbt SF10 row from the incomplete
attempts will be removed from results/run_log.jsonl, leaving the
completed session's single set of five runs, whose exports overwrite
the same output paths the checksums are collected from. The removal
will be verified by row counts per cell before the results are
generated, the same procedure as D11.

## D12. Second VM restart during the Spark SF10 warm-up

The VM restarted at about 22:09 UTC on 2026-11-06, killing the chain
during the Spark SF10 warm-up (T1 and T2 warm-up outputs written, no
measured Spark row logged). The DuckDB SF10 arm was already complete
and is unaffected. The remaining steps (Spark, dbt, incremental,
checksum collection) were relaunched as a reduced chain. The run log
therefore holds two Spark SF10 setup rows: the first session, which the
restart killed, and the completed session, whose setup figure is the
one the results generator reports. Both rows stay in the log; this note
is their explanation. The relaunched chain later stopped again between
the Spark arm's last logged run and the dbt step, with no error in its
log; the cause was not established. The dbt, incremental, and checksum
steps were relaunched as a third chain. No measurement was lost in
either interruption: every completed cell was already in the run log
and its output files on disk.

## D11. Orphaned runner rows from the first SF10 chain (removal recorded)

The first SF10 chain was stopped by killing its shell script. Killing
the script did not kill its current child: by then generation had
finished and an orphaned run_duckdb.py kept running, logging a setup
row and run 1 T1 to T4 (timestamps 21:18:07 to 21:23:39 UTC) before it
died when its input directory was removed. The relaunched chain logged
its own SF10 rows from 21:28:33 UTC. The five orphan rows were removed
from results/run_log.jsonl after the DuckDB arm finished, identified by
their timestamp window; no other rows were touched, and the orphan's
partial output files were overwritten by the relaunched runner in the
same run directory before any checksum was collected. Recorded here so
the run log's edit is never a silent one.

## D10. SF10 generation: chunked route verified, one false alarm

SF10 generation was first launched without the --children flag, so it
ran as a single dbgen call. Its first part file held the full 59,986,052
lineitem rows, which looked like a slicing failure and the run was
stopped and its output deleted. A controlled test then showed the
chunked call does slice (dbgen sf=0.1, children=4: step 0 holds 150,390
lineitem rows of 600,572) and that each step must use a fresh database
file, because a second call appends to the same database. Generation
was relaunched with --children 10 as registered. The deleted output was
regenerated deterministically; no measurement had used it. The single
call also proved a full SF10 dbgen fits this machine inside the memory
cap, which is recorded here as an observation, not used.

## D18. SF10 checksum collection: disk pressure failure, scratch cleanup, per-arm persistence

The first two SF10 checksum collection attempts died on the DuckDB run 1
T2 cell with "IO Error: Could not truncate file ... Disk quota
exceeded" from the canonical checksum export. A foreground reproduction
isolated it: the same export succeeded minutes earlier for the 60M-row
T4 mart inside the incremental harness, and plain 6 GB writes to the
same directories succeeded, so it was not a fixed per-directory quota.
At failure time the VM disk stood at 162 GB of 200 GB used and this
repo's outputs had grown to about 104 GB, including 29 GB of
incremental work databases, 6.9 GB of Spark shuffle scratch, and 2.1 GB
of materialized appended inputs. The fix was to delete that regenerable
scratch (outputs/.incr_work, outputs/.spark_local, outputs/.appended)
after every result it held was already recorded in the run and
incremental logs; the export then ran to completion. No measured output
was deleted: the arm outputs under outputs/duckdb, outputs/spark,
outputs/dbt and the mart exports under outputs/dbt_incremental are the
checksum sources and were kept.

A VM restart at about 10:04 UTC on 2026-11-07 then killed the third
collection attempt during Spark run 5, before checksums.json was
written, so that attempt's SF10 records were lost (its digests survive
only as 12-character prefixes in the attempt log). collect_checksums.py
now persists checksums.json after every arm and accepts an --arms
subset, so a restart loses at most the arm in progress. The digest
computation itself is unchanged.
