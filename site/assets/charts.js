// SVG builders for every figure on the page. Pure functions of data.json values:
// nothing here knows a result in advance. Text uses the page's language spans.

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const L = (en, ja) => `<span class="l" lang="en">${en}</span><span class="l" lang="ja">${ja ?? en}</span>`;
/** bilingual SVG text: two <text> nodes, one hidden by CSS */
export const T = (en, ja, attrs = '', cls = 'lab') =>
  `<text class="l ${cls}" lang="en" ${attrs}>${en}</text><text class="l ${cls}" lang="ja" ${attrs}>${ja ?? en}</text>`;
export const fmt = (v, dp = 0) => (v == null || !Number.isFinite(+v)) ? '—'
  : Number(v).toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp });
const tip = (en, ja) => `data-tip="${esc(en)}"${ja ? ` data-tip-ja="${esc(ja)}"` : ''}`;

export function pending(cmd, extra = '') {
  return `<div class="pending" role="status"><strong>${L('Result pending', '結果は未生成')}</strong>
    <span>${L(`Regenerate with <code>${esc(cmd)}</code>, then <code>python scripts/build_site_data.py</code>.`, `<code>${esc(cmd)}</code> を実行後、<code>python scripts/build_site_data.py</code> で再生成してください。`)}</span>${extra}</div>`;
}

/** nice ticks */
export function ticks(lo, hi, n = 5) {
  const span = hi - lo || 1;
  const step0 = span / n, mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= n) || mag * 10;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) out.push(+v.toFixed(10));
  return { values: out, step };
}
const dpOf = (step) => { const s = String(+(+step).toFixed(8)); return s.includes('.') ? s.split('.')[1].length : 0; };

/* ------------------------------------------------------------------ */
/* Station state machine (shared with fixture3d.js)                     */
/* ------------------------------------------------------------------ */
export const STATES = ['IDLE', 'PART_PRESENT', 'CLAMPING', 'CHECK', 'PASS', 'UNCLAMP'];
export function stateAt(p) {
  if (p < 0.5) return 'IDLE';
  if (p < 0.64) return 'PART_PRESENT';
  if (p < 0.72) return 'CLAMPING';
  if (p < 0.82) return 'CHECK';
  if (p < 0.9) return 'PASS';
  return 'UNCLAMP';
}
export const STATE_P = { IDLE: 0.4, PART_PRESENT: 0.6, CLAMPING: 0.7, CHECK: 0.8, PASS: 0.86, UNCLAMP: 0.96 };
const GLOSS = {
  IDLE: ['idle', '待機'], PART_PRESENT: ['part seated', 'ワーク有'], CLAMPING: ['clamping', 'クランプ'],
  CHECK: ['sensor check', '検査'], PASS: ['good part', '合格'], FAIL: ['reject', '不合格'],
  UNCLAMP: ['release', 'クランプ解除'], ESTOP: ['emergency stop', '非常停止'],
};

