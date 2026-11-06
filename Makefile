PY ?= python3
SF ?= 0.1
CHILDREN ?= 10

.PHONY: data delta run ci-check reproduce

data:
	$(PY) data/gen/generate.py --sf $(SF) $(if $(filter 10,$(SF)),--children $(CHILDREN),)
	$(PY) data/gen/synth.py --sf $(SF)

delta:
	$(PY) data/gen/synth.py --sf $(SF)

run:
	$(PY) src/run_duckdb.py --sf $(SF) --runs 5
	$(PY) src/run_spark.py --sf $(SF) --runs 5
	$(PY) src/run_dbt.py --sf $(SF) --runs 5
	$(PY) src/run_incremental.py --sf $(SF)
	$(PY) src/collect_checksums.py --sf $(SF)

# CI gate (U-10): SF0.1, one run per arm, all checksums must match the
# committed expected values and each other.
ci-check:
	$(PY) data/gen/generate.py --sf 0.1
	$(PY) data/gen/synth.py --sf 0.1
	$(PY) src/run_duckdb.py --sf 0.1 --runs 1
	$(PY) src/run_spark.py --sf 0.1 --runs 1
	$(PY) src/run_dbt.py --sf 0.1 --runs 1
	$(PY) src/run_incremental.py --sf 0.1
	$(PY) src/inject.py --sf 0.1
	$(PY) src/gates.py --sf 0.1
	$(PY) src/collect_checksums.py --sf 0.1
	$(PY) src/check_expected.py

reproduce: data run
	$(PY) src/make_results.py
