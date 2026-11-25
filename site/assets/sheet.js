// Drafting-sheet pieces: preloader, hero sheet (line drawing, mm cursor readout, drag-to-inspect
// callouts), marquee, statement, isometric module icons, manifesto, CTA coordinates, footer wordmark.
// Every number shown comes from data.json.
import { L, fmt, esc } from './charts.js';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const html = document.documentElement;
const clamp01 = (x) => Math.max(0, Math.min(1, x));

/* ------------------------------------------------------------------ */
/* shared: which DFM findings belong to which bend                      */
/* Elongation (rule D8) is governed by the tightest CLR, so it is pinned */
/* to the bends at the minimum CLR; anything else is part-level.         */
/* ------------------------------------------------------------------ */
export function findingsByBend(part, rep) {
  const per = part.lra.map(() => []), global = [];
  if (!rep || !Array.isArray(rep.findings)) return { per, global };
  const minClr = Math.min(...part.lra.map((r) => r.CLR));
  rep.findings.forEach((f) => {
    if (f.status === 'pass') return;
    if (f.rule === 'D8' || /elongation/i.test(f.title || '')) part.lra.forEach((r, i) => { if (Math.abs(r.CLR - minClr) < 1e-9) per[i].push(f); });
    else global.push(f);
  });
  return { per, global };
}
const STATUS = { pass: ['PASS', '合格'], warn: ['WARN', '注意'], fail: ['FAIL', '不可'] };
export const statusChip = (st) => `<span class="status ${esc(st)}">${L(...(STATUS[st] || [st, st]))}</span>`;

/* front view (X, Z) path of a part, in mm, screen y = -z */
function frontPath(pts) { return pts.map((q, i) => `${i ? 'L' : 'M'}${q[0].toFixed(2)},${(-q[2]).toFixed(2)}`).join(''); }
function topPath(pts, dy) { return pts.map((q, i) => `${i ? 'L' : 'M'}${q[0].toFixed(2)},${(-q[1] + dy).toFixed(2)}`).join(''); }