export function stateFlow(container) {
  const narrow = container.clientWidth < 620;
  const nw = narrow ? 104 : 118, nh = 40;
  const pos = narrow ? {
    IDLE: [60, 30], PART_PRESENT: [180, 30], CLAMPING: [300, 30],
    UNCLAMP: [60, 110], PASS: [180, 110], CHECK: [300, 110],
    FAIL: [180, 190], ESTOP: [60, 190],
  } : {
    IDLE: [70, 50], PART_PRESENT: [225, 50], CLAMPING: [380, 50], CHECK: [535, 50], PASS: [690, 50], UNCLAMP: [845, 50],
    FAIL: [690, 120], ESTOP: [70, 120],
  };
  const W = narrow ? 360 : 920, H = narrow ? 220 : 150;
  const clip = (a, b) => {
    const [ax, ay] = pos[a], [bx, by] = pos[b], dx = bx - ax, dy = by - ay;
    const t = (hw, hh) => Math.min(dx ? hw / Math.abs(dx) : Infinity, dy ? hh / Math.abs(dy) : Infinity);
    const ta = t(nw / 2 + 2, nh / 2 + 2), tb = t(nw / 2 + 6, nh / 2 + 6);
    return [ax + dx * ta, ay + dy * ta, bx - dx * tb, by - dy * tb];
  };
  const edges = [['IDLE', 'PART_PRESENT'], ['PART_PRESENT', 'CLAMPING'], ['CLAMPING', 'CHECK'], ['CHECK', 'PASS'],
    ['PASS', 'UNCLAMP'], ['CHECK', 'FAIL'], ['FAIL', 'UNCLAMP']];
  let svg = `<svg class="sf" viewBox="0 0 ${W} ${H}" aria-hidden="true"><defs><marker id="sf-arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8 z" class="arrow"/></marker></defs>`;
  for (const [a, b] of edges) {
    const [x1, y1, x2, y2] = clip(a, b);
    svg += `<line class="edge" data-edge="${a}>${b}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" marker-end="url(#sf-arr)"/>`;
  }
  // return UNCLAMP -> IDLE
  const [ux, uy] = pos.UNCLAMP, [ix, iy] = pos.IDLE;
  const ret = narrow ? `M${ux},${uy - nh / 2 - 2} L${ix},${iy + nh / 2 + 6}`
    : `M${ux},${uy - nh / 2 - 2} L${ux},${12} L${ix},${12} L${ix},${iy - nh / 2 - 6}`;
  svg += `<path class="edge" data-edge="UNCLAMP>IDLE" d="${ret}" marker-end="url(#sf-arr)"/>`;
  // ESTOP: entered from any state, reset to IDLE
  const [ex, ey] = pos.ESTOP;
  svg += `<line class="edge dash" x1="${ex + nw / 2 + 4}" y1="${ey}" x2="${ex + nw / 2 + (narrow ? 26 : 60)}" y2="${ey}" marker-start="url(#sf-arr)"/>`;
  svg += T('from any state', '全状態から', `x="${ex + nw / 2 + (narrow ? 30 : 66)}" y="${ey + 4}"`, 'lab-mute');
  for (const [k, [x, y]] of Object.entries(pos)) {
    const cls = k === 'PASS' ? 'pass' : k === 'FAIL' ? 'fail' : k === 'ESTOP' ? 'estop' : '';
    const [en, ja] = GLOSS[k];
    svg += `<g class="node ${cls}" data-state="${k}"><rect x="${x - nw / 2}" y="${y - nh / 2}" width="${nw}" height="${nh}" rx="8"/>
      <text x="${x}" y="${y - 2}">${k}</text>${T(en, ja, `x="${x}" y="${y + 12}" style="font-size:10px"`, 'ja')}</g>`;
  }
  svg += `<circle class="token" r="5" cx="${pos.IDLE[0] - nw / 2}" cy="${pos.IDLE[1] - nh / 2}"/></svg>`;
  container.innerHTML = svg;
  const token = container.querySelector('.token');
  let cur = null;
  return {
    narrow,
    set(state, animate) {
      if (state === cur) return;
      const prev = cur; cur = state;
      container.querySelectorAll('.node').forEach((n) => n.classList.toggle('on', n.dataset.state === state));
      container.querySelectorAll('.edge').forEach((e) => e.classList.toggle('on', e.dataset.edge === `${prev}>${state}`));
      const [x, y] = pos[state] || pos.IDLE;
      const tx = x + nw / 2 - 4, ty = y - nh / 2 + 4;
      if (animate && window.gsap) window.gsap.to(token, { attr: { cx: tx, cy: ty }, duration: 0.45, ease: 'power2.inOut', overwrite: true });
      else { token.setAttribute('cx', tx); token.setAttribute('cy', ty); }
    },
  };
}

