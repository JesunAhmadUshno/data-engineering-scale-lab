// Every computation the dashboard runs in the browser. The decision rules and
// statistics are a port of src/make_results.py (rules fixed in METHODS.md);
// src/results.check.mjs asserts this file reproduces results/verdicts.json.

export const TKEYS = ['t1', 't2', 't3', 't4', 't5', 't6'];
export const SCALES = [0.1, 1, 10];
// Decision-rule thresholds, as written in METHODS.md "Hypothesis decision rules".
export const RULES = { h1MaxRatio: 0.5, h2MinRatio: 1.5, h5MinCatch: 0.5, h6Saving: 50, cvLine: 30 };
export const FAULTS = ['F01', 'F02', 'F03', 'F04', 'F05', 'F06', 'F07', 'F08', 'F09', 'F10'];

export const parseJsonl = (text) => text.split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l));
export const sfLabel = (sf) => String(+sf); // Python "%g": 0.1 -> "0.1", 1.0 -> "1"
const fmt = (x, d = 2) => (x == null ? 'n/a' : x.toFixed(d));

const mean = (v) => v.reduce((a, b) => a + b, 0) / v.length;
function stdev(v) {
  if (v.length < 2) return 0;
  const m = mean(v);
  return Math.sqrt(v.reduce((a, x) => a + (x - m) ** 2, 0) / (v.length - 1));
}

const key = (arm, sf, t) => `${arm}|${+sf}|${t}`;

/** (arm, sf, t) -> { mean, sd, cv, n, values }, as cell_stats() in make_results.py. */
export function cellStats(runLog) {
  const agg = new Map();
  for (const r of runLog) {
    if (!TKEYS.includes(r.transformation) || r.seconds == null) continue;
    const k = key(r.arm, r.sf, r.transformation);
    if (!agg.has(k)) agg.set(k, []);
    agg.get(k).push(r.seconds);
  }
  const out = new Map();
  for (const [k, v] of agg) {
    const m = mean(v), sd = stdev(v);
    out.set(k, { mean: m, sd, cv: m ? (100 * sd) / m : 0, n: v.length, values: v });
  }
  return out;
}
export const cell = (stats, arm, sf, t) => stats.get(key(arm, sf, t));

export function setupSeconds(runLog) {
  const out = {};
  for (const r of runLog) if (r.transformation === 'setup') out[`${r.arm}|${+r.sf}`] = r.seconds;
  return out;
}

export function totalRatio(stats, sf) {
  let d = 0, s = 0;
  for (const t of TKEYS) {
    const cd = cell(stats, 'duckdb', sf, t), cs = cell(stats, 'spark', sf, t);
    if (cd) d += cd.mean;
    if (cs) s += cs.mean;
  }
  return { ratio: s ? d / s : null, duckdb: d, spark: s };
}

/** Same stream as mulberry32() in src/make_results.py. */
export function mulberry32(seed) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Percentile 95% bootstrap intervals for each D/S ratio and the total, as bootstrap_ratios(). */
export function bootstrapRatios(stats, sf, B = 2000, seed = 20261106) {
  const rand = mulberry32(seed);
  const perT = Object.fromEntries(TKEYS.map((t) => [t, []]));
  const totals = [];
  const resampleMean = (v) => { let s = 0; for (let i = 0; i < v.length; i++) s += v[Math.floor(rand() * v.length)]; return s / v.length; };
  for (let b = 0; b < B; b++) {
    let sd = 0, ss = 0;
    for (const t of TKEYS) {
      const d = resampleMean(cell(stats, 'duckdb', sf, t).values);
      const s = resampleMean(cell(stats, 'spark', sf, t).values);
      perT[t].push(d / s); sd += d; ss += s;
    }
    totals.push(sd / ss);
  }
  const ci = (xs) => { const s = [...xs].sort((a, b) => a - b); return [s[Math.round(0.025 * (s.length - 1))], s[Math.round(0.975 * (s.length - 1))]]; };
  return { total: ci(totals), ...Object.fromEntries(TKEYS.map((t) => [t, ci(perT[t])])) };
}

/** Incremental saving per scale: T3+T4 model time, full refresh vs the S3 incremental run. */
export function incrementalSavings(incr) {
  const bySf = groupIncr(incr), out = {};
  for (const [sf, scen] of Object.entries(bySf)) {
    const f = scen.full_refresh?.model_seconds, i = scen.S3?.model_seconds;
    if (!f || !i) continue;
    const full = f.daily_sales + f.ranked_sales, inc = i.daily_sales + i.ranked_sales;
    if (full) out[sf] = { full, incremental: inc, saving_pct: (100 * (full - inc)) / full };
  }
  return out;
}
export function groupIncr(incr) {
  const out = {};
  for (const r of incr) (out[sfLabel(r.sf)] ??= {})[r.scenario] = r;
  return out;
}

