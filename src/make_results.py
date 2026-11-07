"""Generate every published results file from the recorded evidence.

Inputs: results/run_log.jsonl, results/checksums.json,
results/gate_log.jsonl, results/incremental_log.jsonl,
results/versions.json, and the data manifests under data/.

Outputs:
- results/results.md          full tables and verdicts
- results/checksums/<arm>/<scale>/<transformation>.sha256
- run_log.md                  the U-08 run log table
- RESULTS.md                  generated summary at the repository root
- results/verdicts.json       machine-readable verdicts and totals (the site's
                              known-answer check compares against it)

Hypothesis decision rules are the operationalization fixed in METHODS.md
before the SF1 and SF10 runs were seen.

Usage:
    python src/make_results.py
"""

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESULTS, ROOT, sf_label  # noqa: E402
from spec import TRANSFORMATIONS  # noqa: E402

SCALES = [0.1, 1, 10]
TKEYS = [t["key"] for t in TRANSFORMATIONS]


def load_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def fmt(x, digits=2):
    if x is None:
        return "n/a"
    return f"{x:.{digits}f}"


def cell_stats(run_log):
    """(arm, sf, t) -> dict(mean, sd, cv, n, values)."""
    agg = defaultdict(list)
    for r in run_log:
        if r["transformation"] in TKEYS and r["seconds"] is not None:
            agg[(r["arm"], r["sf"], r["transformation"])].append(r["seconds"])
    out = {}
    for k, v in agg.items():
        mean = statistics.mean(v)
        sd = statistics.stdev(v) if len(v) > 1 else 0.0
        out[k] = {"mean": mean, "sd": sd, "cv": (100 * sd / mean if mean else 0.0),
                  "n": len(v), "values": v}
    return out


def setup_seconds(run_log):
    out = {}
    for r in run_log:
        if r["transformation"] == "setup":
            out[(r["arm"], r["sf"])] = r["seconds"]
    return out


def dbt_wall(run_log):
    out = {}
    for r in run_log:
        if r["transformation"] == "build_wall":
            out.setdefault(r["sf"], []).append(r["seconds"])
    return {sf: statistics.mean(v) for sf, v in out.items()}


def mulberry32(seed):
    """Seeded 32-bit PRNG, bit-for-bit the same as the site's JavaScript copy
    (site/src/lab.js), so the bootstrap intervals match in both places."""
    M = 0xFFFFFFFF
    state = seed & M

    def rand():
        nonlocal state
        state = (state + 0x6D2B79F5) & M
        t = ((state ^ (state >> 15)) * (state | 1)) & M
        t = ((t + (((t ^ (t >> 7)) * (t | 61)) & M)) & M) ^ t
        return ((t ^ (t >> 14)) & M) / 4294967296

    return rand


BOOT_B, BOOT_SEED = 2000, 20261106


def bootstrap_ratios(stats, sf, B=BOOT_B, seed=BOOT_SEED):
    """Percentile 95% intervals for each D/S ratio and the total ratio at one
    scale: resample the five runs of every (arm, transformation) cell with
    replacement, B times. With n=5 these intervals are rough; they are shown
    so the H1 margins carry their run-to-run spread."""
    rand = mulberry32(seed)
    per_t = {t: [] for t in TKEYS}
    totals = []

    def resample_mean(v):
        return sum(v[int(rand() * len(v))] for _ in v) / len(v)

    for _ in range(B):
        sd = ss = 0.0
        for t in TKEYS:
            d = resample_mean(stats[("duckdb", sf, t)]["values"])
            s = resample_mean(stats[("spark", sf, t)]["values"])
            per_t[t].append(d / s)
            sd += d
            ss += s
        totals.append(sd / ss)

    def ci(xs):
        xs = sorted(xs)
        return [xs[round(0.025 * (len(xs) - 1))], xs[round(0.975 * (len(xs) - 1))]]

    return {"total": ci(totals), **{t: ci(per_t[t]) for t in TKEYS}}