/* ------------------------------------------------------------------ */
/* CAD drawing: top and front views of the centreline, third angle      */
/* ------------------------------------------------------------------ */
export function drawing(part) {
  const W = 680, pad = 30, r = part.od / 2;
  const cl = part.centerline, P = part.points;
  const all = cl.concat(P);
  const ext = (i) => [Math.min(...all.map((p) => p[i])) - r, Math.max(...all.map((p) => p[i])) + r];
  const [x0, x1] = ext(0), [y0, y1] = ext(1), [z0, z1] = ext(2);
  const maxH = 150;
  const s = Math.min((W - 2 * pad - 30) / (x1 - x0), maxH / (y1 - y0), maxH / (z1 - z0));
  const ox = (W - (x1 - x0) * s) / 2 - x0 * s;
  const topY0 = 46, topH = (y1 - y0) * s;
  const frY0 = topY0 + topH + 58, frH = (z1 - z0) * s;
  const tbY = frY0 + frH + 34;
  const H = tbY + 58;
  const X = (x) => ox + x * s;
  const Yt = (y) => topY0 + (y1 - y) * s;      // top view: +Y up
  const Yf = (z) => frY0 + (z1 - z) * s;       // front view: +Z up
  const path = (pts, fy, i) => pts.map((p, k) => `${k ? 'L' : 'M'}${X(p[0]).toFixed(1)},${fy(p[i]).toFixed(1)}`).join('');
  const sw = Math.max(2, part.od * s);
  let g = `<svg class="dwg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Drawing of ${esc(part.part_no)}: top and front views of the centreline with ${P.length} XYZ intersection points">`;
  g += `<rect class="frame" x="0.5" y="0.5" width="${W - 1}" height="${H - 1}" rx="6"/>`;
  const view = (y0v, fy, i, en, ja) => {
    let v = T(en, ja, `x="${pad - 12}" y="${y0v - 16}"`, 'view-title');
    v += `<path class="tube draw" pathLength="1" d="${path(cl, fy, i)}" stroke-width="${sw.toFixed(1)}"/>`;
    v += `<path class="cl" d="${path(cl, fy, i)}"/>`;
    v += `<path class="sharp" d="${path(P, fy, i)}"/>`;
    return v;
  };
  g += view(topY0, Yt, 1, 'TOP VIEW · X–Y', '平面図 · X–Y');
  g += view(frY0, Yf, 2, 'FRONT VIEW · X–Z', '正面図 · X–Z');
  P.forEach((p, k) => {
    const cx = X(p[0]), cyT = Yt(p[1]), cyF = Yf(p[2]);
    g += `<g class="pt pop" ${tip(`P${k}: X ${fmt(p[0], 2)}, Y ${fmt(p[1], 2)}, Z ${fmt(p[2], 2)} mm`)}><circle cx="${cx}" cy="${cyT}" r="4"/><text x="${cx + 7}" y="${cyT - 7}">P${k}</text></g>`;
    g += `<g class="pt pop"><circle cx="${cx}" cy="${cyF}" r="3.2"/></g>`;
  });
  part.bends.forEach((b, k) => {
    const cx = X(b.point[0]), cy = Yf(b.point[2]);
    // alternate below / above the bend so neighbouring labels do not collide when bends line up in projection
    g += `<text class="bendlbl pop" x="${cx}" y="${k % 2 ? cy - 10 : cy + 18}" text-anchor="middle">B${k + 1} ${fmt(b.angle, 1)}°</text>`;
  });
  // third-angle projection symbol + title block
  const tx = W - pad - 250;
  g += `<g class="tb"><rect x="${tx}" y="${tbY}" width="250" height="44" rx="3"/>
    <text x="${tx + 10}" y="${tbY + 17}">${esc(part.part_no)} · ${esc(part.material)}</text>
    <text x="${tx + 10}" y="${tbY + 34}">Ø${fmt(part.od, 2)} × ${fmt(part.wall, 2)} · CLR ${part.clr.map((c) => fmt(c, 0)).filter((v, i, a) => a.indexOf(v) === i).join('/')} · mm</text></g>`;
  const sx = pad, sy = tbY + 22;
  g += `<g aria-hidden="true"><path class="proj" d="M${sx},${sy - 9} L${sx + 22},${sy - 5} L${sx + 22},${sy + 5} L${sx},${sy + 9} Z"/><circle class="proj" cx="${sx + 42}" cy="${sy}" r="9"/><circle class="proj" cx="${sx + 42}" cy="${sy}" r="4"/></g>`;
  g += T('Third-angle projection', '第三角法', `x="${sx + 60}" y="${sy + 4}"`, 'lab-mute');
  return g + '</svg>';
}

/* ------------------------------------------------------------------ */
/* Springback: physics estimate band vs measured mean ± sd              */
/* ------------------------------------------------------------------ */
export function gapChart(sb) {
  const ph = sb.physics, m = sb.target_mean, sd = sb.target_sd;
  const W = 520, H = 172, l = 12, r = 20;
  const hi = Math.max(ph.high, m + sd) * 1.12;
  const tk = ticks(0, hi, 5);
  const xmax = Math.max(hi, tk.values[tk.values.length - 1]);
  const X = (v) => l + (v / xmax) * (W - l - r);
  const dp = dpOf(tk.step);
  let g = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Physics springback estimate ${fmt(ph.low, 2)} to ${fmt(ph.high, 2)} degrees versus measured mean ${fmt(m, 2)} degrees">`;
  tk.values.forEach((v) => { g += `<line class="gridl" x1="${X(v)}" x2="${X(v)}" y1="18" y2="${H - 24}"/><text class="lab-mute" x="${X(v)}" y="${H - 8}" text-anchor="middle">${fmt(v, dp)}°</text>`; });
  // physics band
  const y1 = 44;
  g += T('Physics estimate (SUS304 assumed): low · mid · high', '理論推定（SUS304と仮定）：下限・中央・上限', `x="${l}" y="${y1 - 14}"`, 'lab');
  g += `<rect class="band grow-x" x="${X(ph.low)}" y="${y1 - 6}" width="${X(ph.high) - X(ph.low)}" height="12" rx="3" ${tip(`Physics: ${fmt(ph.low, 2)}° · ${fmt(ph.mid, 2)}° · ${fmt(ph.high, 2)}°`)}/>`;
  g += `<rect class="mark-steel" x="${X(ph.mid) - 1.5}" y="${y1 - 10}" width="3" height="20"/>`;
  g += `<text class="lab-m" x="${X(ph.high) + 8}" y="${y1 + 4}">${fmt(ph.mid, 2)}°</text>`;
  // measured
  const y2 = 124;
  g += T(`Measured, TubeBEND (n = ${fmt(sb.n_runs)}): mean ± 1 sd`, `実測 TubeBEND（n = ${fmt(sb.n_runs)}）：平均 ± 1標準偏差`, `x="${l}" y="${y2 - 16}"`, 'lab');
  g += `<line class="whisk" x1="${X(m - sd)}" x2="${X(m + sd)}" y1="${y2}" y2="${y2}"/><line class="whisk" x1="${X(m - sd)}" x2="${X(m - sd)}" y1="${y2 - 6}" y2="${y2 + 6}"/><line class="whisk" x1="${X(m + sd)}" x2="${X(m + sd)}" y1="${y2 - 6}" y2="${y2 + 6}"/>`;
  g += `<circle class="mark-acc pop" cx="${X(m)}" cy="${y2}" r="6" ${tip(`Measured mean ${fmt(m, 2)}° ± ${fmt(sd, 2)}°`)}/>`;
  const lx = X(m + sd) + 8, anchor = lx > W - 90 ? 'end' : 'start';
  g += `<text class="lab-m" x="${anchor === 'end' ? X(m - sd) - 8 : lx}" y="${y2 + 4}" text-anchor="${anchor}">${fmt(m, 2)}° ± ${fmt(sd, 2)}°</text>`;
  // the gap
  const gap = m - ph.mid;
  const yb = y1 + 32;
  g += `<path class="line-acc" d="M${X(ph.mid)},${y1 + 12} L${X(ph.mid)},${yb} L${X(m)},${yb} L${X(m)},${y2 - 10}" fill="none" stroke-dasharray="3 3"/>`;
  g += T(`gap ${fmt(gap, 2)}° · measured is ${fmt(m / ph.mid, 1)}× the estimate`, `差 ${fmt(gap, 2)}° · 実測は推定の${fmt(m / ph.mid, 1)}倍`, `x="${(X(ph.mid) + X(m)) / 2}" y="${yb - 6}" text-anchor="middle"`, 'lab-acc');
  return g + '</svg>';
}

