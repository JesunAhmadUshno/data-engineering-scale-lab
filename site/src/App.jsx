import { useMemo, useState, useEffect, useId } from 'react';
import runLogRaw from '../../results/run_log.jsonl?raw';
import preWarmRaw from '../../results/run_log_pre_warmup.jsonl?raw';
import gatesRaw from '../../results/gate_log.jsonl?raw';
import incrRaw from '../../results/incremental_log.jsonl?raw';
import checks from '../../results/checksums.json';
import expected from '../../results/expected_checksums.json';
import versions from '../../results/versions.json';
import preregMd from '../../PREREG.md?raw';
import methodsMd from '../../METHODS.md?raw';
import roadmapMd from '../../REPORT.md?raw';
import reviewMd from '../../REVIEW.md?raw';
import {
  parseJsonl, evaluate, totalRatio, bootstrapRatios, setupSeconds, sessionCost, twoPointWhatIf, cell,
  groupIncr, canonicalCsv, sha256Hex, mdList, TKEYS, RULES,
} from './lab.js';

const REPO = 'https://github.com/JesunAhmadUshno/data-engineering-scale-lab';
const blob = (p) => `${REPO}/blob/main/${p}`;

const runLog = parseJsonl(runLogRaw);
const preWarm = parseJsonl(preWarmRaw);
const gates = parseJsonl(gatesRaw);
const incr = parseJsonl(incrRaw);
const EV = evaluate({ runLog, checks, gates, incr });
const STATS = EV.stats;
const SETUPS = setupSeconds(runLog);
const MACHINE = runLog.find((r) => r.machine)?.machine ?? {};
const T01 = totalRatio(STATS, 0.1), T1 = totalRatio(STATS, 1), T10 = totalRatio(STATS, 10);
const N_RUNS = cell(STATS, 'duckdb', 1, 't1').n;
const BENCH_SCALES = [0.1, 1, 10];
const ALL_FASTER = BENCH_SCALES.every((sf) => TKEYS.every((t) => cell(STATS, 'duckdb', sf, t).mean < cell(STATS, 'spark', sf, t).mean));
// Highest D/S at SF10: the H2 crossover rule asks whether any transformation reaches 1.5.
const BEST10 = TKEYS.map((t) => [t, cell(STATS, 'duckdb', 10, t).mean / cell(STATS, 'spark', 10, t).mean]).sort((a, b) => b[1] - a[1])[0];
const BOOT_B = 2000; // resamples, as BOOT_B in src/make_results.py
const highCv = (sfs) => sfs.flatMap((sf) => TKEYS.filter((t) => cell(STATS, 'duckdb', sf, t).cv > RULES.cvLine).map((t) => `SF${sf} ${t.toUpperCase()}`));
const HIGH_CV = highCv([0.1, 1]), HIGH_CV10 = highCv([10]);
// Hypothesis and transformation names are read from PREREG.md, not retyped.
const H_NAMES = Object.fromEntries([...preregMd.matchAll(/^- (H\d), ([^:]+):/gm)].map((m) => [m[1], m[2]]));
const T_NAMES = Object.fromEntries([...preregMd.matchAll(/^- (T\d) ([^:]+):/gm)].map((m) => [m[1].toLowerCase(), m[2]]));
const ARMS = [['duckdb', 'DuckDB', 'var(--duck)'], ['spark', 'Spark local', 'var(--spark)'], ['dbt', 'dbt model time', 'var(--dbt)']];
const VPILL = { Supported: 'good', 'Partially supported': 'warn', Refuted: 'bad', 'Not yet measured': 'info', Inconclusive: 'warn' };
const bySfSorted = (o) => Object.entries(o).sort(([a], [b]) => a - b);
const f2 = (x) => x.toFixed(2), f3 = (x) => x.toFixed(3), pct1 = (x) => `${x.toFixed(1)}%`;
const sec = (x) => (x < 1 ? `${(x * 1000).toFixed(0)} ms` : `${x.toFixed(2)} s`);

const SECTIONS = [['top', 'Overview', '◎'], ['prereg', 'Hypotheses', 'H'], ['bench', 'Scale bench', '▥'], ['cost', 'Session cost', '∑'], ['ledger', 'Checksums', '#'], ['faults', 'Gates', '✓'], ['late', 'Late data', '↻'], ['protocol', 'Protocol', '⇄'], ['threats', 'Threats', '!']];

function useReveal() {
  useEffect(() => {
    const els = document.querySelectorAll('.reveal');
    if (!('IntersectionObserver' in window)) { els.forEach((e) => e.classList.add('in')); return; }
    const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { threshold: 0.08 });
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, []);
}

function MenuBar() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 30000); return () => clearInterval(t); }, []);
  return (
    <div className="menubar" role="banner">
      <span className="apple" aria-hidden="true">◆</span>
      <a className="app" href="#top">Data Engineering Scale Lab</a>
      <a className="m" href={blob('PREREG.md')}>Pre-registration</a>
      <a className="m" href={blob('METHODS.md')}>Methods</a>
      <a className="m" href={blob('RESULTS.md')}>Results</a>
      <span className="spacer" />
      <span className="status"><i /> SF0.1 checksum gate in CI</span>
      <a href={REPO}>GitHub ↗</a>
      <span className="clock">{now.toLocaleString('en-US', { weekday: 'short', hour: 'numeric', minute: '2-digit' })}</span>
    </div>
  );
}

function Dock() {
  const [active, setActive] = useState('top');
  useEffect(() => {
    const io = new IntersectionObserver((es) => es.forEach((e) => e.isIntersecting && setActive(e.target.id)), { rootMargin: '-45% 0px -50% 0px' });
    SECTIONS.forEach(([id]) => { const el = document.getElementById(id); if (el) io.observe(el); });
    return () => io.disconnect();
  }, []);
  return (
    <nav className="dock" aria-label="Sections">
      {SECTIONS.map(([id, label, icon]) => (
        <a key={id} href={`#${id}`} className={active === id ? 'on' : ''} aria-current={active === id ? 'true' : undefined}>
          <span className="ico" aria-hidden="true">{icon}</span><span className="lbl">{label}</span>
        </a>
      ))}
    </nav>
  );
}