/** The METHODS.md decision rules, line for line with evaluate() in make_results.py. */
export function evaluate({ runLog, checks, gates, incr }) {
  const stats = cellStats(runLog);
  const sparkScales = new Set([...stats.keys()].filter((k) => k.startsWith('spark|')).map((k) => +k.split('|')[1]));
  const duckScales = new Set([...stats.keys()].filter((k) => k.startsWith('duckdb|')).map((k) => +k.split('|')[1]));
  const v = {};

  if (sparkScales.has(0.1) && sparkScales.has(1)) {
    const r01 = totalRatio(stats, 0.1).ratio, r1 = totalRatio(stats, 1).ratio, m = RULES.h1MaxRatio;
    if (r01 <= m && r1 <= m) v.H1 = ['Supported', `total workload ratio ${fmt(r01, 3)} at SF0.1 and ${fmt(r1, 3)} at SF1, both at most 0.5`];
    else if (r01 <= m || r1 <= m) v.H1 = ['Partially supported', `total workload ratio ${fmt(r01, 3)} at SF0.1 and ${fmt(r1, 3)} at SF1; the 0.5 line is met at one scale only`];
    else v.H1 = ['Refuted', `total workload ratio ${fmt(r01, 3)} at SF0.1 and ${fmt(r1, 3)} at SF1; neither meets 0.5`];
  } else v.H1 = ['Not yet measured', 'Spark runs are missing at SF0.1 or SF1'];

  if (sparkScales.has(10) && duckScales.has(10)) {
    let best = null, bt = null;
    for (const t of TKEYS) {
      const d = cell(stats, 'duckdb', 10, t), s = cell(stats, 'spark', 10, t);
      if (d && s && (best === null || d.mean / s.mean > best)) { best = d.mean / s.mean; bt = t; }
    }
    v.H2 = best !== null && best >= RULES.h2MinRatio
      ? ['Supported', `at SF10, ${bt} ratio ${fmt(best, 3)} reaches the 1.5 line`]
      : ['Refuted', `at SF10 no transformation reaches a 1.5 ratio (best ${fmt(best, 3)}); no crossover observed inside the ladder tested`];
  } else v.H2 = ['Not yet measured', 'SF10 was not completed on this machine; that is not H2 being false'];

  const cv = Object.values(checks.verdicts || {});
  if (cv.length) {
    const agree = cv.every((c) => c.arms_agree_run1);
    const det = cv.every((c) => c.deterministic_run5 === true || c.deterministic_run5 == null);
    v.H3 = [agree ? 'Supported' : 'Refuted', `${cv.filter((c) => c.arms_agree_run1).length} of ${cv.length} (scale, transformation) cells agree across all three arms on run 1; run 5 determinism ${det ? 'holds everywhere' : 'has exceptions named in results/results.md'}`];
  } else v.H3 = ['Not yet measured', 'no checksum records'];

  const bySf = groupIncr(incr);
  let h4ok = true; const h4detail = [];
  for (const sf of Object.keys(bySf).sort((a, b) => a - b)) {
    const scen = bySf[sf], full = scen.full_refresh;
    if (!full) continue;
    for (const name of ['S1', 'S2', 'S3', 'S3b']) {
      const row = scen[name];
      if (!row) { h4ok = false; h4detail.push(`SF${sf} ${name} missing`); continue; }
      for (const t of ['t3', 't4']) if (row.checksums[t].sha256 !== full.checksums[t].sha256) { h4ok = false; h4detail.push(`SF${sf} ${name} ${t} differs from full refresh`); }
    }
  }
  const hasIncr = Object.keys(bySf).length > 0;
  v.H4 = [h4ok && hasIncr ? 'Supported' : hasIncr ? 'Refuted' : 'Not yet measured',
    h4ok && hasIncr ? 'every scenario checksum equals the full-refresh comparator at every tested scale' : h4detail.join('; ') || 'no incremental runs recorded'];

  const f = faultMatrix(gates, v.H4[0] === 'Supported');
  if (gates.length) {
    v.H5 = f.caught / 10 >= RULES.h5MinCatch && !f.criticalMissed.length
      ? ['Supported', `${f.caught} of 10 faults caught; zero missed critical faults`]
      : ['Refuted', `${f.caught} of 10 faults caught; missed critical faults: ${f.criticalMissed.length ? `[${f.criticalMissed.map((x) => `'${x}'`).join(', ')}]` : 'none'} (the hypothesis needs at least 50 percent caught and zero critical misses)`];
  } else v.H5 = ['Not yet measured', 'no gate runs recorded'];

  const sav = incrementalSavings(incr), S = (sf) => sav[sf]?.saving_pct, L = RULES.h6Saving;
  if (['0.1', '1', '10'].every((sf) => sf in sav)) {
    const s10 = S('10'), small = [S('0.1'), S('1')];
    if (s10 > L && small.every((x) => x <= L)) v.H6 = ['Supported', `incremental saving ${fmt(s10, 1)}% at SF10, ${fmt(small[0], 1)}% at SF0.1 and ${fmt(small[1], 1)}% at SF1`];
    else if (s10 > L) v.H6 = ['Partially supported', `incremental saving ${fmt(s10, 1)}% at SF10, but a small scale also exceeds 50% (SF0.1 ${fmt(small[0], 1)}%, SF1 ${fmt(small[1], 1)}%)`];
    else v.H6 = ['Refuted', `incremental saving at SF10 is ${fmt(s10, 1)}%, not above 50%`];
  } else if ('10' in sav) v.H6 = ['Inconclusive', 'SF10 saving is recorded but a small-scale saving is missing'];
  else {
    const over = ['0.1', '1'].filter((sf) => sf in sav && S(sf) > L).map((sf) => `SF${sf} ${fmt(S(sf), 1)}%`);
    let why = 'no SF10 incremental timing recorded';
    if (over.length) why += `; the small-scale clause (saving at most 50% at SF0.1 and SF1) already fails (${over.join(', ')}), so once SF10 is run the best possible verdict is Partially supported, never Supported`;
    v.H6 = ['Not yet measured', why];
  }
  return { verdicts: v, stats, savings: sav, faults: f };
}

