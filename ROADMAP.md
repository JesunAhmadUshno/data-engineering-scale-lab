# Roadmap

What remains, in evidence order. Nothing here is claimed until it is
measured and committed the same way as the current results.

1. SF30 on a machine that can hold it. The ladder's top point was cut
   before preregistration as a machine limit (7.7 GiB RAM against a 15
   to 18 GB generation peak). On a 32 GB machine the same code runs the
   same protocol at SF30, which is where H2's crossover, if it exists
   for this workload, is most likely to appear.
2. A second reviewer pass (research pack U-12). Until a reviewer who is
   not the author is named in REVIEW.md, the study carries the pack's
   UNVERIFIED label for review status.
3. A repeated-measures pass for the incremental economics: H6 rests on
   one S3 run per scale. Five repeated incremental cycles per scale
   would put a spread on the saving figures.
4. A second dataset family (for example a wider, sparser schema) to test
   whether the regime map moves. The current claims are for this
   workload shape only.
5. Beam as a fourth arm, if a local Beam runner can be stood up at zero
   spend on this machine class. The gap register names Beam beside
   Spark; this study covers Spark only.
6. Partitioned Parquet inputs (by date) as a variant arm, to measure how
   much of DuckDB's SF10 behaviour is scan pruning rather than engine
   speed. The current arms all read unpartitioned files by design.