/* ------------------------------------------------------------------ */
/* Parity scatter                                                        */
/* ------------------------------------------------------------------ */
export function parity(par, tol) {
  const W = 420, H = 380, l = 50, r = 14, t = 14, b = 46;
  const all = par.measured.concat(par.predicted).filter(Number.isFinite);
  const pad = (Math.max(...all) - Math.min(...all)) * 0.08 || 0.1;
  const lo = Math.min(...all) - pad - (tol ? 0 : 0), hi = Math.max(...all) + pad;
  const tk = ticks(lo, hi, 5), dp = dpOf(tk.step);
  const X = (v) => l + (v - lo) / (hi - lo) * (W - l - r);
  const Y = (v) => H - b - (v - lo) / (hi - lo) * (H - t - b);
  let g = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Parity plot of ${par.measured.length} out-of-fold springback predictions against measurements">`;
  g += `<defs><clipPath id="par-clip"><rect x="${l}" y="${t}" width="${W - l - r}" height="${H - t - b}"/></clipPath></defs>`;
  tk.values.forEach((v) => {
    g += `<line class="gridl" x1="${X(v)}" x2="${X(v)}" y1="${t}" y2="${H - b}"/><line class="gridl" x1="${l}" x2="${W - r}" y1="${Y(v)}" y2="${Y(v)}"/>`;
    g += `<text class="lab-mute" x="${X(v)}" y="${H - b + 16}" text-anchor="middle">${fmt(v, dp)}</text><text class="lab-mute" x="${l - 8}" y="${Y(v) + 4}" text-anchor="end">${fmt(v, dp)}</text>`;
  });
  if (tol) g += `<path class="tolband" clip-path="url(#par-clip)" d="M${X(lo)},${Y(lo + tol)} L${X(hi)},${Y(hi + tol)} L${X(hi)},${Y(hi - tol)} L${X(lo)},${Y(lo - tol)} Z"/>`;
  g += `<line class="diag" x1="${X(lo)}" y1="${Y(lo)}" x2="${X(hi)}" y2="${Y(hi)}"/>`;
  g += '<g class="dots">';
  par.measured.forEach((mv, i) => { const pv = par.predicted[i]; if (Number.isFinite(mv) && Number.isFinite(pv)) g += `<circle class="dot pop" cx="${X(mv).toFixed(1)}" cy="${Y(pv).toFixed(1)}" r="3.4"/>`; });
  g += '</g>';
  g += T('Measured springback (°)', '実測スプリングバック（°）', `x="${(l + W - r) / 2}" y="${H - 8}" text-anchor="middle"`, 'lab');
  g += T('Predicted (°)', '予測値（°）', `x="${14}" y="${(t + H - b) / 2}" text-anchor="middle" transform="rotate(-90 14 ${(t + H - b) / 2})"`, 'lab');
  g += `<rect class="hit" data-parity x="${l}" y="${t}" width="${W - l - r}" height="${H - t - b}"/>`;
  return { svg: g + '</svg>', X, Y, lo, hi, W, H };
}