/** Fault matrix rows F01-F10. F08 is scored by the incremental checksum gate (H4). */
export function faultMatrix(gates, f08Caught) {
  const by = Object.fromEntries(gates.map((r) => [r.scenario, r]));
  const rows = FAULTS.map((id) => {
    if (id === 'F08') return { id, critical: true, caught: f08Caught, fired: ['incremental checksum equality (PREREG Section 8)'], blocked: null, flagged: false, fromIncremental: true };
    const r = by[id];
    if (!r) return { id, missing: true };
    return { id, critical: r.critical, caught: !!r.caught, fired: [...Object.keys(r.gate_failures || {}), ...Object.keys(r.gate_warnings || {})],
      failures: r.gate_failures || {}, warnings: r.gate_warnings || {}, blocked: !r.promoted, flagged: !!r.flagged_stale, tests: r.tests };
  });
  const caught = rows.filter((r) => r.caught).length;
  const criticalMissed = rows.filter((r) => r.critical && !r.caught && !r.missing && r.id !== 'F08').map((r) => r.id);
  if (!f08Caught && gates.length) criticalMissed.push('F08');
  return { rows, caught, criticalMissed, clean: by.clean };
}

/** Session amortisation: setup paid once, then `jobs` passes over the chosen transformations. */
export function sessionCost({ stats, setups, sf, chosen, jobs }) {
  const per = (arm) => chosen.reduce((a, t) => a + cell(stats, arm, sf, t).mean, 0);
  const d = { setup: setups[`duckdb|${sf}`], perJob: per('duckdb') }, s = { setup: setups[`spark|${sf}`], perJob: per('spark') };
  d.total = d.setup + jobs * d.perJob; s.total = s.setup + jobs * s.perJob;
  // Spark would break even only if its per-job time were lower than DuckDB's.
  const breakEven = s.perJob < d.perJob ? (s.setup - d.setup) / (d.perJob - s.perJob) : null;
  return { duckdb: d, spark: s, ratio: d.total / s.total, steadyRatio: d.perJob / s.perJob, sparkSetupShare: s.setup / s.total, breakEven };
}

/** Two-point log-log what-if: an extrapolation from SF0.1 and SF1 only, never a result. */
export function twoPointWhatIf(stats, t, target = RULES.h2MinRatio) {
  const slope = (arm) => Math.log10(cell(stats, arm, 1, t).mean / cell(stats, arm, 0.1, t).mean);
  const bD = slope('duckdb'), bS = slope('spark');
  const r1 = cell(stats, 'duckdb', 1, t).mean / cell(stats, 'spark', 1, t).mean;
  const gap = bD - bS;
  return { bD, bS, r1, impliedSf: gap > 0 ? (target / r1) ** (1 / gap) : null, ratioAt: (sf) => r1 * sf ** gap };
}

/** Canonical CSV like src/checksum.py: optional ORDER BY all columns, '|' delimiter, no header. */
export function canonicalCsv(rows, { sort = true } = {}) {
  const r = rows.map((x) => [...x]);
  if (sort) r.sort((a, b) => { for (let i = 0; i < a.length; i++) { const c = cmp(a[i], b[i]); if (c) return c; } return 0; });
  return r.map((x) => x.join('|')).join('\n') + '\n';
}
const cmp = (a, b) => { const na = +a, nb = +b; if (a !== '' && b !== '' && !isNaN(na) && !isNaN(nb)) return na - nb; return a < b ? -1 : a > b ? 1 : 0; };

export async function sha256Hex(text) {
  const buf = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/** Pull a markdown section's list items (bullets or numbered) as plain paragraphs. */
export function mdList(md, heading) {
  const start = md.indexOf(heading);
  if (start < 0) return [];
  const body = md.slice(start + heading.length).split(/\n## /)[0];
  const items = [];
  for (const line of body.split('\n')) {
    if (/^(- |\d+\. )/.test(line)) items.push(line.replace(/^(- |\d+\. )/, ''));
    else if (/^\s+\S/.test(line) && items.length) items[items.length - 1] += ' ' + line.trim();
  }
  return items;
}