def evaluate(run_log, checks, gates, incr):
    """Apply the METHODS.md decision rules. Pure: reads nothing, writes nothing."""
    stats = cell_stats(run_log)

    def total_ratio(sf):
        d = sum(stats[("duckdb", sf, t)]["mean"] for t in TKEYS if ("duckdb", sf, t) in stats)
        s = sum(stats[("spark", sf, t)]["mean"] for t in TKEYS if ("spark", sf, t) in stats)
        return (d / s) if s else None, d, s

    tested_scales = sorted({sf for (arm, sf, t) in stats if arm == "duckdb"})
    spark_scales = sorted({sf for (arm, sf, t) in stats if arm == "spark"})

    # ---- hypothesis verdicts ------------------------------------------
    verdicts = {}

    if 0.1 in spark_scales and 1 in spark_scales:
        r01, _, _ = total_ratio(0.1)
        r1, _, _ = total_ratio(1)
        if r01 <= 0.5 and r1 <= 0.5:
            verdicts["H1"] = ("Supported", f"total workload ratio {fmt(r01,3)} at SF0.1 and {fmt(r1,3)} at SF1, both at most 0.5")
        elif r01 <= 0.5 or r1 <= 0.5:
            verdicts["H1"] = ("Partially supported", f"total workload ratio {fmt(r01,3)} at SF0.1 and {fmt(r1,3)} at SF1; the 0.5 line is met at one scale only")
        else:
            verdicts["H1"] = ("Refuted", f"total workload ratio {fmt(r01,3)} at SF0.1 and {fmt(r1,3)} at SF1; neither meets 0.5")
    else:
        verdicts["H1"] = ("Not yet measured", "Spark runs are missing at SF0.1 or SF1")

    if 10 in spark_scales and 10 in tested_scales:
        ratios10 = {}
        for t in TKEYS:
            d = stats.get(("duckdb", 10, t))
            s = stats.get(("spark", 10, t))
            if d and s:
                ratios10[t] = d["mean"] / s["mean"]
        best = max(ratios10.values()) if ratios10 else None
        if best is not None and best >= 1.5:
            bt = max(ratios10, key=ratios10.get)
            verdicts["H2"] = ("Supported", f"at SF10, {bt} ratio {fmt(best,3)} reaches the 1.5 line")
        else:
            verdicts["H2"] = ("Refuted", f"at SF10 no transformation reaches a 1.5 ratio (best {fmt(best,3)}); no crossover observed inside the ladder tested")
    else:
        verdicts["H2"] = ("Not yet measured", "SF10 was not completed on this machine; that is not H2 being false")

    cv = checks.get("verdicts", {})
    if cv:
        agree = all(v["arms_agree_run1"] for v in cv.values())
        det = all(v.get("deterministic_run5") in (True, None) for v in cv.values())
        verdicts["H3"] = ("Supported" if agree else "Refuted",
                          f"{sum(1 for v in cv.values() if v['arms_agree_run1'])} of {len(cv)} (scale, transformation) cells agree across all three arms on run 1; run 5 determinism {'holds everywhere' if det else 'has exceptions named in results/results.md'}")
    else:
        verdicts["H3"] = ("Not yet measured", "no checksum records")

    incr_by_sf = defaultdict(dict)
    for row in incr:
        incr_by_sf[row["sf"]][row["scenario"]] = row
    h4_ok, h4_detail = True, []
    savings = {}
    for sf, scen in sorted(incr_by_sf.items()):
        full = scen.get("full_refresh")
        if not full:
            continue
        for name in ("S1", "S2", "S3", "S3b"):
            row = scen.get(name)
            if row is None:
                h4_ok = False
                h4_detail.append(f"SF{sf_label(sf)} {name} missing")
                continue
            for t in ("t3", "t4"):
                if row["checksums"][t]["sha256"] != full["checksums"][t]["sha256"]:
                    h4_ok = False
                    h4_detail.append(f"SF{sf_label(sf)} {name} {t} differs from full refresh")
        ms_full = full.get("model_seconds") or {}
        s3 = scen.get("S3") or {}
        ms_inc = s3.get("model_seconds") or {}
        if ms_full and ms_inc and all(ms_full.get(m) is not None and ms_inc.get(m) is not None for m in ("daily_sales", "ranked_sales")):
            f = sum(ms_full[m] for m in ("daily_sales", "ranked_sales"))
            i = sum(ms_inc[m] for m in ("daily_sales", "ranked_sales"))
            if f:
                savings[sf] = {"full": f, "incremental": i, "saving_pct": 100 * (f - i) / f}
    verdicts["H4"] = ("Supported" if h4_ok and incr_by_sf else "Refuted" if incr_by_sf else "Not yet measured",
                      "every scenario checksum equals the full-refresh comparator at every tested scale" if h4_ok and incr_by_sf else "; ".join(h4_detail) or "no incremental runs recorded")

    gate_by_name = {r["scenario"]: r for r in gates}
    caught_names, missed_critical = [], []
    for fname in ("F01", "F02", "F03", "F04", "F05", "F06", "F07", "F09", "F10"):
        row = gate_by_name.get(fname)
        if row and row.get("caught"):
            caught_names.append(fname)
        elif row:
            missed_critical.append(fname) if row.get("critical") else None
    f08_caught = verdicts["H4"][0] == "Supported"
    if f08_caught:
        caught_names.append("F08")
    total_caught = len(caught_names)
    crit_missed = [f for f in missed_critical]
    if not f08_caught and "H4" in verdicts and incr_by_sf:
        crit_missed.append("F08")
    if gates:
        if total_caught / 10 >= 0.5 and not crit_missed:
            verdicts["H5"] = ("Supported", f"{total_caught} of 10 faults caught; zero missed critical faults")
        else:
            verdicts["H5"] = ("Refuted", f"{total_caught} of 10 faults caught; missed critical faults: {crit_missed or 'none'} (the hypothesis needs at least 50 percent caught and zero critical misses)")
    else:
        verdicts["H5"] = ("Not yet measured", "no gate runs recorded")

    if all(sf in savings for sf in (0.1, 1, 10)):
        s10 = savings[10]["saving_pct"]
        small = [savings[0.1]["saving_pct"], savings[1]["saving_pct"]]
        if s10 > 50 and all(x <= 50 for x in small):
            verdicts["H6"] = ("Supported", f"incremental saving {fmt(s10,1)}% at SF10, {fmt(small[0],1)}% at SF0.1 and {fmt(small[1],1)}% at SF1")
        elif s10 > 50:
            verdicts["H6"] = ("Partially supported", f"incremental saving {fmt(s10,1)}% at SF10, but a small scale also exceeds 50% (SF0.1 {fmt(small[0],1)}%, SF1 {fmt(small[1],1)}%)")
        else:
            verdicts["H6"] = ("Refuted", f"incremental saving at SF10 is {fmt(s10,1)}%, not above 50%")
    elif 10 in savings:
        verdicts["H6"] = ("Inconclusive", "SF10 saving is recorded but a small-scale saving is missing")
    else:
        over = [f"SF{sf_label(sf)} {fmt(savings[sf]['saving_pct'], 1)}%" for sf in (0.1, 1)
                if sf in savings and savings[sf]["saving_pct"] > 50]
        why = "no SF10 incremental timing recorded"
        if over:
            why += (f"; the small-scale clause (saving at most 50% at SF0.1 and SF1) already fails"
                    f" ({', '.join(over)}), so once SF10 is run the best possible verdict is"
                    f" Partially supported, never Supported")
        verdicts["H6"] = ("Not yet measured", why)

    boot = {sf: bootstrap_ratios(stats, sf) for sf in spark_scales
            if all(("duckdb", sf, t) in stats and ("spark", sf, t) in stats for t in TKEYS)}
    return {"verdicts": verdicts, "stats": stats, "savings": savings, "incr_by_sf": incr_by_sf,
            "gate_by_name": gate_by_name, "f08_caught": f08_caught, "total_caught": total_caught,
            "crit_missed": crit_missed, "tested_scales": tested_scales, "spark_scales": spark_scales,
            "total_ratio": total_ratio, "boot": boot, "cv": cv}


