// Known-answer check, run by "npm run build" before vite: every computation the
// page does in the browser (src/lab.js) must reproduce the repo's own outputs.
// Reference: results/verdicts.json, written by src/make_results.py from the same logs.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import {
  parseJsonl, evaluate, totalRatio, bootstrapRatios, sessionCost, setupSeconds, twoPointWhatIf,
  canonicalCsv, sha256Hex, mulberry32, cell, mdList, TKEYS,
} from './lab.js';

const R = (p) => readFileSync(new URL(`../../${p}`, import.meta.url), 'utf8');
const runLog = parseJsonl(R('results/run_log.jsonl'));
const checks = JSON.parse(R('results/checksums.json'));
const gates = parseJsonl(R('results/gate_log.jsonl'));
const incr = parseJsonl(R('results/incremental_log.jsonl'));
const ref = JSON.parse(R('results/verdicts.json'));
const close = (a, b, tol, what) => assert.ok(Math.abs(a - b) <= tol, `${what}: ${a} vs ${b}`);

// 1. Hypothesis verdicts and their reasons, word for word with make_results.py.
const ev = evaluate({ runLog, checks, gates, incr });
for (const [h, { verdict, why }] of Object.entries(ref.verdicts)) {
  assert.equal(ev.verdicts[h][0], verdict, `${h} verdict`);
  assert.equal(ev.verdicts[h][1], why, `${h} reason`);
}
assert.deepEqual(Object.fromEntries(Object.entries(ev.verdicts).map(([h, [v]]) => [h, v])),
  { H1: 'Supported', H2: 'Refuted', H3: 'Supported', H4: 'Supported', H5: 'Supported', H6: 'Partially supported' });
// SF10 is in the logs: the page's SF10 figures (H2's best ratio, the SF10 total, the H6 saving) are pinned too.
const best10 = TKEYS.map((t) => cell(ev.stats, 'duckdb', 10, t).mean / cell(ev.stats, 'spark', 10, t).mean).sort((x, y) => y - x)[0];
assert.ok(ref.verdicts.H2.why.includes(`best ${best10.toFixed(3)}`), 'H2 best SF10 ratio');
assert.equal(best10.toFixed(3), '0.467');
assert.equal(totalRatio(ev.stats, 10).ratio.toFixed(3), '0.248');
assert.equal(ev.savings['10'].saving_pct.toFixed(1), '87.1');
// Without the SF10 rows, the rules fall back to Not yet measured, as make_results.py does.
const small = evaluate({ runLog: runLog.filter((r) => r.sf !== 10), checks, gates, incr: incr.filter((r) => r.sf !== 10) });
assert.equal(small.verdicts.H2[0], 'Not yet measured'); assert.equal(small.verdicts.H6[0], 'Not yet measured');

// 2. Totals, ratios and bootstrap intervals (same PRNG stream as Python).
for (const [sf, t] of Object.entries(ref.totals)) {
  const got = totalRatio(ev.stats, +sf);
  close(got.duckdb, t.duckdb, 1e-6, `SF${sf} DuckDB total`);
  close(got.spark, t.spark, 1e-6, `SF${sf} Spark total`);
  close(got.ratio, t.ratio, 1e-6, `SF${sf} ratio`);
  const b = bootstrapRatios(ev.stats, +sf, ref.bootstrap.resamples, ref.bootstrap.seed);
  close(b.total[0], t.ratio_ci95[0], 1e-6, `SF${sf} CI lo`); close(b.total[1], t.ratio_ci95[1], 1e-6, `SF${sf} CI hi`);
  for (const k of TKEYS) for (const i of [0, 1]) close(b[k][i], t.per_transformation_ci95[k][i], 1e-6, `SF${sf} ${k} CI`);
}
const rand = mulberry32(20261106);
assert.deepEqual([rand(), rand(), rand()], [0.01353957294486463, 0.8884504192974418, 0.7106646823231131]);

// 3. Incremental savings, fault matrix.
for (const [sf, pct] of Object.entries(ref.incremental_saving_pct)) close(ev.savings[sf].saving_pct, pct, 1e-4, `SF${sf} saving`);
assert.equal(ev.faults.caught, ref.faults_caught);
assert.deepEqual(ev.faults.criticalMissed, ref.critical_missed);

// 4. Session calculator: with one job it is setup plus the six means, by hand from the log.
const setups = setupSeconds(runLog);
const sc = sessionCost({ stats: ev.stats, setups, sf: 1, chosen: TKEYS, jobs: 1 });
close(sc.duckdb.total, setups['duckdb|1'] + ref.totals['1'].duckdb, 1e-9, 'session DuckDB');
close(sc.spark.total, setups['spark|1'] + ref.totals['1'].spark, 1e-9, 'session Spark');
close(sc.steadyRatio, ref.totals['1'].ratio, 1e-6, 'steady-state ratio equals the H1 total ratio');
assert.equal(sc.breakEven, null, 'Spark is slower per job at SF1, so there is no break-even');

// 5. Two-point what-if: the extrapolated ratio at SF1 is the measured SF1 ratio.
for (const t of TKEYS) {
  const w = twoPointWhatIf(ev.stats, t);
  close(w.ratioAt(1), cell(ev.stats, 'duckdb', 1, t).mean / cell(ev.stats, 'spark', 1, t).mean, 1e-12, `${t} what-if anchor`);
  close(w.ratioAt(0.1), cell(ev.stats, 'duckdb', 0.1, t).mean / cell(ev.stats, 'spark', 0.1, t).mean, 1e-9, `${t} what-if SF0.1`);
}

// 5b. The SF10 session calculator uses the completed session's setup (the last setup row, as make_results.py).
assert.equal(setups['spark|10'], runLog.filter((r) => r.arm === 'spark' && r.sf === 10 && r.transformation === 'setup').at(-1).seconds);

// 6. Checksum playground: crypto.subtle equals node's SHA-256, and the canonical sort makes order irrelevant.
const rows = [['1995-03-01', '12', '1034.50'], ['1994-07-19', '9', '880.10'], ['1995-03-01', '3', '75.00']];
const a = canonicalCsv(rows), b = canonicalCsv([...rows].reverse());
assert.equal(a, b);
assert.equal(await sha256Hex(a), createHash('sha256').update(a).digest('hex'));
assert.notEqual(await sha256Hex(canonicalCsv(rows, { sort: false })), await sha256Hex(canonicalCsv([...rows].reverse(), { sort: false })));
assert.notEqual(await sha256Hex(a), await sha256Hex(canonicalCsv(rows.map((r) => [r[0], r[1], String(+r[2])]))));

// 7. Threats and roadmap are read from the study's own markdown.
assert.ok(mdList(R('METHODS.md'), '## Threats to validity').length >= 4);
assert.ok(mdList(R('REPORT.md'), 'in evidence order.').length >= 5);

console.log('results ok', { H: Object.values(ev.verdicts).map((v) => v[0]).join(' / '), sf01: ref.totals['0.1'].ratio, sf1: ref.totals['1'].ratio, sf10: ref.totals['10'].ratio });