/* ------------------------------------------------------------------ */
/* preloader: the handlebar's views draw, title block and log type in   */
/* ------------------------------------------------------------------ */
export function preloader(d, part, full) {
  const el = $('#preloader');
  const done = () => {
    html.classList.remove('preload');
    $('#main').setAttribute('aria-busy', 'false');
    try { sessionStorage.setItem('pf-seen', '1'); } catch { /* private mode */ }
  };
  if (!html.classList.contains('preload')) { done(); return Promise.resolve(); }
  if (!full || !window.gsap) { done(); return Promise.resolve(); }
  const gsap = window.gsap;

  // drawing: top view above front view (third angle), plus the CL datum through the front view
  const cl = part.centerline, r = part.od / 2;
  const xs = cl.map((q) => q[0]), ys = cl.map((q) => q[1]), zs = cl.map((q) => q[2]);
  const x0 = Math.min(...xs) - r, x1 = Math.max(...xs) + r;
  const yext = Math.max(...ys) - Math.min(...ys) + 2 * r, zext = Math.max(...zs) - Math.min(...zs) + 2 * r;
  const gap = Math.max(yext, zext) * 0.9;
  const dy = -(zext / 2 + gap + yext / 2);           // top view sits above the front view
  const top = -(Math.max(...zs) + r) + dy - yext / 2 - 20, bottom = -(Math.min(...zs) - r) + 26;
  const w = x1 - x0;
  $('#pl-dwg').innerHTML = `<svg viewBox="${x0 - 30} ${top} ${w + 60} ${bottom - top}" aria-hidden="true">
    <path class="pv" pathLength="1" d="${topPath(cl, dy)}" stroke-width="${part.od}" style="stroke-opacity:.14"/>
    <path class="pv" pathLength="1" d="${topPath(cl, dy)}"/>
    <path class="pv" pathLength="1" d="${frontPath(cl)}" stroke-width="${part.od}" style="stroke-opacity:.14"/>
    <path class="pv" pathLength="1" d="${frontPath(cl)}"/>
    <line class="pv-cl" x1="${x0 - 24}" x2="${x1 + 24}" y1="0" y2="0"/>
    <text class="pv-lbl" x="${x1 + 28}" y="4">CL</text>
    <text class="pv-t" x="${x0 - 24}" y="${dy - yext / 2 - 6}">TOP · X–Y</text>
    <text class="pv-t" x="${x0 - 24}" y="${-(Math.max(...zs) + r) - 6}">FRONT · X–Z</text>
  </svg>`;
  const rows = [
    ['Part', part.part_no], ['Matl', part.material], ['OD × t', `${fmt(part.od, 1)} × t${fmt(part.wall, 1)}`],
    ['Bends', fmt(part.lra.length)], ['Cut', `${fmt(part.cut_length, 2)} mm`],
  ];
  $('#pl-block').innerHTML = rows.map(([k]) => `<dt>${esc(k)}</dt><dd data-t></dd>`).join('');
  const log = [
    [`Geometry · ${fmt(d.parts.length)} parts`],
    [`LRA · ${fmt(part.lra.length)} bends`],
    d.dfm ? [`DFM · ${fmt(d.dfm.length)} reports`] : null,
    d.springback ? [`Springback model · ${fmt(d.springback.n_runs)} runs`] : null,
    d.kaizen ? [`Line sim · ${fmt(d.kaizen.rows.length)} scenarios`] : null,
  ].filter(Boolean).map(([t], i) => `${String(i + 1).padStart(3, '0')} ${t}`);
  $('#pl-log').innerHTML = log.map(() => '<li></li>').join('');

  return new Promise((resolve) => {
    let finished = false;
    const tl = gsap.timeline({ onComplete: () => finish() });
    const paths = $$('#pl-dwg .pv');
    tl.fromTo(paths, { strokeDasharray: 1, strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 0.95, ease: 'power2.inOut', stagger: 0.08 }, 0);
    tl.fromTo('#pl-dwg .pv-cl', { opacity: 0 }, { opacity: 1, duration: 0.3 }, 0.55);
    const type = (node, text, at, dur) => {
      const o = { n: 0 };
      tl.to(o, { n: text.length, duration: dur, ease: 'none', onUpdate: () => { node.textContent = text.slice(0, Math.round(o.n)); } }, at);
    };
    $$('#pl-block dd').forEach((dd, i) => type(dd, rows[i][1], 0.15 + i * 0.16, 0.22));
    $$('#pl-log li').forEach((li, i) => {
      const at = 0.75 + i * 0.2;
      type(li, log[i], at, 0.16);
      tl.call(() => { li.insertAdjacentHTML('beforeend', ' <span class="ok">· OK</span>'); }, null, at + 0.18);
    });
    tl.to({}, { duration: 0.12 });           // ends by about 1.8 s; fade-out brings it to at most 2.2 s
    const cap = setTimeout(() => finish(), 1800);   // wall-clock cap, even if animation frames are throttled
    function finish() {
      if (finished) return;
      finished = true;
      clearTimeout(cap);
      tl.progress(1).kill();
      el.classList.add('out');
      removeEventListener('keydown', skip);
      setTimeout(() => { done(); resolve(); }, 400);
    }
    function skip(e) { if (e && e.type === 'keydown' && e.key === 'Tab') return; finish(); }
    $('#pl-skip').addEventListener('click', skip);
    el.addEventListener('pointerdown', skip);
    addEventListener('keydown', skip);
  });
}