/* ------------------------------------------------------------------ */
/* Horizontal bar list (FPY, SHAP)                                       */
/* ------------------------------------------------------------------ */
export function hbars(rows, { max, unit = '', dp = 1, aria = '', accentKeys = [] } = {}) {
  const W = 400, rowH = 44, l = 0, r = 62;
  const H = rows.length * rowH + 6;
  const mx = max ?? Math.max(...rows.map((d) => d.value), 1e-9);
  const X = (v) => (v / mx) * (W - l - r);
  let g = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(aria)}">`;
  rows.forEach((d, i) => {
    const y = i * rowH;
    const acc = accentKeys.includes(d.key);
    g += T(d.en, d.ja, `x="${l}" y="${y + 14}"`, 'lab');
    g += `<rect class="mark-soft" x="${l}" y="${y + 21}" width="${W - l - r}" height="12" rx="3" opacity=".35"/>`;
    g += `<rect class="${acc ? 'mark-acc' : 'mark'} grow-x" x="${l}" y="${y + 21}" width="${Math.max(d.value > 0 ? 2 : 0, X(d.value))}" height="12" rx="3" ${tip(d.tip || `${d.en}: ${fmt(d.value, dp)}${unit}`)}/>`;
    g += `<text class="lab-m" x="${W - r + 8}" y="${y + 32}">${fmt(d.value, dp)}${unit}</text>`;
    if (d.sub) g += `<text class="lab-mute" x="${W}" y="${y + 14}" text-anchor="end">${d.sub}</text>`;
  });
  return g + '</svg>';
}

/* ------------------------------------------------------------------ */
/* Yamazumi: stacked work elements per station against takt             */
/* ------------------------------------------------------------------ */
export function yamazumi(container, line, before, after, stationJa) {
  const W = 760, H = 360, l = 44, r = 74, t = 20, b = 54;
  const keys = line.stations.map((s) => s.key);
  const names = Object.fromEntries(line.stations.map((s) => [s.key, s]));
  const totals = (rows) => keys.map((k) => rows.filter((e) => e.station === k).reduce((a, e) => a + e.seconds, 0));
  const ymax0 = Math.max(line.takt_s, ...totals(before), ...totals(after)) * 1.12;
  const tk = ticks(0, ymax0, 5);
  const ymax = Math.max(ymax0, tk.values[tk.values.length - 1]);
  const band = (W - l - r) / keys.length, bw = Math.min(70, band * 0.56);
  const X = (i) => l + band * i + (band - bw) / 2;
  const Y = (v) => H - b - (v / ymax) * (H - t - b);
  const keyOf = (e) => (before.filter((x) => x.element === e.element).length <= 1 && after.filter((x) => x.element === e.element).length <= 1) ? e.element : `${e.station}|${e.element}`;
  const layout = (rows) => {
    const out = {}, acc = Object.fromEntries(keys.map((k) => [k, 0]));
    rows.forEach((e) => {
      const i = keys.indexOf(e.station); if (i < 0) return;
      const y0 = acc[e.station], y1 = y0 + e.seconds; acc[e.station] = y1;
      out[keyOf(e)] = { x: X(i), y: Y(y1), h: Math.max(0, Y(y0) - Y(y1) - 2), e };
    });
    return { segs: out, tot: keys.map((k) => acc[k]) };
  };
  const A = layout(before), B = layout(after);
  const allKeys = [...new Set([...Object.keys(A.segs), ...Object.keys(B.segs)])];
  let g = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Yamazumi chart: work content per station in seconds against a takt time of ${fmt(line.takt_s, 1)} s">`;
  tk.values.forEach((v) => { g += `<line class="gridl" x1="${l}" x2="${W - r}" y1="${Y(v)}" y2="${Y(v)}"/><text class="lab-mute" x="${l - 8}" y="${Y(v) + 4}" text-anchor="end">${fmt(v)}</text>`; });
  g += `<text class="lab-mute" x="${l - 8}" y="${t - 6}" text-anchor="end">s</text>`;
  g += '<g class="segs">';
  allKeys.forEach((k, i) => {
    const s = A.segs[k] || B.segs[k];
    g += `<rect class="seg-${s.e.kind} yseg" data-k="${i}" x="${s.x}" y="${s.y}" width="${bw}" height="${s.h}" rx="2"/>`;
  });
  g += '</g>';
  keys.forEach((k, i) => {
    g += `<text class="lab-m ytot" data-i="${i}" x="${X(i) + bw / 2}" y="${Y(A.tot[i]) - 8}" text-anchor="middle">${fmt(A.tot[i])} s</text>`;
    g += `<text class="lab-mute" x="${X(i) + bw / 2}" y="${H - b + 18}" text-anchor="middle">${esc(k)}</text>`;
    g += `<text class="lab" x="${X(i) + bw / 2}" y="${H - b + 36}" text-anchor="middle" style="font-family:var(--jp)">${esc(names[k].name_ja)}</text>`;
  });
  g += `<line class="line-takt" x1="${l}" x2="${W - r + 8}" y1="${Y(line.takt_s)}" y2="${Y(line.takt_s)}"/>`;
  g += T(`Takt ${fmt(line.takt_s, 1)} s`, `タクト ${fmt(line.takt_s, 1)} 秒`, `x="${W - r + 12}" y="${Y(line.takt_s) + 4}"`, 'lab-m');
  g += '</svg>';
  container.innerHTML = g;
  const rects = [...container.querySelectorAll('.yseg')];
  const tots = [...container.querySelectorAll('.ytot')];
  const set = (state, animate) => {
    const Lx = state === 'after' ? B : A;
    rects.forEach((el) => {
      const k = allKeys[+el.dataset.k], s = Lx.segs[k];
      const attrs = s ? { x: s.x, y: s.y, height: s.h } : { height: 0, y: Y(0) };
      const op = s ? 1 : 0;
      if (s) {
        const e = s.e;
        el.setAttribute('data-tip', `${e.station} · ${e.element} · ${fmt(e.seconds)} s · ${e.kind}`);
      }
      if (animate && window.gsap) window.gsap.to(el, { attr: attrs, opacity: op, duration: 0.7, ease: 'power3.inOut', overwrite: true });
      else { Object.entries(attrs).forEach(([a, v]) => el.setAttribute(a, v)); el.style.opacity = op; }
    });
    tots.forEach((el, i) => {
      const v = Lx.tot[i], over = v > line.takt_s;
      el.textContent = `${fmt(v)} s${over ? ' ▲' : ''}`;
      el.classList.toggle('lab-acc', over); el.classList.toggle('lab-m', !over);
      if (animate && window.gsap) window.gsap.to(el, { attr: { y: Y(v) - 8 }, duration: 0.7, ease: 'power3.inOut', overwrite: true });
      else el.setAttribute('y', Y(v) - 8);
    });
    return { totals: Lx.tot, max: Math.max(...Lx.tot), bottleneck: keys[Lx.tot.indexOf(Math.max(...Lx.tot))] };
  };
  return { set };
}

