# Changelog

All notable changes to this project. Format: Keep a Changelog 1.1.
Versions follow Semantic Versioning; no release is tagged yet.

## [Unreleased]

### Changed
- 2026-11-08: Adopted the portfolio standard v2. README opens with the
  question, headline, field, job family and verdict (Functional). The
  new REPORT.md scores every hypothesis and names the misses and the
  protocol breaches; ROADMAP.md and docs/research-review.md moved into
  it, and the scores they and AUDIT.md carried left the public repo
  (scoring is internal). The lock is tagged proposal-v1 on 0e0c035, and
  a test fails if one byte of the locked PREREG.md text changes. CI
  checks that the generated results regenerate unchanged and builds the
  dashboard; CodeQL and Dependabot added; main protected.

### Added
- 2026-11-07: SF10 measured: five runs per arm, checksums agree in 18
  of 18 cells, the incremental scenarios equal full refresh at every
  scale; DECISIONS.md D14 to D18.
- 2026-11-07: Live dashboard in site/ and its Pages workflow; the build
  first checks every browser computation against results/verdicts.json.
- 2026-11-07 (from the self-review, now in REPORT.md): bootstrap 95%
  intervals for every D/S ratio and total; PREREG.md Deviation 2 for the
  two sub-150 ms DuckDB cells over the 30% CV line; the generated
  RESULTS.md, results/results.md, run_log.md, results/verdicts.json and
  per-arm checksum files promised by PREREG.md Section 7; AUDIT.md;
  src/check_results.py for the decision rules in `make check` and CI;
  README.md.
- 2026-11-06: SF0.1 and SF1 measured; build of the three arms, the gate
  and incremental harnesses, the SQL parity check and CI.
- 2026-11-06: Pre-registration (0e0c035), before any code or data.

### Fixed
- 2026-11-07 (from the self-review): H6 was reported as "Not yet
  measured", hiding that SF1's 70.5% already broke its small-scale
  clause; make_results.py now says so. After the SF10 merge it printed
  a stale "SF10 was not run" section and mislabelled the SF10 high-CV
  cells as timer jitter; both are now driven by the data, and
  src/check_results.py pins the SF10 known answers. The dbt run log and
  per-user id file are no longer tracked.
- 2026-11-06: the .gitignore data/ rule hid the generator sources
  (DECISIONS.md D9).