/* ------------------------------------------------------------------ */
/* hero sheet: line drawing, mm readout, drag-to-inspect callouts       */
/* ------------------------------------------------------------------ */
export function heroSheet(part, rep) {
  const svg = $('#hero-dwg'), stage = $('#hero-stage'), hero = $('#hero');
  const cl = part.centerline, r = part.od / 2;
  const xs = cl.map((q) => q[0]), zs = cl.map((q) => q[2]);
  const x0 = Math.min(...xs) - r - 10, x1 = Math.max(...xs) + r + 10, z0 = Math.min(...zs) - r - 10, z1 = Math.max(...zs) + r + 10;
  svg.setAttribute('viewBox', `${x0} ${-z1} ${x1 - x0} ${z1 - z0}`);
  const d = frontPath(cl);
  svg.innerHTML = `<line class="hd-axis" x1="${x0}" x2="${x1}" y1="0" y2="0" stroke-dasharray="6 6"/>
    <path class="hd-tube hd-draw" pathLength="1" d="${d}" stroke-width="${part.od}"/>
    <path class="hd-in" d="${d}" stroke-width="${Math.max(0.5, part.od - 2 * part.wall)}"/>
    <path class="hd-sharp" d="${frontPath(part.points)}"/>
    <path class="hd-cl" d="${d}"/>
    ${part.points.map((q) => `<circle class="hd-pt" cx="${q[0]}" cy="${-q[2]}" r="${(part.od * 0.32).toFixed(2)}"/>`).join('')}`;
  $('#hero-sheet-label').textContent = `${part.part_no} · ${part.material} · FRONT VIEW X–Z · MM`;

  const fine = matchMedia('(pointer: fine)').matches;
  const { per } = findingsByBend(part, rep);
  const callouts = $('#hero-callouts');
  callouts.innerHTML = part.bends.map((b, k) => {
    const row = part.lra[k];
    const f = per[k] || [];
    return `<div class="co" data-k="${k}"><i class="co-lead"></i><i class="co-dot"></i><div class="co-box">
      <b>B${k + 1} · ${L('Bend', '曲げ')}</b>
      <span>A ${fmt(row.A, 2)}° · R ${fmt(row.R, 1)}°</span>
      <span>CLR ${fmt(row.CLR, 1)} MM · ${fmt(row.CLR / part.od, 2)} D</span>
      <span>L ${fmt(row.L, 2)} MM</span>
      ${f.length ? f.map((x) => `<span class="co-find">${statusChip(x.status)}<b style="display:inline;background:none;padding:0">${esc(x.rule)}</b> ${esc(x.title)}</span>`).join('') : `<span class="co-find">${L('No DFM rule flagged here', 'DFM指摘なし')}</span>`}
    </div></div>`;
  }).join('');
  const cos = $$('.co', callouts);

  let enabled = true, shown = new Set(), inspecting = false;
  const toScreen = (x, z) => {
    const m = svg.getScreenCTM(); if (!m) return null;
    const pt = svg.createSVGPoint(); pt.x = x; pt.y = -z;
    const p = pt.matrixTransform(m), rs = stage.getBoundingClientRect();
    return { x: p.x - rs.left, y: p.y - rs.top };
  };
  function place() {
    const rs = stage.getBoundingClientRect();
    cos.forEach((co, k) => {
      const b = part.bends[k], s = toScreen(b.point[0], b.point[2]);
      if (!s) return;
      const up = k % 2 === 0, right = s.x < rs.width * 0.5;
      const dx = right ? 46 : -46, dy = up ? -64 : 64;
      co.style.transform = `translate(${s.x}px, ${s.y}px)`;
      const lead = co.querySelector('.co-lead'), box = co.querySelector('.co-box');
      lead.style.width = `${Math.hypot(dx, dy)}px`;
      lead.style.transform = `rotate(${Math.atan2(dy, dx)}rad)`;
      const bw = box.offsetWidth || 220, bh = box.offsetHeight || 120;
      let bx = right ? dx : dx - bw, by = up ? dy - bh : dy;
      bx = Math.max(-s.x + 8, Math.min(rs.width - s.x - bw - 8, bx));     // keep inside the stage
      by = Math.max(-s.y + 70, Math.min(rs.height - s.y - bh - 8, by));
      box.style.left = `${bx}px`; box.style.top = `${by}px`;
    });
  }
  function setInspect(on) {
    inspecting = on;
    hero.classList.toggle('inspecting', on);
    if (!on) { shown.clear(); cos.forEach((c) => c.classList.remove('on')); }
  }
  function show(keys) {
    shown = new Set(keys);
    setInspect(shown.size > 0);
    place();
    cos.forEach((c) => c.classList.toggle('on', shown.has(+c.dataset.k)));
    const btn = $('#inspect-btn');
    btn.setAttribute('aria-pressed', String(shown.size === part.bends.length));
  }
  $('#inspect-btn').addEventListener('click', () => {
    if (shown.size) show([]); else show(part.bends.map((_, k) => k));
  });
  addEventListener('keydown', (e) => { if (e.key === 'Escape' && inspecting) show([]); });
  new ResizeObserver(() => { if (inspecting) place(); }).observe(stage);

  // cursor readout and rubber-band selection: fine pointers only
  const cur = $('#cursor'), read = $('#cursor-read'), cx = cur.querySelector('.cx'), cy = cur.querySelector('.cy'), box = $('#sel-box');
  let drag = null;
  if (fine) {
    stage.addEventListener('pointermove', (e) => {
      if (!enabled) return;
      const rs = stage.getBoundingClientRect(), m = svg.getScreenCTM();
      const x = e.clientX - rs.left, y = e.clientY - rs.top;
      hero.classList.add('has-cursor');
      cx.style.transform = `translateY(${y}px)`; cy.style.transform = `translateX(${x}px)`;
      if (m) {
        const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
        const p = pt.matrixTransform(m.inverse());
        read.textContent = `X ${fmt(p.x, 1)} MM · Z ${fmt(-p.y, 1)} MM`;
      }
      read.style.transform = `translate(${Math.min(x + 14, rs.width - 210)}px, ${y + 14}px)`;
      if (drag) {
        const l = Math.min(drag.x, x), t = Math.min(drag.y, y), w = Math.abs(x - drag.x), h = Math.abs(y - drag.y);
        Object.assign(box.style, { left: `${l}px`, top: `${t}px`, width: `${w}px`, height: `${h}px` });
        if (w + h > 8) { box.classList.add('on'); setInspect(true); }
      }
    });
    stage.addEventListener('pointerleave', () => hero.classList.remove('has-cursor'));
    stage.addEventListener('pointerdown', (e) => {
      if (!enabled || e.button !== 0) return;
      const rs = stage.getBoundingClientRect();
      drag = { x: e.clientX - rs.left, y: e.clientY - rs.top };
      stage.setPointerCapture(e.pointerId);
    });
    stage.addEventListener('pointerup', (e) => {
      if (!drag) return;
      const rs = stage.getBoundingClientRect();
      const x = e.clientX - rs.left, y = e.clientY - rs.top;
      const l = Math.min(drag.x, x), t = Math.min(drag.y, y), rgt = Math.max(drag.x, x), btm = Math.max(drag.y, y);
      drag = null; box.classList.remove('on');
      if (rgt - l + btm - t < 8) { show([]); return; }
      const hits = part.bends.map((b, k) => ({ k, s: toScreen(b.point[0], b.point[2]) }))
        .filter(({ s }) => s && s.x >= l && s.x <= rgt && s.y >= t && s.y <= btm).map(({ k }) => k);
      show(hits);
    });
  } else {
    $('#inspect-hint').hidden = true;
  }
  return {
    setEnabled(on) {
      if (on === enabled) return;
      enabled = on;
      $('.hero-top').style.opacity = on ? '' : '0';
      if (!on) { show([]); hero.classList.remove('has-cursor'); }
    },
    setRenderReady() { html.classList.add('render-ready'); },
    drawOn() {
      if (!window.gsap) return;
      window.gsap.fromTo('#hero-dwg .hd-draw', { strokeDasharray: 1, strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 1.2, ease: 'power2.inOut', clearProps: 'strokeDasharray,strokeDashoffset' });
    },
  };
}