/* ------------------------------------------------------------------ */
/* Kaizen scenarios: good parts per day with 95 % CI vs demand           */
/* ------------------------------------------------------------------ */
export const SCEN_JA = {
  'Baseline': '現状', 'Line rebalancing': 'ライン編成の見直し', 'SMED on bender': 'ベンダーの段取り短縮（SMED）',
  'Buffer before bender': 'ベンダー前バッファ', 'Closed-loop springback': 'スプリングバックのクローズドループ補正',
};
export const splitScenario = (s) => { const m = /^(\d+)\s+(.*)$/.exec(s); return m ? { n: m[1], name: m[2] } : { n: '', name: s }; };

export function kaizenChart(rows, demand) {
  const W = 760, H = 380, l = 52, r = 16, t = 34, b = 78;
  const hi0 = Math.max(demand, ...rows.map((d) => d.per_day + (d.per_day_ci95 || 0))) * 1.1;
  const tk = ticks(0, hi0, 5);
  const hi = Math.max(hi0, tk.values[tk.values.length - 1]);
  const band = (W - l - r) / rows.length, bw = Math.min(84, band * 0.5);
  const X = (i) => l + band * i + (band - bw) / 2;
  const Y = (v) => H - b - (v / hi) * (H - t - b);
  let g = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Good parts per day for ${rows.length} simulated kaizen scenarios against a demand of ${fmt(demand)} per day">`;
  tk.values.forEach((v) => { g += `<line class="gridl" x1="${l}" x2="${W - r}" y1="${Y(v)}" y2="${Y(v)}"/><text class="lab-mute" x="${l - 8}" y="${Y(v) + 4}" text-anchor="end">${fmt(v)}</text>`; });
  rows.forEach((d, i) => {
    const last = i === rows.length - 1, x = X(i), cx = x + bw / 2;
    const { n, name } = splitScenario(d.scenario);
    g += `<rect class="${last ? 'mark-acc' : 'mark'} grow-y" x="${x}" y="${Y(d.per_day)}" width="${bw}" height="${Y(0) - Y(d.per_day)}" rx="3" ${tip(`${d.scenario}: ${fmt(d.per_day, 1)} ± ${fmt(d.per_day_ci95, 1)} /day (95 % CI) · ${fmt(d.demand_met_pct, 1)} % of demand · scrap ${fmt(d.scrap_pct, 1)} % · bottleneck ${d.bottleneck}`)}/>`;
    if (d.per_day_ci95) {
      const a = Y(d.per_day + d.per_day_ci95), c = Y(d.per_day - d.per_day_ci95);
      g += `<line class="whisk" x1="${cx}" x2="${cx}" y1="${a}" y2="${c}"/><line class="whisk" x1="${cx - 6}" x2="${cx + 6}" y1="${a}" y2="${a}"/><line class="whisk" x1="${cx - 6}" x2="${cx + 6}" y1="${c}" y2="${c}"/>`;
    }
    g += `<text class="lab-m" x="${cx}" y="${Y(d.per_day + (d.per_day_ci95 || 0)) - 18}" text-anchor="middle">${fmt(d.per_day)}</text>`;
    g += `<text class="lab-mute" x="${cx}" y="${Y(d.per_day + (d.per_day_ci95 || 0)) - 5}" text-anchor="middle">${fmt(d.demand_met_pct, 1)} %</text>`;
    g += `<text class="lab-acc" x="${cx}" y="${H - b + 18}" text-anchor="middle">${esc(n)}</text>`;
    const words = name.split(' '), mid = Math.ceil(words.length / 2);
    const l1 = words.slice(0, mid).join(' '), l2 = words.slice(mid).join(' ');
    g += `<text class="l lab" lang="en" x="${cx}" y="${H - b + 34}" text-anchor="middle">${esc(l1)}</text><text class="l lab" lang="en" x="${cx}" y="${H - b + 49}" text-anchor="middle">${esc(l2)}</text>`;
    const ja = SCEN_JA[name] || name;
    const j1 = ja.length > 9 ? ja.slice(0, Math.ceil(ja.length / 2)) : ja, j2 = ja.length > 9 ? ja.slice(Math.ceil(ja.length / 2)) : '';
    g += `<text class="l lab" lang="ja" x="${cx}" y="${H - b + 34}" text-anchor="middle">${esc(j1)}</text><text class="l lab" lang="ja" x="${cx}" y="${H - b + 49}" text-anchor="middle">${esc(j2)}</text>`;
    g += `<text class="lab-mute" x="${cx}" y="${H - b + 66}" text-anchor="middle">BN ${esc(d.bottleneck)}</text>`;
  });
  g += `<line class="line-demand" x1="${l}" x2="${W - r}" y1="${Y(demand)}" y2="${Y(demand)}"/>`;
  g += T(`Demand ${fmt(demand)} /day`, `需要 ${fmt(demand)} 本／日`, `x="${l + 4}" y="${Y(demand) - 7}"`, 'lab-acc');
  return g + '</svg>';
}

