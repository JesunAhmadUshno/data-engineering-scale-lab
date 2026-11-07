"""Assert-based check of the hypothesis decision rules in make_results.py.

Two parts:
1. Known answer: the committed logs give the committed verdicts and totals.
2. Rule edges: small synthetic inputs drive each rule to its other branches
   (Partially supported, Refuted), so a broken rule cannot pass silently.

Reads results/*.jsonl and checksums.json, writes nothing, needs no data
generation, duckdb or Spark. Runs in well under a second.

Usage:
    python src/check_results.py
"""

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESULTS  # noqa: E402
from make_results import evaluate, load_jsonl, mulberry32  # noqa: E402

run_log = load_jsonl(RESULTS / "run_log.jsonl")
checks = json.loads((RESULTS / "checksums.json").read_text())
gates = load_jsonl(RESULTS / "gate_log.jsonl")
incr = load_jsonl(RESULTS / "incremental_log.jsonl")


def verdicts(rl=run_log, ch=checks, ga=gates, inc=incr):
    return {h: v for h, (v, _) in evaluate(rl, ch, ga, inc)["verdicts"].items()}


# ---- 1. known answer -------------------------------------------------------
ev = evaluate(run_log, checks, gates, incr)
assert verdicts() == {"H1": "Supported", "H2": "Not yet measured", "H3": "Supported",
                      "H4": "Supported", "H5": "Supported", "H6": "Not yet measured"}, verdicts()
r01, d01, s01 = ev["total_ratio"](0.1)
r1, d1, s1 = ev["total_ratio"](1)
assert (round(d01, 2), round(s01, 2), round(r01, 3)) == (1.48, 11.86, 0.125)
assert (round(d1, 2), round(s1, 2), round(r1, 3)) == (16.27, 100.59, 0.162)
assert round(ev["savings"][0.1]["saving_pct"], 1) == 23.2
assert round(ev["savings"][1]["saving_pct"], 1) == 70.5
assert ev["total_caught"] == 10 and ev["crit_missed"] == []
assert "best possible verdict is Partially supported" in ev["verdicts"]["H6"][1]
lo, hi = ev["boot"][1]["total"]
assert lo < r1 < hi, (lo, r1, hi)
# Same PRNG stream as site/src/lab.js (values printed by node for seed 20261106).
rand = mulberry32(20261106)
assert [rand(), rand(), rand()] == [0.01353957294486463, 0.8884504192974418, 0.7106646823231131]

# ---- 2. rule edges -----------------------------------------------------------
# H1: slow DuckDB at SF1 only -> Partially supported; at both -> Refuted.
def scaled(factor_by_sf):
    out = []
    for r in run_log:
        r = dict(r)
        if r["arm"] == "duckdb" and r["sf"] in factor_by_sf and r["seconds"] is not None:
            r["seconds"] *= factor_by_sf[r["sf"]]
        out.append(r)
    return out


assert verdicts(rl=scaled({1: 10}))["H1"] == "Partially supported"
assert verdicts(rl=scaled({0.1: 10, 1: 10}))["H1"] == "Refuted"

# H2: add SF10 rows where Spark wins t2 by 2x -> Supported; by 1.2x -> Refuted.
def with_sf10(spark_t2, duck_t2):
    extra = []
    for t in ("t1", "t2", "t3", "t4", "t5", "t6"):
        for run in range(1, 6):
            extra.append({"arm": "spark", "sf": 10, "transformation": t, "run": run, "seconds": 10.0})
            extra.append({"arm": "duckdb", "sf": 10, "transformation": t, "run": run,
                          "seconds": duck_t2 if t == "t2" else 5.0})
    for e in extra:
        if e["arm"] == "spark" and e["transformation"] == "t2":
            e["seconds"] = spark_t2
    return run_log + extra


assert verdicts(rl=with_sf10(10.0, 20.0))["H2"] == "Supported"
assert verdicts(rl=with_sf10(10.0, 12.0))["H2"] == "Refuted"

# H3: one disagreeing cell -> Refuted.
bad = copy.deepcopy(checks)
next(iter(bad["verdicts"].values()))["arms_agree_run1"] = False
assert verdicts(ch=bad)["H3"] == "Refuted"

# H4 and H5: a changed S2 checksum fails H4 and, through F08, H5.
bad_incr = copy.deepcopy(incr)
next(r for r in bad_incr if r["scenario"] == "S2")["checksums"]["t3"]["sha256"] = "0" * 64
v = verdicts(inc=bad_incr)
assert v["H4"] == "Refuted" and v["H5"] == "Refuted", v

# H5: a missed critical gate fault -> Refuted even with 9 of 10 caught.
bad_gates = copy.deepcopy(gates)
next(r for r in bad_gates if r["scenario"] == "F01")["caught"] = False
assert verdicts(ga=bad_gates)["H5"] == "Refuted"

# H6: an SF10 saving above 50% with SF1 at 70.5% -> Partially supported.
def with_sf10_incr(full, inc):
    extra = [{"sf": 10, "scenario": s, "checksums": copy.deepcopy(incr[0]["checksums"])}
             for s in ("full_refresh", "S1", "S2", "S3", "S3b")]
    # Reuse SF0.1 checksums for every SF10 row so H4 still holds.
    extra[0]["model_seconds"] = {"daily_sales": full, "ranked_sales": full}
    extra[3]["model_seconds"] = {"daily_sales": inc, "ranked_sales": inc}
    return incr + extra


assert verdicts(inc=with_sf10_incr(10.0, 2.0))["H6"] == "Partially supported"
assert verdicts(inc=with_sf10_incr(10.0, 8.0))["H6"] == "Refuted"

print("decision rules ok: H1-H6 match the committed verdicts and every rule branch was exercised")