function Range({ label, value, min, max, step, onChange, show }) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label} <span>{show}</span></label>
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(+e.target.value)} />
    </div>
  );
}

function Seg({ label, options, value, onChange }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map(([k, l]) => <button key={String(k)} aria-pressed={value === k} onClick={() => onChange(k)}>{l}</button>)}
    </div>
  );
}

export default function App() {
  useReveal();
  return (
    <div className="wrap">
      <MenuBar />
      <div className="glow" aria-hidden="true" />
      <Hero />
      <Hypotheses />
      <ScaleBench />
      <SessionCost />
      <Ledger />
      <Faults />
      <LateData />
      <Protocol />
      <Threats />
      <Dock />
      <footer>
        <p>Data derived from TPC-H with DuckDB's tpch extension; not comparable to official TPC results. The late delta is synthetic. Code: Apache-2.0.</p>
        <p>Recorded with DuckDB {versions.duckdb}, Spark {versions.spark}, dbt Core {versions.dbt_core} with dbt-duckdb {versions.dbt_duckdb}, Python {versions.python}, {versions.java.split(' ').slice(0, 3).join(' ').replace(/"/g, '')}.</p>
        <p>Every number on this page is read from <code>results/</code> at build time or computed in your browser from those files; nothing here is a new measurement.</p>
      </footer>
    </div>
  );
}

function Hero() {
  const b01 = bootstrapRatios(STATS, 0.1).total, b1 = bootstrapRatios(STATS, 1).total, b10 = bootstrapRatios(STATS, 10).total;
  const cv = Object.values(checks.verdicts);
  return (
    <header className="card hero window" id="top" data-title="data-engineering-scale-lab — README.md">
      <div className="head">
        <p className="eyebrow">Pre-registered study · 3 arms · recorded runs</p>
        <span className="pill warn">Derived from TPC-H, not comparable to official TPC results</span>
      </div>
      <h1>At SF0.1 on one {MACHINE.cores}-core machine, DuckDB ran six transformations in <em>{f3(T01.ratio)}×</em> of Spark’s time.</h1>
      <p className="sub">
        Same Parquet files, same SQL, {MACHINE.cores} cores and {MACHINE.ram_gib} GiB of RAM. Summed over the six frozen transformations (mean of {N_RUNS} runs each),
        DuckDB took {f2(T01.duckdb)} s against Spark local mode’s {f2(T01.spark)} s at SF0.1, and {f2(T1.duckdb)} s against {f2(T1.spark)} s at SF1 ({f3(T1.ratio)}×).
        At SF10 it was {f2(T10.duckdb)} s against {f2(T10.spark)} s ({f3(T10.ratio)}×). All three arms wrote byte-identical outputs.
        The question the study was built for, whether Spark overtakes DuckDB at a larger scale, got a <b>no inside the ladder tested</b>: at SF10 the closest transformation, {BEST10[0].toUpperCase()}, reached a D/S of {f3(BEST10[1])}, far from the {RULES.h2MinRatio} crossover line. The ladder stops at SF10, and so does that claim.
      </p>
      <div className="actions">
        <a className="btn primary" href="#bench">Explore the recorded timings</a>
        <a className="btn ghost" href={blob('PREREG.md')}>Read the pre-registration</a>
        <span className="hint">Cheap checks: <code>make check</code></span>
      </div>
      <div className="tiles five">
        <div className="tile"><div className="num">{f3(T01.ratio)}×</div><div className="cap">SF0.1: {f2(T01.duckdb)} s DuckDB vs {f2(T01.spark)} s Spark, six means, n={N_RUNS} (95% CI {f3(b01[0])} to {f3(b01[1])})</div></div>
        <div className="tile"><div className="num">{f3(T1.ratio)}×</div><div className="cap">SF1: {f2(T1.duckdb)} s DuckDB vs {f2(T1.spark)} s Spark, six means, n={N_RUNS} (95% CI {f3(b1[0])} to {f3(b1[1])})</div></div>
        <div className="tile"><div className="num">{f3(T10.ratio)}×</div><div className="cap">SF10: {f2(T10.duckdb)} s DuckDB vs {f2(T10.spark)} s Spark, six means, n={N_RUNS} (95% CI {f3(b10[0])} to {f3(b10[1])})</div></div>
        <div className="tile"><div className="num">{cv.filter((c) => c.arms_agree_run1).length}/{cv.length}</div><div className="cap">(scale, transformation) cells where all three arms give the same SHA-256</div></div>
        <div className="tile"><div className="num">{EV.faults.caught}/10</div><div className="cap">injected faults caught, {EV.faults.criticalMissed.length} critical missed</div></div>
      </div>
    </header>
  );
}

function Hypotheses() {
  const v = EV.verdicts, sav = EV.savings;
  const b = { '0.1': bootstrapRatios(STATS, 0.1).total, 1: bootstrapRatios(STATS, 1).total };
  const bBest = bootstrapRatios(STATS, 10)[BEST10[0]];
  const bySf = groupIncr(incr);
  let eq = 0, tot = 0;
  for (const scen of Object.values(bySf)) for (const s of ['S1', 'S2', 'S3', 'S3b']) for (const t of ['t3', 't4']) { tot++; if (scen[s]?.checksums[t].sha256 === scen.full_refresh.checksums[t].sha256) eq++; }
  const cv = Object.values(checks.verdicts);
  const cards = [
    ['H1', `Total D/S ratio at most ${RULES.h1MaxRatio} at SF0.1 and SF1`, `${f3(T01.ratio)} (CI ${f3(b['0.1'][0])} to ${f3(b['0.1'][1])}) and ${f3(T1.ratio)} (CI ${f3(b[1][0])} to ${f3(b[1][1])})`],
    ['H2', `Some transformation at D/S ≥ ${RULES.h2MinRatio} at SF10`, `Highest at SF10: ${BEST10[0].toUpperCase()} ${f3(BEST10[1])} (CI ${f3(bBest[0])} to ${f3(bBest[1])})`],
    ['H3', 'Identical checksum across all arms, every cell', `${cv.filter((c) => c.arms_agree_run1).length} of ${cv.length} cells agree on run 1`],
    ['H4', 'Every late-data scenario equals the full refresh (T3, T4)', `${eq} of ${tot} scenario checksums equal`],
    ['H5', `At least ${RULES.h5MinCatch * 100}% of F01–F10 caught, zero critical missed`, `${EV.faults.caught} of 10 caught, ${EV.faults.criticalMissed.length} critical missed`],
    ['H6', `Incremental saving > ${RULES.h6Saving}% at SF10, ≤ ${RULES.h6Saving}% at SF0.1 and SF1`, `SF0.1 ${pct1(sav['0.1'].saving_pct)}, SF1 ${pct1(sav['1'].saving_pct)}, SF10 ${pct1(sav['10'].saving_pct)}`],
  ];
  return (
    <section id="prereg" className="card window reveal" data-title="prereg.md — RQ1 and H1–H6">
      <p className="eyebrow">Hypothesis board · verdicts computed in your browser</p>
      <h2>Four hypotheses hold. H2 is refuted at <em>SF10</em>, and H6 is refuted under the locked rule.</h2>
      <p className="sub">
        RQ1 asks at what data scale, if any, local Spark beats DuckDB on identical transformations, and what incremental dbt models with quality gates cost and catch.
        Each card applies the decision rule from <a href={blob('METHODS.md')}>METHODS.md</a> to the recorded logs, using a JavaScript port of <a href={blob('src/make_results.py')}>make_results.py</a>.
        The build fails if any verdict or reason differs from the Python output. PREREG Section 2 says the study passes only when every hypothesis holds; with H2 and H6 refuted, it does not pass as a whole, and the verdicts stand as measured.
      </p>
      <div className="hgrid">
        {cards.map(([h, rule, measured]) => (
          <div className="tile hcard" key={h}>
            <div className="head" style={{ marginBottom: 6 }}>
              <h3>{h} · {H_NAMES[h]}</h3>
              <span className={`pill ${VPILL[v[h][0]]}`}>{v[h][0]}</span>
            </div>
            <dl>
              <dt>Rule</dt><dd>{rule}</dd>
              <dt>Measured</dt><dd>{measured}</dd>
            </dl>
            <p className="hint" style={{ margin: '8px 0 0' }}>{v[h][1].charAt(0).toUpperCase() + v[h][1].slice(1)}.</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function ScaleBench() {
  const [sf, setSf] = useState(1);
  const [pre, setPre] = useState(false);
  const [hover, setHover] = useState(null);
  const boot = useMemo(() => bootstrapRatios(STATS, sf), [sf]);
  const W = 960, H = 320, pad = { l: 56, r: 12, t: 14, b: 34 };
  const lo = -2.2, hi = 3;
  const y = (s) => pad.t + (1 - (Math.log10(Math.max(10 ** lo, s)) - lo) / (hi - lo)) * (H - pad.t - pad.b);
  const gw = (W - pad.l - pad.r) / TKEYS.length, bw = gw / 4.6;
  const gx = (i) => pad.l + i * gw + gw * 0.12;
  const preCells = (arm, t) => preWarm.filter((r) => r.arm === arm && r.sf === 0.1 && r.transformation === t).map((r) => r.seconds);
  const flaggedCells = TKEYS.flatMap((t) => ARMS.filter(([a]) => a !== 'dbt' && cell(STATS, a, sf, t).cv > RULES.cvLine).map(([a, n]) => ({ label: `${n} ${t.toUpperCase()} (CV ${cell(STATS, a, sf, t).cv.toFixed(0)}%)`, c: cell(STATS, a, sf, t) })));
  const flagged = flaggedCells.map((f) => f.label);
  const flaggedMax = Math.max(0, ...flaggedCells.flatMap((f) => f.c.values));
  const h = hover;
  return (
    <section id="bench" className="card window reveal" data-title="scale_bench.app — recorded replay">
      <div className="head">
        <div>
          <p className="eyebrow">Recorded timings · not a live run</p>
          <h2>At SF0.1, SF1 and SF10 ({N_RUNS} runs per cell), DuckDB beat Spark local on <em>{ALL_FASTER ? 'every one' : 'most'}</em> of the six transformations.</h2>
          <p className="sub">
            Bars are the mean of {N_RUNS} recorded runs per cell, after one uncounted warm-up pass; dots are the individual runs. Log scale.
            DuckDB and Spark times are execution plus write. dbt bars use dbt’s own per-model execution time, a different timing base, so they are shown for cost context and never ratioed.
          </p>
        </div>
        <Seg label="Scale factor" value={sf} onChange={setSf} options={[[0.1, 'SF0.1'], [1, 'SF1'], [10, 'SF10']]} />
      </div>
      <>
          <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Recorded mean seconds per transformation at SF${sf} for DuckDB, Spark and dbt, log scale`} onMouseLeave={() => setHover(null)}>
            {[0.01, 0.1, 1, 10, 100, 1000].map((t) => <g key={t}><line className="axis" x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} /><text x={pad.l - 8} y={y(t) + 4} textAnchor="end">{t >= 1 ? `${t} s` : `${t * 1000} ms`}</text></g>)}
            {TKEYS.map((t, i) => (
              <g key={t} onMouseEnter={() => setHover(t)} style={{ cursor: 'default' }}>
                <rect x={pad.l + i * gw} y={pad.t} width={gw} height={H - pad.t - pad.b} fill={hover === t ? 'var(--primary-pale)' : 'transparent'} />
                {ARMS.map(([arm, , color], j) => {
                  const c = cell(STATS, arm, sf, t), x0 = gx(i) + j * (bw + 6);
                  return (
                    <g key={arm}>
                      <rect x={x0} y={y(c.mean)} width={bw} height={H - pad.b - y(c.mean)} rx="4" fill={color} opacity={arm === 'dbt' ? 0.45 : 0.85} />
                      {c.values.map((s, k) => <circle key={k} cx={x0 + bw / 2 + (k - 2) * 3} cy={y(s)} r="2.6" fill="var(--text)" opacity="0.75" />)}
                      {pre && sf === 0.1 && arm !== 'dbt' && preCells(arm, t).map((s, k) => <circle key={`p${k}`} cx={x0 + bw / 2 + (k - 2) * 3} cy={y(s)} r="3.4" fill="none" stroke="var(--bad)" strokeWidth="1.6" />)}
                      {arm !== 'dbt' && c.cv > RULES.cvLine && <text x={x0 + bw / 2} y={y(Math.max(c.mean, ...c.values)) - 10} textAnchor="middle" style={{ fill: 'var(--warn)', fontWeight: 700 }}>CV!</text>}
                    </g>
                  );
                })}
                <text x={pad.l + i * gw + gw / 2} y={H - 12} textAnchor="middle" style={{ fill: 'var(--text)' }}>{t.toUpperCase()} {T_NAMES[t]}</text>
              </g>
            ))}
          </svg>
          <div className="legend">
            {ARMS.map(([a, n, c]) => <span key={a}><i style={{ background: c, opacity: a === 'dbt' ? 0.45 : 0.85 }} />{n}</span>)}
            <span><i style={{ background: 'var(--text)', borderRadius: '50%' }} />one recorded run</span>
            {sf === 0.1 && pre && <span><i style={{ border: '2px solid var(--bad)', borderRadius: '50%' }} />pre-warm-up run (discarded)</span>}
          </div>
          <div className="tip" aria-live="polite">
            {h ? <>{h.toUpperCase()} at SF{sf}: DuckDB {sec(cell(STATS, 'duckdb', sf, h).mean)} ± {sec(cell(STATS, 'duckdb', sf, h).sd)}, Spark {sec(cell(STATS, 'spark', sf, h).mean)} ± {sec(cell(STATS, 'spark', sf, h).sd)}, D/S {f3(cell(STATS, 'duckdb', sf, h).mean / cell(STATS, 'spark', sf, h).mean)} (95% CI {f3(boot[h][0])} to {f3(boot[h][1])}), n={N_RUNS} each.</> : 'Hover a transformation to read its cell.'}
          </div>
          {sf === 0.1 && (
            <label className="check">
              <input type="checkbox" checked={pre} onChange={(e) => setPre(e.target.checked)} />
              Overlay the discarded pre-warm-up runs (<a href={blob('results/run_log_pre_warmup.jsonl')}>run_log_pre_warmup.jsonl</a>): they explain PREREG Deviation 1, where Spark’s first run of every cell carried one-time JVM costs.
            </label>
          )}
          <div style={{ overflowX: 'auto', marginTop: 14 }}>
            <table>
              <thead><tr><th>Cell</th><th>DuckDB mean (SD, CV)</th><th>Spark mean (SD, CV)</th><th>D/S</th><th>D/S 95% bootstrap CI</th><th>dbt model mean</th></tr></thead>
              <tbody>
                {TKEYS.map((t) => {
                  const d = cell(STATS, 'duckdb', sf, t), s = cell(STATS, 'spark', sf, t), m = cell(STATS, 'dbt', sf, t);
                  return (
                    <tr key={t}><td>{t.toUpperCase()} {T_NAMES[t]}</td>
                      <td className={d.cv > RULES.cvLine ? 'no' : ''}>{sec(d.mean)} ({sec(d.sd)}, {d.cv.toFixed(0)}%)</td>
                      <td className={s.cv > RULES.cvLine ? 'no' : ''}>{sec(s.mean)} ({sec(s.sd)}, {s.cv.toFixed(0)}%)</td>
                      <td>{f3(d.mean / s.mean)}</td><td>{f3(boot[t][0])} to {f3(boot[t][1])}</td><td>{sec(m.mean)}</td></tr>
                  );
                })}
                <tr><td><b>Total (six means)</b></td><td><b>{f2(totalRatio(STATS, sf).duckdb)} s</b></td><td><b>{f2(totalRatio(STATS, sf).spark)} s</b></td><td><b>{f3(totalRatio(STATS, sf).ratio)}</b></td><td><b>{f3(boot.total[0])} to {f3(boot.total[1])}</b></td><td /></tr>
              </tbody>
            </table>
          </div>
          <p className="hint">
            {!flagged.length ? `No cell at SF${sf} is over the ${RULES.cvLine}% CV line.`
              : sf === 10 ? `Over the pre-registered ${RULES.cvLine}% CV line: ${flagged.join(', ')}. These are not timer jitter: the cause on record is co-tenant load on the same VM and VM restarts during the SF10 sequence (AUDIT.md, DECISIONS.md D17). The H2 verdict does not turn on them; its margin to ${RULES.h2MinRatio} is wide.`
              : `Over the pre-registered ${RULES.cvLine}% CV line: ${flagged.join(', ')}. The slowest run in these cells took ${sec(flaggedMax)}, where timer jitter is of the same order as the measurement; recorded as PREREG Deviation 2, not re-run.`}
            {' '}Bootstrap intervals resample the {N_RUNS} runs per cell {BOOT_B.toLocaleString('en-US')} times; with n={N_RUNS} they describe run-to-run spread on this machine only.
          </p>
        </>
      <WhatIf />
    </section>
  );
}

function WhatIf() {
  const [t, setT] = useState('t2');
  const w = useMemo(() => twoPointWhatIf(STATS, t), [t]);
  const measured10 = cell(STATS, 'duckdb', 10, t).mean / cell(STATS, 'spark', 10, t).mean;
  const id = useId();
  return (
    <div className="whatif">
      <div className="head" style={{ marginBottom: 8 }}>
        <h3>Two-point what-if: what did SF0.1 and SF1 alone predict for SF10?</h3>
        <span className="pill bad">Extrapolation, not a result</span>
      </div>
      <div className="field" style={{ maxWidth: 320 }}>
        <label htmlFor={id}>Transformation</label>
        <select id={id} value={t} onChange={(e) => setT(e.target.value)}>
          {TKEYS.map((k) => <option key={k} value={k}>{k.toUpperCase()} {T_NAMES[k]}</option>)}
        </select>
      </div>
      <p className="hint" style={{ fontSize: 13 }}>
        From SF0.1 to SF1, {t.toUpperCase()} time grew as scale^{f2(w.bD)} for DuckDB and scale^{f2(w.bS)} for Spark (log-log slope over two points).
        {w.impliedSf ? ` Drawing those two straight lines onward, the D/S ratio would reach ${RULES.h2MinRatio} near SF${w.impliedSf < 1e4 ? w.impliedSf.toFixed(0) : w.impliedSf.toExponential(1)}.` : ' DuckDB’s time grew no faster than Spark’s, so the straight lines never reach the H2 line.'}
        {' '}At SF10 the same lines give a D/S of {f3(w.ratioAt(10))}; the recorded SF10 ratio is {f3(measured10)}.
        Two points fix a line exactly and say nothing about curvature, memory spill or out-of-core behaviour, so this is a check on how far a naive trend can be trusted, not a forecast past the ladder.
      </p>
    </div>
  );
}

function SessionCost() {
  const [sf, setSf] = useState(1);
  const [chosen, setChosen] = useState(TKEYS);
  const [jobs, setJobs] = useState(1);
  const pick = chosen.length ? chosen : ['t1'];
  const r = sessionCost({ stats: STATS, setups: SETUPS, sf, chosen: pick, jobs });
  const W = 460, H = 220, pad = { l: 48, r: 10, t: 10, b: 24 }, maxJ = 50;
  const ymax = SETUPS[`spark|${sf}`] + maxJ * r.spark.perJob;
  const x = (j) => pad.l + ((j - 1) / (maxJ - 1)) * (W - pad.l - pad.r);
  const y = (v) => pad.t + (1 - v / ymax) * (H - pad.t - pad.b);
  const line = (arm) => Array.from({ length: maxJ }, (_, i) => `${x(i + 1)},${y(r[arm].setup + (i + 1) * r[arm].perJob)}`).join(' ');
  const toggle = (t) => setChosen((c) => (c.includes(t) ? c.filter((k) => k !== t) : TKEYS.filter((k) => c.includes(k) || k === t)));
  return (
    <section id="cost" className="card window reveal" data-title="session_cost.calc — arithmetic on recorded means">
      <p className="eyebrow">Calculator · no new measurement</p>
      <h2>Spark’s start-up is not the whole story: at SF{sf} it is also <em>{r.steadyRatio < 1 ? 'slower per job' : 'not faster per job'}</em>.</h2>
      <p className="sub">
        Spark’s JVM, session and first action were timed separately at {f2(SETUPS['spark|0.1'])} s (SF0.1), {f2(SETUPS['spark|1'])} s (SF1) and {f2(SETUPS['spark|10'])} s (SF10); DuckDB’s connect and views at {f2(SETUPS['duckdb|0.1'])} s, {f2(SETUPS['duckdb|1'])} s and {f2(SETUPS['duckdb|10'])} s (one measurement each; at SF10 the completed session’s, DECISIONS.md D17).
        Pick a scale, a set of transformations and how many times a session runs them. Total = setup + jobs × the sum of the recorded means. If Spark were faster per job, a long enough session would pay back its start-up; the calculator shows whether that happens.
      </p>
      <div className="grid2" style={{ marginTop: 16 }}>
        <div>
          <div className="controls" style={{ gridTemplateColumns: '1fr' }}>
            <div className="field"><span className="flabel">Scale factor</span><Seg label="Scale factor for the calculator" value={sf} onChange={setSf} options={[[0.1, 'SF0.1'], [1, 'SF1'], [10, 'SF10']]} /></div>
            <fieldset className="field picks"><legend className="flabel">Transformations in each job</legend>
              {TKEYS.map((t) => <label key={t}><input type="checkbox" checked={chosen.includes(t)} onChange={() => toggle(t)} /> {t.toUpperCase()} {T_NAMES[t]}</label>)}
            </fieldset>
            <Range label="Jobs per session" value={jobs} min={1} max={maxJ} step={1} onChange={setJobs} show={jobs} />
          </div>
        </div>
        <div>
          <div className="tiles" style={{ gridTemplateColumns: '1fr 1fr', marginTop: 0 }}>
            <div className="tile"><div className="num">{f2(r.duckdb.total)} s</div><div className="cap">DuckDB session total</div></div>
            <div className="tile"><div className="num">{f2(r.spark.total)} s</div><div className="cap">Spark session total, {(r.sparkSetupShare * 100).toFixed(0)}% of it start-up</div></div>
            <div className="tile"><div className="num">{f3(r.ratio)}×</div><div className="cap">D/S with start-up included (steady state {f3(r.steadyRatio)}×)</div></div>
            <div className="tile"><div className="num">{r.breakEven == null ? 'never' : Math.ceil(r.breakEven)}</div><div className="cap">{r.breakEven == null ? 'jobs for Spark to break even: its per-job time is higher too' : 'jobs for Spark to break even'}</div></div>
          </div>
          <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Session total seconds against jobs per session, DuckDB and Spark" style={{ marginTop: 12 }}>
            {[0, 0.5, 1].map((f) => <g key={f}><line className="axis" x1={pad.l} x2={W - pad.r} y1={y(f * ymax)} y2={y(f * ymax)} /><text x={pad.l - 6} y={y(f * ymax) + 4} textAnchor="end">{(f * ymax).toFixed(0)} s</text></g>)}
            <polyline fill="none" stroke="var(--spark)" strokeWidth="2.5" points={line('spark')} />
            <polyline fill="none" stroke="var(--duck)" strokeWidth="2.5" points={line('duckdb')} />
            <line x1={x(jobs)} x2={x(jobs)} y1={pad.t} y2={H - pad.b} stroke="var(--muted)" strokeDasharray="4 4" />
            <text x={pad.l} y={H - 4}>1 job</text><text x={W - pad.r} y={H - 4} textAnchor="end">{maxJ} jobs</text>
          </svg>
          <div className="legend"><span><i style={{ background: 'var(--duck)' }} />DuckDB</span><span><i style={{ background: 'var(--spark)' }} />Spark local</span></div>
        </div>
      </div>
    </section>
  );
}

function Ledger() {
  const cells = Object.entries(checks.verdicts);
  const rowsOf = (k) => { const [s, t] = k.split(':'); return checks.records.find((r) => `sf${+r.sf}` === s && r.transformation === t && r.run === 1)?.rows; };
  return (
    <section id="ledger" className="card window reveal" data-title={`checksum_ledger.sha256 — ${cells.length} cells × 3 arms`}>
      <p className="eyebrow">Recorded checksums · H3</p>
      <h2>Three engines, one answer: <em>identical bytes</em> in every cell.</h2>
      <p className="sub">
        Each arm’s output is ordered by all columns and written through one fixed CSV writer, then hashed with SHA-256 (<a href={blob('src/checksum.py')}>checksum.py</a>).
        Agreement below is worked out in your browser from <a href={blob('results/checksums.json')}>checksums.json</a>. The SF0.1 digests are also the values the CI gate holds in <a href={blob('results/expected_checksums.json')}>expected_checksums.json</a>.
      </p>
      <div style={{ overflowX: 'auto', marginTop: 12 }}>
        <table>
          <thead><tr><th>Cell</th><th>Rows</th>{ARMS.map(([a, n]) => <th key={a}>{n.replace(' model time', '')} run 1</th>)}<th>Arms agree</th><th>Run 5 = run 1</th><th>CI gate</th></tr></thead>
          <tbody>
            {cells.map(([k, v]) => {
              const ds = ARMS.map(([a]) => v.digests_run1[a]);
              const agree = ds.every((d) => d === ds[0]);
              const [s, t] = k.split(':');
              const ci = s === 'sf0.1' ? expected[t] === ds[0] : null;
              return (
                <tr key={k}><td className="mono">{s.toUpperCase()} {t.toUpperCase()}</td><td>{rowsOf(k)?.toLocaleString('en-US')}</td>
                  {ds.map((d, i) => <td key={i} className="mono" title={d}>{d.slice(0, 10)}…</td>)}
                  <td><span className={`pill ${agree ? 'good' : 'bad'}`}>{agree ? 'agree' : 'differ'}</span></td>
                  <td><span className={`pill ${v.deterministic_run5 ? 'good' : 'warn'}`}>{v.deterministic_run5 ? 'yes' : String(v.deterministic_run5)}</span></td>
                  <td>{ci === null ? <span className="hint">SF0.1 only</span> : <span className={`pill ${ci ? 'good' : 'bad'}`}>{ci ? 'held' : 'mismatch'}</span>}</td></tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const FAULT_DESC = { F01: 'Duplicate primary key (o_orderkey)', F02: 'Null primary key', F03: 'Orphan foreign key', F04: 'Negative quantity', F05: 'Bad date format', F06: 'Price stored as a string', F07: 'Duplicate whole row', F08: 'Late row with a changed price', F09: 'Missing column (l_partkey)', F10: 'Stale file (old shipdates)' };

function Faults() {
  const [sel, setSel] = useState('F01');
  const f = EV.faults, row = f.rows.find((r) => r.id === sel);
  return (
    <section id="faults" className="card window reveal" data-title="fault_matrix.dbt — F01 to F10">
      <div className="head">
        <div>
          <p className="eyebrow">Recorded gate runs · H5</p>
          <h2>Ten injected faults, <em>{f.caught} caught</em>, {f.criticalMissed.length} critical faults missed.</h2>
          <p className="sub">
            Faults were injected into copies of the SF0.1 inputs. Staging builds, the dbt gate tests run, and the marts build only if every error-severity test passes.
            F08 is scored by the late-data checksum gate, and F10 is warn severity by design: flagged, then promoted. Click a fault to see which tests fired.
          </p>
        </div>
        <span className="pill good">Catch rate {(f.caught * 10).toFixed(0)}%</span>
      </div>
      <div className="faultgrid" role="group" aria-label="Choose a fault">
        {f.rows.map((r) => (
          <button key={r.id} aria-pressed={sel === r.id} onClick={() => setSel(r.id)} className={r.caught ? 'caught' : 'missed'}>
            <b>{r.id}</b><small>{r.critical ? 'critical' : 'not critical'}</small>
          </button>
        ))}
      </div>
      <div className="grid2" style={{ marginTop: 16 }}>
        <div className="tile">
          <div className="head" style={{ marginBottom: 6 }}><h3>{row.id} · {FAULT_DESC[row.id]}</h3><span className={`pill ${row.caught ? 'good' : 'bad'}`}>{row.caught ? 'caught' : 'missed'}</span></div>
          <dl>
            <dt>Critical</dt><dd>{row.critical ? 'yes' : 'no'}</dd>
            <dt>Outcome</dt><dd>{row.fromIncremental ? 'Every late-data scenario checksum equals the full refresh, so the changed price was applied exactly once (scored from incremental_log.jsonl).' : row.flagged ? 'Flagged stale in the gate log, promotion allowed (warn and flag).' : row.blocked ? 'Promotion blocked: marts were not built.' : 'Promoted.'}</dd>
            <dt>Tests that fired</dt><dd>{row.fired.length ? row.fired.map((n) => <code key={n} className="tname">{n}{row.failures?.[n] === 'error' ? ' (errored)' : ''}</code>) : 'none'}</dd>
          </dl>
          {row.fired.length > 1 && !row.fromIncremental && <p className="hint" style={{ margin: '8px 0 0' }}>More than one gate fired. Only one test is designed for this fault; the others trip as a side effect, which the study does not attribute separately.</p>}
        </div>
        <div style={{ overflowX: 'auto' }}>
          {row.tests ? (
            <table>
              <thead><tr><th>Gate test</th><th>{row.id}</th><th>Clean input</th></tr></thead>
              <tbody>
                {Object.keys(f.clean.tests).map((t) => (
                  <tr key={t}><td className="mono" style={{ wordBreak: 'break-all' }}>{t}</td><td className={row.tests[t] === 'pass' ? 'ok' : 'no'}>{row.tests[t]}</td><td className="ok">{f.clean.tests[t]}</td></tr>
                ))}
              </tbody>
            </table>
          ) : <p className="hint">F08 has no gate-test row: it is scored by checksum equality in the late-data replay below.</p>}
        </div>
      </div>
    </section>
  );
}

function LateData() {
  const bySf = groupIncr(incr), sav = EV.savings;
  const scen = ['full_refresh', 'S1', 'S2', 'S3', 'S3b'];
  const max = Math.max(...Object.values(sav).map((s) => s.full));
  return (
    <section id="late" className="card window reveal" data-title="late_data.replay — H4 and H6">
      <p className="eyebrow">Recorded incremental runs · synthetic late delta</p>
      <h2>Late data never broke the answer. The saving was <em>bigger than predicted</em> at SF1.</h2>
      <p className="sub">
        A small synthetic delta (new orders on existing dates plus one price change) arrives before the run (S1), after staging (S2), after a finished run (S3) or appended to the inputs (S3b).
        Each incremental output for T3 and T4 is compared with a full refresh on base plus delta. The saving is the T3 + T4 dbt model time of S3’s incremental run against the full refresh, one run per scale.
      </p>
      <div style={{ overflowX: 'auto', marginTop: 12 }}>
        <table>
          <thead><tr><th>Scenario</th>{bySfSorted(bySf).map(([sf]) => <th key={sf}>SF{sf} T3 / T4</th>)}</tr></thead>
          <tbody>
            {scen.map((s) => (
              <tr key={s}><td>{s === 'full_refresh' ? 'Full refresh (comparator)' : s}</td>
                {bySfSorted(bySf).map(([sf, rows]) => {
                  const r = rows[s], full = rows.full_refresh;
                  if (s === 'full_refresh') return <td key={sf} className="mono">{r.checksums.t3.sha256.slice(0, 8)}… / {r.checksums.t4.sha256.slice(0, 8)}…</td>;
                  const ok = ['t3', 't4'].every((t) => r.checksums[t].sha256 === full.checksums[t].sha256);
                  return <td key={sf}><span className={`pill ${ok ? 'good' : 'bad'}`}>{ok ? 'equal' : 'differs'}</span></td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="grid2" style={{ marginTop: 20 }}>
        <div>
          <h3>Incremental saving, computed from model_seconds</h3>
          <div className="bars" style={{ marginTop: 12 }}>
            {bySfSorted(sav).flatMap(([sf, s]) => [
              <div className="bar-row" key={`${sf}f`}><div className="lab"><span>SF{sf} full refresh</span><b>{f2(s.full)} s</b></div><div className="track"><div className="fill" style={{ width: `${(s.full / max) * 100}%`, background: 'var(--muted)' }} /></div></div>,
              <div className="bar-row" key={`${sf}i`}><div className="lab"><span>SF{sf} incremental (S3)</span><b>{f2(s.incremental)} s · saves {pct1(s.saving_pct)}</b></div><div className="track"><div className="fill" style={{ width: `${(s.incremental / max) * 100}%`, background: 'var(--dbt)' }} /></div></div>,
            ])}
          </div>
        </div>
        <div className="tile">
          <div className="head" style={{ marginBottom: 6 }}><h3>What this does to H6</h3><span className={`pill ${VPILL[EV.verdicts.H6[0]]}`}>{EV.verdicts.H6[0]}</span></div>
          <p className="hint" style={{ margin: 0, fontSize: 13 }}>
            H6 predicted a saving of at most {RULES.h6Saving}% at SF0.1 and SF1 and above {RULES.h6Saving}% only at SF10. SF10 fits ({pct1(sav['10'].saving_pct)}) and so does SF0.1 ({pct1(sav['0.1'].saving_pct)}), but SF1 is already {pct1(sav['1'].saving_pct)}.
            The large-scale half of the prediction holds and the small-scale half does not. The locked rule needs both, so H6 is refuted; a post-lock reading would call it partially supported (PREREG Deviation 3). Each figure is a single S3 run with no spread.
          </p>
        </div>
      </div>
    </section>
  );
}

const SAMPLE = [['1995-03-04', '7', '20381.50'], ['1994-11-20', '5', '15020.00'], ['1995-03-04', '2', '980.10'], ['1996-01-12', '9', '31210.75']];

function Protocol() {
  const [rows, setRows] = useState(SAMPLE);
  const [sorted, setSorted] = useState(true);
  const [bFloat, setBFloat] = useState(false);
  const [order, setOrder] = useState([3, 1, 0, 2]);
  const [dig, setDig] = useState({});
  const rowsB = order.filter((i) => i < rows.length).map((i) => rows[i]).map((r) => (bFloat ? [r[0], r[1], String(+r[2])] : r));
  const csvA = canonicalCsv(rows, { sort: sorted }), csvB = canonicalCsv(rowsB, { sort: sorted });
  useEffect(() => { let live = true; Promise.all([sha256Hex(csvA), sha256Hex(csvB)]).then(([a, b]) => live && setDig({ a, b })); return () => { live = false; }; }, [csvA, csvB]);
  const same = dig.a && dig.a === dig.b;
  const edit = (i, j, val) => setRows((rs) => rs.map((r, k) => (k === i ? r.map((c, m) => (m === j ? val : c)) : r)));
  const shuffle = () => setOrder((o) => { const n = [...o]; n.push(n.shift()); [n[0], n[2]] = [n[2], n[0]]; return n; });
  const cols = ['order_date', 'orders_count', 'gross_revenue'];
  return (
    <section id="protocol" className="card window reveal" data-title="checksum_protocol.play — live SHA-256">
      <div className="head">
        <div>
          <p className="eyebrow">Live in your browser · crypto.subtle</p>
          <h2>Why two different engines can produce the <em>same hash</em>.</h2>
          <p className="sub">
            Engines return rows in whatever order their parallel plan finishes, and each has its own way of printing a decimal. The study removes both: every output is sorted by all columns and written by one fixed CSV writer before hashing.
            Below, engine A and engine B hold the same made-up rows (example input, not study data). Edit a cell, shuffle B’s order, or let B print decimals its own way, and watch the two SHA-256 digests.
          </p>
        </div>
        <span className={`pill ${same ? 'good' : 'bad'}`}>{same ? 'digests match' : 'digests differ'}</span>
      </div>
      <div className="grid2">
        <div style={{ overflowX: 'auto' }}>
          <table className="edit">
            <thead><tr>{cols.map((c) => <th key={c} className="mono">{c}</th>)}</tr></thead>
            <tbody>
              {rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}><input aria-label={`Row ${i + 1} ${cols[j]}`} value={c} onChange={(e) => edit(i, j, e.target.value)} /></td>)}</tr>)}
            </tbody>
          </table>
          <div className="actions" style={{ marginTop: 12 }}>
            <button className="btn ghost" onClick={shuffle}>Shuffle engine B’s row order</button>
            <button className="btn ghost" onClick={() => { setRows(SAMPLE); setOrder([3, 1, 0, 2]); setSorted(true); setBFloat(false); }}>Reset</button>
          </div>
          <label className="check"><input type="checkbox" checked={sorted} onChange={(e) => setSorted(e.target.checked)} /> Canonical ORDER BY all columns before writing</label>
          <label className="check"><input type="checkbox" checked={bFloat} onChange={(e) => setBFloat(e.target.checked)} /> Engine B writes decimals its own way (drops trailing zeros)</label>
        </div>
        <div className="digests">
          {[['A', csvA, dig.a], ['B', csvB, dig.b]].map(([n, csv, d]) => (
            <div key={n} className="tile">
              <h3>Engine {n} · bytes hashed</h3>
              <pre>{csv}</pre>
              <div className="mono hash">{d || '…'}</div>
            </div>
          ))}
        </div>
      </div>
      <p className="hint">This is the same idea as <a href={blob('src/checksum.py')}>checksum.py</a> (ORDER BY all output columns, COPY to CSV with a '|' delimiter, no header). In the study all monetary columns are exact decimals, so sums do not drift between engines either.</p>
    </section>
  );
}

function Threats() {
  const threats = mdList(methodsMd, '## Threats to validity');
  const roadmap = mdList(roadmapMd, 'in evidence order.');
  const reviewOpen = /Reviewer: \(open\)/.test(reviewMd);
  const own = [
    `H2 is refuted only inside the ladder tested: no crossover up to SF10 (best D/S ${f3(BEST10[1])}). SF30 was cut before pre-registration as a machine limit, so nothing here says what happens above SF10.`,
    'With H2 and H6 refuted, the study does not pass its own all-hypotheses rule (PREREG Section 2).',
    `The H6 savings and every late-data scenario rest on one run per scale; the timing cells have ${N_RUNS} runs each and setup overhead one, so there are no significance tests, only means, SDs, CVs and bootstrap intervals.`,
    `${HIGH_CV.length} DuckDB cells at SF0.1 and SF1 (${HIGH_CV.join(', ')}) exceed the ${RULES.cvLine}% CV line and were not re-run (PREREG Deviation 2).`,
    `${HIGH_CV10.length} DuckDB cells at SF10 (${HIGH_CV10.join(', ')}) also exceed it, recorded under co-tenant load on the same VM and across VM restarts in the SF10 sequence (AUDIT.md).`,
    `When a fault trips more than one gate (${EV.faults.rows.filter((r) => !r.fromIncremental && r.fired?.length > 1).map((r) => r.id).join(', ')}), the study does not separate the designed gate from side effects.`,
    'Arms A and B time execution plus write; Arm C uses dbt’s execution_time. The bases differ, so dbt is never ratioed against the engines.',
  ];
  return (
    <section id="threats" className="reveal">
      <div className="grid2 tw">
        <div className="card window" data-title="threats.txt — limits of this evidence">
          <p className="eyebrow">Threats to validity</p>
          <h2>What this study <em>cannot</em> tell you.</h2>
          <ul className="list">
            {own.map((t) => <li key={t}>{t}</li>)}
            <li>{reviewOpen ? 'No independent reviewer has signed REVIEW.md, so the study is UNVERIFIED for review status by its own rule.' : 'See REVIEW.md for the independent review.'}</li>
            {threats.map((t) => <li key={t}>{t}</li>)}
          </ul>
        </div>
        <div className="card window" data-title="report.md — what remains">
          <p className="eyebrow">Roadmap</p>
          <h2>Next evidence, <em>in order</em>.</h2>
          <ol className="list">{roadmap.map((t) => <li key={t}>{t}</li>)}</ol>
          <div className="docs" style={{ marginTop: 16, gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}>
            {[['PREREG.md', 'Pre-registration'], ['METHODS.md', 'Methods'], ['RESULTS.md', 'Results (generated)'], ['AUDIT.md', 'Audit'], ['DECISIONS.md', 'Decisions'], ['REPORT.md', 'Report']].map(([p, t]) => <a key={p} href={blob(p)}><b>{t}</b><small>{p}</small></a>)}
          </div>
        </div>
      </div>
    </section>
  );
}