def main():
    run_log = load_jsonl(RESULTS / "run_log.jsonl")
    checks = json.loads((RESULTS / "checksums.json").read_text()) if (RESULTS / "checksums.json").exists() else {"records": [], "verdicts": {}}
    gates = load_jsonl(RESULTS / "gate_log.jsonl")
    incr = load_jsonl(RESULTS / "incremental_log.jsonl")
    versions = json.loads((RESULTS / "versions.json").read_text()) if (RESULTS / "versions.json").exists() else {}
    ev = evaluate(run_log, checks, gates, incr)
    verdicts, stats, savings, incr_by_sf = ev["verdicts"], ev["stats"], ev["savings"], ev["incr_by_sf"]
    gate_by_name, f08_caught, cv = ev["gate_by_name"], ev["f08_caught"], ev["cv"]
    tested_scales, spark_scales, total_ratio, boot = ev["tested_scales"], ev["spark_scales"], ev["total_ratio"], ev["boot"]
    setups = setup_seconds(run_log)
    walls = dbt_wall(run_log)

    def timing_table(sf):
        lines = [f"| Transformation | DuckDB mean (SD, CV) | Spark mean (SD, CV) | Ratio D/S | dbt model mean (SD) |",
                 "| --- | --- | --- | --- | --- |"]
        for t in TKEYS:
            d = stats.get(("duckdb", sf, t))
            s = stats.get(("spark", sf, t))
            b = stats.get(("dbt", sf, t))
            ratio = (d["mean"] / s["mean"]) if d and s else None
            lines.append(
                f"| {t} | {fmt(d['mean']) if d else 'n/a'} ({fmt(d['sd']) if d else '-'}, {fmt(d['cv'],0) if d else '-'}%) "
                f"| {fmt(s['mean']) if s else 'n/a'} ({fmt(s['sd']) if s else '-'}, {fmt(s['cv'],0) if s else '-'}%) "
                f"| {fmt(ratio, 3)} | {fmt(b['mean']) if b else 'n/a'} ({fmt(b['sd']) if b else '-'}) |")
        return lines


    # ---- checksum files (U-08 layout) ----------------------------------
    for rec in checks["records"]:
        if rec["run"] == 1 and not rec["partial"]:
            dest = (RESULTS / "checksums" / rec["arm"] / f"sf{sf_label(rec['sf'])}"
                    / f"{rec['transformation']}.sha256")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(rec["sha256"] + "\n")

    # ---- run_log.md (U-08) ---------------------------------------------
    digest1 = {}
    for rec in checks["records"]:
        if rec["run"] == 1:
            digest1[(rec["arm"], rec["sf"], rec["transformation"])] = rec["sha256"][:16]
    rl = ["# Run log", "",
          "Generated by src/make_results.py from results/run_log.jsonl. "
          "Cost is 0 dollars for every run (local, zero spend).", "",
          "| Date | Arm | Scale | Transformation | Run | Seconds | Cores | RAM GiB | Checksum (run 1, first 16) | Cost USD |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in run_log:
        m = r.get("machine") or {}
        rl.append(f"| {r.get('ts','')[:10]} | {r['arm']} | {sf_label(r['sf'])} | {r['transformation']} | {r['run']} "
                  f"| {fmt(r['seconds'], 3)} | {m.get('cores','')} | {m.get('ram_gib','')} "
                  f"| {digest1.get((r['arm'], r['sf'], r['transformation']), '') if r['run'] == 1 else ''} | 0 |")
    (ROOT / "run_log.md").write_text("\n".join(rl) + "\n")

    # ---- results/results.md --------------------------------------------
    out = ["# Results (generated)", "",
           "Generated by src/make_results.py from the run log, the checksum "
           "records, the gate log, and the incremental log. Never hand-edited. "
           "All data derived from TPC-H; see LICENSES.md.", ""]
    out += ["## Versions", ""]
    for k in ("python", "duckdb", "dbt_core", "dbt_duckdb", "spark", "java"):
        if k in versions:
            out.append(f"- {k}: {versions[k]}")
    out += ["", "## Setup overhead (seconds, reported separately)", "",
            "| Scale | DuckDB connect and views | Spark JVM, session, first action | dbt build wall (mean of 5, includes dbt startup) |",
            "| --- | --- | --- | --- |"]
    for sf in SCALES:
        out.append(f"| SF{sf_label(sf)} | {fmt(setups.get(('duckdb', sf)))} | {fmt(setups.get(('spark', sf)))} | {fmt(walls.get(sf))} |")
    for sf in SCALES:
        if sf not in tested_scales:
            out += ["", f"## SF{sf_label(sf)}", "", "Not tested on this machine (see AUDIT.md)."]
            continue
        tr, td, ts_ = total_ratio(sf)
        out += ["", f"## SF{sf_label(sf)} timings (seconds, 5 runs, one warm-up pass)", ""]
        out += timing_table(sf)
        if sf in boot:
            out += ["", f"Bootstrap 95% intervals for D/S ({BOOT_B} resamples of the five runs, seed {BOOT_SEED}; rough at n=5): "
                    + "; ".join(f"{t} {fmt(boot[sf][t][0], 3)} to {fmt(boot[sf][t][1], 3)}" for t in TKEYS)
                    + f"; total {fmt(boot[sf]['total'][0], 3)} to {fmt(boot[sf]['total'][1], 3)}."]
            cv_flag = [f"{arm} {t} ({fmt(stats[(arm, sf, t)]['cv'], 0)}%)" for arm in ("duckdb", "spark") for t in TKEYS
                       if (arm, sf, t) in stats and stats[(arm, sf, t)]["cv"] > 30]
            if cv_flag:
                out += ["", f"Cells above the pre-registered 30% CV line: {', '.join(cv_flag)}. "
                        + ("Recorded as PREREG.md Deviation 2 (every run in these cells is under 150 ms, where timer and scheduler jitter is of the same order as the measurement)."
                           if sf in (0.1, 1) else
                           "Cause on record: co-tenant load on the same VM and VM restarts during the SF10 sequence (AUDIT.md, DECISIONS.md D17); the verdicts do not turn on these cells.")]
        out += ["", f"Total workload: DuckDB {fmt(td)} s, Spark {fmt(ts_)} s, ratio {fmt(tr, 3)}. "
                "dbt model times are dbt execution_time per model; they are not ratioed against the engine times."]
    out += ["", "## Checksum verdicts (H3 and determinism)", "",
            "| Cell | Arms agree on run 1 | Rows agree | Run 5 reproduces run 1 |",
            "| --- | --- | --- | --- |"]
    for k, v in sorted(cv.items()):
        out.append(f"| {k} | {v['arms_agree_run1']} | {v['rows_agree']} | {v.get('deterministic_run5')} |")
    out += ["", "## Incremental scenarios (H4) and savings (H6)", ""]
    for sf, scen in sorted(incr_by_sf.items()):
        full = scen.get("full_refresh", {})
        out.append(f"SF{sf_label(sf)}: full-refresh T3 { (full.get('checksums') or {}).get('t3', {}).get('sha256', '')[:12] }, "
                   f"T4 { (full.get('checksums') or {}).get('t4', {}).get('sha256', '')[:12] }.")
        for name in ("S1", "S2", "S3", "S3b"):
            row = scen.get(name)
            if row:
                eq = all(row["checksums"][t]["sha256"] == full["checksums"][t]["sha256"] for t in ("t3", "t4"))
                out.append(f"- {name}: T3 and T4 equal to full refresh: {eq}.")
        if sf in savings:
            sv = savings[sf]
            out.append(f"- H6 inputs: full-refresh T3+T4 model time {fmt(sv['full'])} s, incremental (S3) {fmt(sv['incremental'])} s, saving {fmt(sv['saving_pct'], 1)}%.")
    out += ["", "## Gate matrix (H5)", "",
            "| Fault | Critical | Gate that fired | Outcome |",
            "| --- | --- | --- | --- |"]
    fault_desc = {"F01": "duplicate primary key", "F02": "null primary key", "F03": "orphan foreign key",
                  "F04": "negative quantity", "F05": "bad date format", "F06": "price stored as a string",
                  "F07": "duplicate whole row", "F08": "late row with changed price (checksum gate)",
                  "F09": "missing column", "F10": "stale file"}
    for fname in ("F01", "F02", "F03", "F04", "F05", "F06", "F07", "F08", "F09", "F10"):
        if fname == "F08":
            out.append(f"| F08 | True | incremental checksum equality (Section 8) | {'caught' if f08_caught else 'missed'} |")
            continue
        row = gate_by_name.get(fname)
        if not row:
            out.append(f"| {fname} |  |  | not run |")
            continue
        fired = ", ".join(list(row.get("gate_failures", {}).keys()) + list(row.get("gate_warnings", {}).keys())) or "none"
        outcome = "caught (promotion blocked)" if row.get("caught") and fname != "F10" else ("caught (flagged stale, promoted)" if row.get("caught") else "missed")
        out.append(f"| {fname} ({fault_desc[fname]}) | {row.get('critical')} | {fired} | {outcome} |")
    out += ["", "## Hypothesis verdicts", ""]
    for h in ("H1", "H2", "H3", "H4", "H5", "H6"):
        v, why = verdicts[h]
        out.append(f"- {h}: **{v}**. {why}.")
    (RESULTS / "results.md").write_text("\n".join(out) + "\n")

    # ---- root RESULTS.md (summary) --------------------------------------
    s = ["# Results", "",
         "Generated by src/make_results.py. Full tables: results/results.md. "
         "Run log: run_log.md. All data derived from TPC-H.", "",
         "## Verdicts", ""]
    for h in ("H1", "H2", "H3", "H4", "H5", "H6"):
        v, why = verdicts[h]
        s.append(f"- {h}: **{v}**. {why}.")
    s += ["", "## Headline totals (sum of the six transformation means)", "",
          "| Scale | DuckDB total s | Spark total s | Ratio D/S | Bootstrap 95% interval |",
          "| --- | --- | --- | --- | --- |"]
    summary = {"generated_by": "src/make_results.py", "bootstrap": {"resamples": BOOT_B, "seed": BOOT_SEED},
               "verdicts": {h: {"verdict": v, "why": why} for h, (v, why) in verdicts.items()},
               "totals": {}, "incremental_saving_pct": {sf_label(sf): round(v["saving_pct"], 4) for sf, v in savings.items()},
               "faults_caught": ev["total_caught"], "critical_missed": ev["crit_missed"]}
    for sf in SCALES:
        if sf in tested_scales and sf in spark_scales:
            tr, td, ts_ = total_ratio(sf)
            b = boot.get(sf, {}).get("total")
            s.append(f"| SF{sf_label(sf)} | {fmt(td)} | {fmt(ts_)} | {fmt(tr, 3)} | {fmt(b[0], 3) + ' to ' + fmt(b[1], 3) if b else 'n/a'} |")
            summary["totals"][sf_label(sf)] = {"duckdb": round(td, 6), "spark": round(ts_, 6), "ratio": round(tr, 6),
                                               "ratio_ci95": [round(x, 6) for x in b] if b else None,
                                               "per_transformation_ci95": {t: [round(x, 6) for x in boot[sf][t]] for t in TKEYS} if sf in boot else None}
        else:
            s.append(f"| SF{sf_label(sf)} | not tested | not tested | n/a | n/a |")
    s += ["", "The intervals resample the five measured runs per cell; with n=5 they describe run-to-run spread on this machine, not a population.",
          ""]
    open_h = [h for h, (v, _) in verdicts.items() if v == "Not yet measured"]
    if open_h:
        s += ["## Not yet measured", "",
              f"{', '.join(open_h)} have no verdict yet. Under PREREG.md Section 2 the study does not pass until every hypothesis holds; it is incomplete, not failed.", ""]
    else:
        failed = [h for h, (v, _) in verdicts.items() if v != "Supported"]
        s += ["## Study status", "",
              f"Every hypothesis has a verdict. {', '.join(failed) or 'None'} did not come out Supported, so under PREREG.md Section 2 the study does not pass as a whole; the verdicts above stand as measured." if failed else
              "Every hypothesis has a verdict and all are Supported.", ""]
    s += ["No second reviewer has signed REVIEW.md yet, so review status is UNVERIFIED. What was checked is listed in AUDIT.md."]
    (RESULTS / "verdicts.json").write_text(json.dumps(summary, indent=2) + "\n")
    (ROOT / "RESULTS.md").write_text("\n".join(s) + "\n")

    print(json.dumps({h: verdicts[h][0] for h in verdicts}, indent=2))
    return verdicts


if __name__ == "__main__":
    main()