/* ------------------------------------------------------------------ */
/* marquee of data-driven tags                                          */
/* ------------------------------------------------------------------ */
export function marquee(d) {
  const sb = d.springback, cl = d.closed_loop, items = [];
  const b = (v) => `<b>${v}</b>`;
  if (sb) items.push([`${b(fmt(sb.n_runs))} real bends`, `実曲げ ${b(fmt(sb.n_runs))} 本`]);
  if (sb && sb.best && sb.springback && sb.springback[sb.best.setup]) {
    const m = sb.springback[sb.best.setup].mae; const v = typeof m === 'object' ? m.mean : m;
    items.push([`MAE ${b(fmt(v, 3) + '°')} unseen setups`, `未知の設定で MAE ${b(fmt(v, 3) + '°')}`]);
  }
  if (cl && cl.fpy && cl.fpy.ml != null) items.push([`${b(fmt(cl.fpy.ml * 100, 1) + ' %')} within ±${fmt(cl.tolerance_deg, 1)}°`, `±${fmt(cl.tolerance_deg, 1)}° 以内 ${b(fmt(cl.fpy.ml * 100, 1) + ' %')}`]);
  if (sb && sb.physics) items.push([`physics ${b(fmt(sb.physics.mid, 2) + '°')} vs measured ${b(fmt(sb.target_mean, 2) + '°')}`, `理論 ${b(fmt(sb.physics.mid, 2) + '°')} / 実測 ${b(fmt(sb.target_mean, 2) + '°')}`]);
  items.push([`${b(fmt(d.parts.length))} sample parts`, `サンプル部品 ${b(fmt(d.parts.length))}`]);
  const mats = [...new Set(d.parts.map((p) => p.material))];
  items.push([`JIS / material: ${mats.map(esc).join(' · ')}`, `材質：${mats.map(esc).join('・')}`]);
  if (Array.isArray(d.dfm)) {
    const pass = d.dfm.reduce((a, r) => a + (r.counts ? r.counts.pass : 0), 0);
    items.push([`${b(fmt(d.dfm.length))} DFM reports · ${b(fmt(pass))} checks pass`, `DFM ${b(fmt(d.dfm.length))} 件 · 合格 ${b(fmt(pass))}`]);
  }
  if (d.fixture) items.push([`${b(fmt(d.fixture.blocks.length))} fixture blocks · 3-2-1`, `受けブロック ${b(fmt(d.fixture.blocks.length))} · 3-2-1`]);
  if (d.line) items.push([`takt ${b(fmt(d.line.takt_s, 1) + ' s')} · ${b(fmt(d.line.stations.length))} stations`, `タクト ${b(fmt(d.line.takt_s, 1) + ' 秒')} · ${b(fmt(d.line.stations.length))} 工程`]);
  if (d.kaizen) items.push([`${b('+' + fmt(d.kaizen.throughput_gain_pct, 1) + ' %')} good parts/day (synthetic line)`, `良品数 ${b('+' + fmt(d.kaizen.throughput_gain_pct, 1) + ' %')}（合成ライン）`]);
  if (sb) items.push([`GroupKFold ${b(fmt(sb.folds) + ' × ' + fmt(sb.repeats))}`, `GroupKFold ${b(fmt(sb.folds) + ' × ' + fmt(sb.repeats))}`]);
  const set = items.map(([en, ja]) => `<span class="mq-item"><i class="dia" aria-hidden="true"></i>${L(en, ja)}</span>`).join('');
  $('#mq-track').innerHTML = `<div class="mq-set">${set}</div><div class="mq-set" aria-hidden="true">${set}</div>`;
}