/* ------------------------------------------------------------------ */
/* SMED: changeover minutes, internal vs external, before and after     */
/* ------------------------------------------------------------------ */
export function smedChart(smed) {
  const W = 520, H = 170, l = 70, r = 16;
  const tb = smed.reduce((a, s) => a + s.minutes_before, 0), ta = smed.reduce((a, s) => a + s.minutes_after, 0);
  const tk = ticks(0, Math.max(tb, ta) * 1.05, 5);
  const mx = Math.max(tk.values[tk.values.length - 1], tb, ta);
  const X = (v) => l + (v / mx) * (W - l - r);
  let g = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Bender changeover in minutes before and after SMED, split into internal and external work"><defs><pattern id="hatch-ext" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="5" height="5" fill="var(--card)"/><rect width="2" height="5" class="seg-machine"/></pattern></defs>`;
  tk.values.forEach((v) => { g += `<line class="gridl" x1="${X(v)}" x2="${X(v)}" y1="10" y2="${H - 34}"/><text class="lab-mute" x="${X(v)}" y="${H - 18}" text-anchor="middle">${fmt(v)}</text>`; });
  g += T('min', '分', `x="${W - r}" y="${H - 4}" text-anchor="end"`, 'lab-mute');
  const bar = (y, key, en, ja) => {
    let acc = 0, s = T(en, ja, `x="${l - 10}" y="${y + 17}" text-anchor="end"`, 'lab');
    let inn = 0, ext = 0;
    smed.forEach((st) => {
      const m = st[`minutes_${key}`], internal = st[`internal_${key}`];
      if (!m) return;
      internal ? (inn += m) : (ext += m);
      s += `<rect class="grow-x" x="${X(acc) + 1}" y="${y}" width="${Math.max(0, X(acc + m) - X(acc) - 2)}" height="26" rx="2" fill="${internal ? 'var(--s-manual)' : 'url(#hatch-ext)'}" ${internal ? '' : 'stroke="var(--s-machine)"'} ${tip(`${st.step}: ${fmt(m, 1)} min, ${internal ? 'internal' : 'external'}`)}/>`;
      acc += m;
    });
    return { s, inn, ext };
  };
  const b1 = bar(16, 'before', 'Before', '改善前'), b2 = bar(70, 'after', 'After', '改善後');
  g += b1.s + b2.s;
  g += T(`internal ${fmt(b1.inn, 1)} · external ${fmt(b1.ext, 1)} min`, `内段取り ${fmt(b1.inn, 1)} · 外段取り ${fmt(b1.ext, 1)} 分`, `x="${l}" y="${16 + 40}"`, 'lab-mute');
  g += T(`internal ${fmt(b2.inn, 1)} · external ${fmt(b2.ext, 1)} min`, `内段取り ${fmt(b2.inn, 1)} · 外段取り ${fmt(b2.ext, 1)} 分`, `x="${l}" y="${70 + 40}"`, 'lab-mute');
  return g + '</svg>';
}