/* ------------------------------------------------------------------ */
/* statement: physics vs measured, word-by-word fill                    */
/* ------------------------------------------------------------------ */
function words(text, lang) {
  let toks;
  if (lang === 'ja' && 'Segmenter' in Intl) toks = [...new Intl.Segmenter('ja', { granularity: 'word' }).segment(text)].map((s) => s.segment);
  else if (lang === 'ja') toks = [...text];
  else toks = text.split(/(\s+)/);
  return toks.map((t) => (/^\s+$/.test(t) ? t : `<span class="w${/\d/.test(t) ? ' num' : ''}">${esc(t)}</span>`)).join('');
}
export function statement(d, bendCfg) {
  const sb = d.springback, cl = d.closed_loop;
  let en, ja;
  if (sb && sb.physics) {
    const fpy = cl && cl.fpy && cl.fpy.ml != null ? cl.fpy.ml * 100 : null;
    en = `The textbook predicts ${fmt(sb.physics.mid, 2)}° of springback. ${fmt(sb.n_runs)} real bends measured ${fmt(sb.target_mean, 2)}°.` +
      (fpy != null ? ` A model trained on them puts ${fmt(fpy, 1)}% of bends inside ±${fmt(cl.tolerance_deg, 1)}°.` : '');
    ja = `教科書の式は${fmt(sb.physics.mid, 2)}°のスプリングバックを予測。実際の曲げ${fmt(sb.n_runs)}本の実測は${fmt(sb.target_mean, 2)}°。` +
      (fpy != null ? `それらで学習したモデルは、曲げの${fmt(fpy, 1)}%を±${fmt(cl.tolerance_deg, 1)}°以内に収めます。` : '');
  } else {
    en = 'The textbook estimate and the machine disagree. PipeForge learns the gap from real bends.';
    ja = '教科書の推定と実機は一致しません。PipeForgeは実際の曲げからその差を学習します。';
  }
  $('#statement-text').innerHTML = `<span class="l" lang="en">${words(en, 'en')}</span><span class="l" lang="ja">${words(ja, 'ja')}</span>`;

  // figure: bend die, released tube (ink) and the overbend (accent), angles from the data
  if (!bendCfg) return;
  const A = bendCfg.targetDeg, sbv = bendCfg.springbackDeg, ex = bendCfg.exaggeration || 1;
  const R = 100, Ll = 120, Lt = 150, cx = 200, cy = 60;
  const D2R = Math.PI / 180;
  const tube = (deg) => {
    const t = deg * D2R;
    const sx = cx - Lt, ex0 = cx + R * Math.sin(t), ey0 = cy + R * (1 - Math.cos(t));
    return `M${sx},${cy} L${cx},${cy} A${R},${R} 0 0 1 ${ex0.toFixed(2)},${ey0.toFixed(2)} L${(ex0 + Ll * Math.cos(t)).toFixed(2)},${(ey0 + Ll * Math.sin(t)).toFixed(2)}`;
  };
  const over = sbv ? A + sbv * ex : A;
  const arcR = R + 46, a1 = A * D2R, a2 = over * D2R;
  $('#st-dwg').innerHTML = `<svg viewBox="24 -4 420 290" aria-hidden="true">
    <circle class="sd-die st-draw" pathLength="1" cx="${cx}" cy="${cy + R}" r="${R - 12}"/>
    <circle class="sd-hidden" cx="${cx}" cy="${cy + R}" r="${R + 12}"/>
    <line class="sd-hidden" x1="${cx}" y1="${cy + R}" x2="${cx}" y2="${cy - 20}"/>
    ${sbv ? `<path class="sd-over st-fade" d="${tube(over)}"/>` : ''}
    <path class="sd-tube st-draw" pathLength="1" d="${tube(A)}"/>
    <path class="sd-arc st-draw" pathLength="1" d="M${cx},${cy + R - arcR} A${arcR},${arcR} 0 0 1 ${(cx + arcR * Math.sin(a1)).toFixed(2)},${(cy + R - arcR * Math.cos(a1)).toFixed(2)}"/>
    <text class="sd-t st-fade" x="${cx + arcR * Math.sin(a1 / 2) + 10}" y="${cy + R - arcR * Math.cos(a1 / 2)}">A ${fmt(A, 1)}°</text>
    ${sbv ? `<text class="sd-ta st-fade" x="${cx + (arcR + 26) * Math.sin(a2) + 6}" y="${cy + R - (arcR + 26) * Math.cos(a2) + 18}">+${fmt(sbv, 2)}° SB</text>` : ''}
    <text class="sd-t st-fade" x="${cx - Lt}" y="${cy - 14}">CLR ${fmt(bendCfg.clr, 0)} · Ø${fmt(bendCfg.od, 1)}</text>
  </svg>`;
  $('#st-cap').innerHTML = sbv
    ? L(`Bend 1, ${esc(bendCfg.partNo || '')}: dashed = overbend, springback drawn ×${ex}`, `曲げ1（${esc(bendCfg.partNo || '')}）：破線はオーバーベンド、スプリングバックは×${ex}で表示`)
    : L('Bend 1: springback pending', '曲げ1：スプリングバック未生成');
}
export function statementMotion() {
  const { gsap } = window;
  const groups = $$('#statement-text .l').map((g) => $$('.w', g));
  const fill = (p) => groups.forEach((ws) => { const k = Math.round(p * ws.length); ws.forEach((w, i) => w.classList.toggle('on', i < k)); });
  const o = { p: 0 };
  fill(0);
  gsap.to(o, { p: 1, ease: 'none', onUpdate: () => fill(o.p), scrollTrigger: { trigger: '#statement', start: 'top 72%', end: 'bottom 55%', scrub: 0.6 } });
  const draws = $$('#st-dwg .st-draw'), fades = $$('#st-dwg .st-fade');
  if (draws.length) gsap.fromTo(draws, { strokeDasharray: 1, strokeDashoffset: 1 }, { strokeDashoffset: 0, ease: 'none', stagger: 0.15, scrollTrigger: { trigger: '#statement', start: 'top 75%', end: 'center 45%', scrub: 0.6 } });
  if (fades.length) gsap.fromTo(fades, { opacity: 0 }, { opacity: 1, ease: 'none', stagger: 0.1, scrollTrigger: { trigger: '#statement', start: 'top 45%', end: 'center 40%', scrub: 0.6 } });
}

/* ------------------------------------------------------------------ */
/* isometric line icons for the modules grid (hidden lines dashed)      */
/* ------------------------------------------------------------------ */
const ISO = ([x, y, z]) => [(x - y) * 0.866, (x + y) * 0.5 - z];
function isoSvg(lines) {
  const all = lines.flatMap((l) => l.pts.map(ISO));
  const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]);
  const x0 = Math.min(...xs) - 6, y0 = Math.min(...ys) - 6, w = Math.max(...xs) - x0 + 6, h = Math.max(...ys) - y0 + 6;
  const d = (pts) => pts.map(ISO).map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('');
  return `<svg viewBox="${x0.toFixed(1)} ${y0.toFixed(1)} ${w.toFixed(1)} ${h.toFixed(1)}" aria-hidden="true">${lines.map((l) => `<path class="${l.c}" d="${d(l.pts)}"/>`).join('')}</svg>`;
}
const ring = (c, r, plane, a0 = 0, a1 = 360, n = 48) => Array.from({ length: n + 1 }, (_, i) => {
  const t = (a0 + (a1 - a0) * i / n) * Math.PI / 180, u = r * Math.cos(t), v = r * Math.sin(t);
  return plane === 'xy' ? [c[0] + u, c[1] + v, c[2]] : plane === 'yz' ? [c[0], c[1] + u, c[2] + v] : [c[0] + u, c[1], c[2] + v];
});
const box = (x, y, z, a, b, c, cls = 'iso', hid = 'iso-h') => {
  const P = (i, j, k) => [x + i * a, y + j * b, z + k * c];
  return [
    { c: hid, pts: [P(0, 0, 0), P(1, 0, 0)] }, { c: hid, pts: [P(0, 0, 0), P(0, 1, 0)] }, { c: hid, pts: [P(0, 0, 0), P(0, 0, 1)] },
    { c: cls, pts: [P(1, 0, 0), P(1, 1, 0), P(0, 1, 0)] }, { c: cls, pts: [P(1, 0, 0), P(1, 0, 1)] }, { c: cls, pts: [P(0, 1, 0), P(0, 1, 1)] },
    { c: cls, pts: [P(1, 1, 0), P(1, 1, 1)] }, { c: cls, pts: [P(0, 0, 1), P(1, 0, 1), P(1, 1, 1), P(0, 1, 1), P(0, 0, 1)] },
  ];
};
const ICONS = {
  tube() {   // a bent tube: straight along x, 90° bend around z, straight along y
    const R = 26, r = 8, Lx = 60, Ly = 50, out = [];
    const cl = [[0, 0, 0], [Lx, 0, 0], ...ring([Lx, R, 0], R, 'xy', -90, 0, 16).slice(1), [Lx + R, R + Ly, 0]];
    for (const dz of [-r, r]) out.push({ c: 'iso', pts: cl.map((p) => [p[0], p[1], p[2] + dz]) });
    out.push({ c: 'iso-a', pts: cl });
    out.push({ c: 'iso', pts: ring([0, 0, 0], r, 'yz') });
    out.push({ c: 'iso', pts: ring([Lx + R, R + Ly, 0], r, 'xz') });
    return out;
  },
  die() {    // bend die: a grooved disc, tube tangent to it
    const R = 40, H = 16, out = [];
    out.push({ c: 'iso', pts: ring([0, 0, H], R, 'xy') });
    out.push({ c: 'iso', pts: ring([0, 0, 0], R, 'xy', -45, 135) });
    out.push({ c: 'iso-h', pts: ring([0, 0, 0], R, 'xy', 135, 315) });
    out.push({ c: 'iso', pts: ring([0, 0, H / 2], R - 5, 'xy', -45, 135) });
    out.push({ c: 'iso', pts: ring([0, 0, H], 9, 'xy') });
    out.push({ c: 'iso', pts: [[R * Math.cos(-Math.PI / 4), R * Math.sin(-Math.PI / 4), 0], [R * Math.cos(-Math.PI / 4), R * Math.sin(-Math.PI / 4), H]] });
    out.push({ c: 'iso', pts: [[R * Math.cos(3 * Math.PI / 4), R * Math.sin(3 * Math.PI / 4), 0], [R * Math.cos(3 * Math.PI / 4), R * Math.sin(3 * Math.PI / 4), H]] });
    out.push({ c: 'iso-a', pts: [[-70, R + 4, H / 2], [0, R + 4, H / 2], ...ring([0, 0, H / 2], R + 4, 'xy', 90, 20, 10)] });
    return out;
  },
  block() {  // U-nest locating block with the tube in its groove
    const a = 40, b = 46, c = 30, g = 10, out = box(0, 0, 0, a, b, c);
    out.push({ c: 'iso', pts: ring([a, b / 2, c], g, 'yz', 180, 360) });
    out.push({ c: 'iso-h', pts: ring([0, b / 2, c], g, 'yz', 180, 360) });
    out.push({ c: 'iso-a', pts: [[-30, b / 2, c], [a + 34, b / 2, c]] });
    out.push({ c: 'iso-a', pts: ring([a + 34, b / 2, c], 7, 'yz') });
    return out;
  },
  line() {   // three stations on a line, the middle one is the bottleneck
    const out = [];
    [0, 50, 100].forEach((x, i) => box(x, 0, 0, 30, 30, i === 1 ? 40 : 24, i === 1 ? 'iso-a' : 'iso').forEach((l) => out.push(l)));
    out.push({ c: 'iso', pts: [[-12, 42, 0], [142, 42, 0]] });
    out.push({ c: 'iso-h', pts: [[-12, -10, 0], [142, -10, 0]] });
    return out;
  },
};
export function moduleIcons() {
  $$('.mod-ico[data-ico]').forEach((el) => { const f = ICONS[el.dataset.ico]; if (f) el.innerHTML = isoSvg(f()); });
}