/* ------------------------------------------------------------------ */
/* Buffer curve: mean good parts/day ± sd vs buffer size                 */
/* ------------------------------------------------------------------ */
export function bufferChart(curve) {
  const W = 520, H = 260, l = 52, r = 14, t = 14, b = 40;
  const lo0 = Math.min(...curve.map((d) => d.per_day - d.sd)), hi0 = Math.max(...curve.map((d) => d.per_day + d.sd));
  const tk = ticks(lo0, hi0, 5);
  const lo = Math.min(lo0, tk.values[0]), hi = Math.max(hi0, tk.values[tk.values.length - 1]);
  const bx0 = Math.min(...curve.map((d) => d.buffer)), bx1 = Math.max(...curve.map((d) => d.buffer));
  const X = (v) => l + (v - bx0) / ((bx1 - bx0) || 1) * (W - l - r);
  const Y = (v) => H - b - (v - lo) / ((hi - lo) || 1) * (H - t - b);
  let g = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Good parts per day against buffer size before the bender, buffers ${bx0} to ${bx1}">`;
  tk.values.forEach((v) => { g += `<line class="gridl" x1="${l}" x2="${W - r}" y1="${Y(v)}" y2="${Y(v)}"/><text class="lab-mute" x="${l - 8}" y="${Y(v) + 4}" text-anchor="end">${fmt(v)}</text>`; });
  ticks(bx0, bx1, 6).values.forEach((v) => { g += `<text class="lab-mute" x="${X(v)}" y="${H - b + 16}" text-anchor="middle">${fmt(v)}</text>`; });
  const up = curve.map((d) => `${X(d.buffer)},${Y(d.per_day + d.sd)}`), dn = curve.slice().reverse().map((d) => `${X(d.buffer)},${Y(d.per_day - d.sd)}`);
  g += `<polygon class="band" points="${up.concat(dn).join(' ')}"/>`;
  g += `<polyline class="line-ink" points="${curve.map((d) => `${X(d.buffer)},${Y(d.per_day)}`).join(' ')}"/>`;
  curve.forEach((d) => { g += `<circle class="mark pop" cx="${X(d.buffer)}" cy="${Y(d.per_day)}" r="3"/><rect class="hit" x="${X(d.buffer) - 10}" y="${t}" width="20" height="${H - t - b}" ${tip(`buffer ${d.buffer}: ${fmt(d.per_day, 1)} ± ${fmt(d.sd, 1)} /day · WIP ${fmt(d.wip, 1)}`)}/>`; });
  g += T('Buffer size (parts) · y-axis does not start at zero', 'バッファ容量（個）· 縦軸はゼロ起点ではありません', `x="${(l + W - r) / 2}" y="${H - 6}" text-anchor="middle"`, 'lab-mute');
  return g + '</svg>';
}

/* ------------------------------------------------------------------ */
/* Station pictograms (line art, 120 x 80)                               */
/* ------------------------------------------------------------------ */
export function pictogram(key) {
  const k = String(key).toUpperCase();
  const wrap = (s) => `<svg viewBox="0 0 120 80" aria-hidden="true">${s}</svg>`;
  if (k.startsWith('CUT')) return wrap(`<rect class="fill" x="8" y="50" width="104" height="8" rx="2"/><circle class="ln" cx="60" cy="32" r="22"/><circle class="ln" cx="60" cy="32" r="4"/><path class="acc" d="M60 10 l4 -4 M82 32 l4 4 M60 54 l-4 4 M38 32 l-4 -4"/><path class="acc" d="M56 54 v8"/>`);
  if (k.startsWith('END')) return wrap(`<rect class="fill" x="10" y="34" width="60" height="12" rx="2"/><path class="ln" d="M70 34 l14 -8 v28 l-14 -8"/><path class="ln" d="M92 20 v40 M100 20 v40"/><path class="acc" d="M40 30 v-6 M40 50 v6"/>`);
  if (k.startsWith('BEND')) return wrap(`<circle class="ln" cx="66" cy="44" r="24"/><circle class="ln" cx="66" cy="44" r="5"/><path class="ln" d="M6 68 H66 A24 24 0 0 0 87 56 L104 26" stroke-width="7" opacity=".35"/><path class="acc" d="M6 68 H66 A24 24 0 0 0 87 56 L104 26"/>`);
  if (k.startsWith('WELD')) return wrap(`<rect class="fill" x="10" y="52" width="100" height="8" rx="2"/><rect class="ln" x="44" y="40" width="30" height="12" rx="2"/><path class="ln" d="M84 8 L70 36"/><path class="ln" d="M90 12 l-8 -4"/><path class="acc" d="M68 40 l-4 -6 M70 42 l6 -4 M66 42 l-8 -2"/>`);
  if (k.startsWith('INSP')) return wrap(`<rect class="fill" x="8" y="54" width="104" height="8" rx="2"/><path class="ln" d="M18 54 v-14 h10 v14 M54 54 v-14 h10 v14 M90 54 v-14 h10 v14"/><path class="ln" d="M14 44 H104" stroke-width="5" opacity=".35"/><path class="acc" d="M50 18 l8 8 l16 -16"/>`);
  if (k.startsWith('PACK')) return wrap(`<path class="ln" d="M28 30 L60 18 L92 30 L92 64 L60 74 L28 64 Z M28 30 L60 42 L92 30 M60 42 V74"/><path class="acc" d="M40 26 L72 14"/>`);
  return wrap('<rect class="ln" x="20" y="20" width="80" height="44" rx="6"/>');
}