/* ------------------------------------------------------------------ */
/* manifesto: one centred line at a time, grey to ink                   */
/* ------------------------------------------------------------------ */
export function manifestoMotion() {
  const { gsap } = window;
  const lis = $$('#mf-lines li'), n = lis.length, num = $('#mf-i');
  const apply = (p) => {
    const seg = Math.min(n - 1e-6, p * n), i = Math.floor(seg), f = seg - i;
    lis.forEach((li, j) => {
      if (j !== i) { li.style.opacity = '0'; return; }
      const fadeIn = j === 0 ? 1 : clamp01(f / 0.14), fadeOut = j === n - 1 ? 1 : clamp01((1 - f) / 0.14);
      li.style.opacity = String(Math.min(fadeIn, fadeOut));
      li.style.setProperty('--f', clamp01((f - 0.08) / 0.5).toFixed(3));
      li.style.transform = `translateY(calc(-50% + ${((0.5 - f) * 24).toFixed(1)}px))`;
    });
    num.textContent = String(i + 1).padStart(2, '0');
  };
  const o = { p: 0 };
  apply(0);
  gsap.to(o, { p: 1, ease: 'none', onUpdate: () => apply(o.p), scrollTrigger: { trigger: '#manifesto', start: 'top top', end: 'bottom bottom', scrub: 0.6 } });
  return () => lis.forEach((li) => { li.style.opacity = ''; li.style.transform = ''; li.style.removeProperty('--f'); });
}

/* ------------------------------------------------------------------ */
/* CTA grid coordinates (real XYZ of the hero part) and wordmark marks  */
/* ------------------------------------------------------------------ */
export function ctaCoords(part) {
  $$('.coord[data-coord]').forEach((el) => {
    const q = part.points[+el.dataset.coord % part.points.length];
    el.textContent = `[${fmt(q[0], 1)}, ${fmt(q[1], 1)}, ${fmt(q[2], 1)}]`;
  });
}
export function wordmarkMarks() {
  const g = $('#wm-ticks');
  let s = '';
  for (let x = 20; x <= 1580; x += 26) s += `<line x1="${x}" x2="${x}" y1="250" y2="${(x - 20) % 130 === 0 ? 266 : 258}"/>`;
  for (let i = 0; i < 9; i++) { const x = 20 + 1560 * (i + 0.5) / 9; s += `<line class="cm" x1="${x - 7}" x2="${x + 7}" y1="156" y2="156"/><line class="cm" x1="${x}" x2="${x}" y1="149" y2="163"/>`; }
  g.innerHTML = s;
}
export function wordmarkMotion() {
  const { gsap, ScrollTrigger } = window;
  const t = $('.wm-text');
  if (t.getBoundingClientRect().top < innerHeight) return;
  gsap.set(t, { strokeDashoffset: 3200 });
  gsap.set('#wm-ticks line, .wm-cons line', { opacity: 0 });
  ScrollTrigger.create({ trigger: '.wordmark', start: 'top 92%', once: true, onEnter: () => {
    gsap.to(t, { strokeDashoffset: 0, duration: 2.6, ease: 'power2.inOut' });
    gsap.to('.wm-cons line', { opacity: 1, duration: 0.6, stagger: 0.1 });
    gsap.to('#wm-ticks line', { opacity: 1, duration: 0.3, stagger: { amount: 1.2 } });
  } });
}
