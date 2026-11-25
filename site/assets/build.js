// Chapter 01: the drawing builds itself in steps as you scroll.
// points -> centreline -> tube outline -> dimension chains and angles -> DFM markers -> LRA side panel.
// Geometry, lengths, angles and findings all come from the part and its DFM report in data.json.
import { L, fmt, esc } from './charts.js';
import { findingsByBend, statusChip } from './sheet.js';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const c01 = (x) => Math.max(0, Math.min(1, x));
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a, b, k = 1) => [a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k];
const nrm = (a) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
const AX = ['X', 'Y', 'Z'];

export const STEPS = [
  ['Points', '交点', (p) => [`${p.points.length} XYZ intersection points, where the straight centrelines would meet if every bend were sharp.`, `XYZ交点 ${p.points.length} 点。曲げが鋭角だった場合に直線部の中心線が交わる点です。`]],
  ['Centreline', '中心線', (p) => [`Arcs at the CLR replace the sharp corners. The developed length becomes the cut length.`, `鋭角の角を曲げR（CLR）の円弧に置き換えます。展開長が切断長になります。`]],
  ['Tube', '管外形', (p) => [`The outer diameter gives the outline: Ø${fmt(p.od, 2)} × t${fmt(p.wall, 2)} mm, ${esc(p.material)}.`, `外径から外形線を描きます：Ø${fmt(p.od, 2)} × t${fmt(p.wall, 2)} mm、${esc(p.material)}。`]],
  ['Dimensions', '寸法', (p) => [`Straight lengths L and bend angles A: the numbers a bender runs.`, `直線長Lと曲げ角度A。ベンダーが実行する数値です。`]],
  ['DFM', 'DFM', (p, rep) => rep && rep.counts
    ? [`${rep.counts.pass} checks pass, ${rep.counts.warn} warn, ${rep.counts.fail} fail. Open a numbered marker for the rule.`, `合格 ${rep.counts.pass}、注意 ${rep.counts.warn}、不可 ${rep.counts.fail}。番号マーカーを開くとルールを表示します。`]
    : ['DFM report pending: regenerate with make artifacts.', 'DFMレポートは未生成（make artifacts で再生成）。']],
  ['Program', '曲げデータ', (p) => [`The LRA program and the cut length, ready for the machine.`, `LRA曲げデータと切断長。機械に渡せる形です。`]],
];

/**
 * Lay the view out in CSS pixels for the stage it is drawn in, so labels stay 11 px on any screen.
 * The two axes with the largest spread form the view; on a portrait stage the long axis runs vertically.
 */
function layout(part, hw, hh) {
  const P = part.points, C = part.centerline, r = part.od / 2;
  const ext = [0, 1, 2].map((i) => Math.max(...C.map((q) => q[i])) - Math.min(...C.map((q) => q[i])));
  const order = [0, 1, 2].sort((a, b) => ext[b] - ext[a]);
  const i = order[0], j = order[1];
  const W = Math.max(280, Math.round(hw)), H = Math.max(260, Math.round(hh));
  const portrait = H > W * 1.15;
  const pad = Math.max(46, Math.min(92, Math.min(W, H) * 0.13));
  const ci = (Math.max(...C.map((q) => q[i])) + Math.min(...C.map((q) => q[i]))) / 2;
  const cj = (Math.max(...C.map((q) => q[j])) + Math.min(...C.map((q) => q[j]))) / 2;
  let s, X, Y;
  if (!portrait) {
    s = Math.min((W - 2 * pad) / (ext[i] + 2 * r), (H - 2 * pad) / (ext[j] + 2 * r));
    X = (q) => W / 2 + (q[i] - ci) * s; Y = (q) => H / 2 - (q[j] - cj) * s;
  } else {
    s = Math.min((H - 2 * pad) / (ext[i] + 2 * r), (W - 2 * pad) / (ext[j] + 2 * r));
    X = (q) => W / 2 + (q[j] - cj) * s; Y = (q) => H / 2 - (q[i] - ci) * s;
  }
  return { W, H, s, i: portrait ? j : i, j: portrait ? i : j, X, Y, P };
}

/** tangent points along each straight: [start, end] in 3D, from the bend angles and CLRs */
function straights(part) {
  const P = part.points, n = P.length, out = [];
  const t = P.map((_, k) => (k === 0 || k === n - 1) ? 0 : part.lra[k - 1].CLR * Math.tan(part.bends[k - 1].angle * Math.PI / 360));
  for (let k = 0; k < n - 1; k++) {
    const u = nrm(sub(P[k + 1], P[k]));
    out.push([add(P[k], u, t[k]), add(P[k + 1], u, -t[k + 1])]);
  }
  return out;
}

export function createBuild() {
  const host = $('#build-dwg');
  const fit = document.createElement('div');
  fit.className = 'build-fit';
  fit.append($('#build-svg'), $('#build-markers'), $('#build-callout'));
  host.appendChild(fit);
  const panel = $('#build-panel'), card = $('#step-card');
  let G = null, part = null, rep = null, groups = {}, markers = [], p = 1, lastStep = -1, staticMode = false;

  function fitSize() {
    if (!G) return;
    const w = host.clientWidth - 16, h = host.clientHeight - 16;
    if (w <= 0 || h <= 0) return;
    const fw = Math.min(w, h * G.W / G.H);
    fit.style.width = `${fw}px`; fit.style.height = `${fw * G.H / G.W}px`;
  }
  let lastSize = '';
  new ResizeObserver(() => {
    if (!part) return;
    const key = `${Math.round(host.clientWidth / 24)}x${Math.round(host.clientHeight / 24)}`;
    if (key !== lastSize) { lastSize = key; render(part, rep); } else fitSize();
  }).observe(host);

  function render(pt, report) {
    part = pt; rep = report;
    G = layout(pt, (host.clientWidth || 900) - 16, (host.clientHeight || 500) - 16);
    lastSize = `${Math.round(host.clientWidth / 24)}x${Math.round(host.clientHeight / 24)}`;
    const { W, H, X, Y, s } = G;
    const pts = pt.points, cl = pt.centerline;
    const path = (arr) => arr.map((q, k) => `${k ? 'L' : 'M'}${X(q).toFixed(1)},${Y(q).toFixed(1)}`).join('');
    const sw = Math.max(3, pt.od * s);
    // centroid in screen space, to push dimensions outward
    const cx = pts.reduce((a, q) => a + X(q), 0) / pts.length, cy = pts.reduce((a, q) => a + Y(q), 0) / pts.length;
    let dims = '';
    straights(pt).forEach(([a, b], k) => {
      const ax = X(a), ay = Y(a), bx = X(b), by = Y(b), len = Math.hypot(bx - ax, by - ay);
      if (len < 34) return;
      const dx = (bx - ax) / len, dy = (by - ay) / len;
      let nx = -dy, ny = dx;
      if (nx * ((ax + bx) / 2 - cx) + ny * ((ay + by) / 2 - cy) < 0) { nx = -nx; ny = -ny; }
      const off = sw / 2 + 22, o1 = sw / 2 + 4, o2 = off + 6;
      const A = [ax + nx * off, ay + ny * off], B = [bx + nx * off, by + ny * off];
      const tick = (q) => `M${(q[0] - (dx + nx) * 4).toFixed(1)},${(q[1] - (dy + ny) * 4).toFixed(1)}L${(q[0] + (dx + nx) * 4).toFixed(1)},${(q[1] + (dy + ny) * 4).toFixed(1)}`;
      let ang = Math.atan2(dy, dx) * 180 / Math.PI; if (ang > 90) ang -= 180; if (ang < -90) ang += 180;
      const tx = (A[0] + B[0]) / 2 + nx * 10, ty = (A[1] + B[1]) / 2 + ny * 10;
      const label = k < pt.lra.length ? `L${k + 1} ${fmt(pt.lra[k].L, 2)}` : `L END ${fmt(pt.final_L, 2)}`;
      dims += `<g class="bd-dimg"><path class="bd-dim" d="M${(ax + nx * o1).toFixed(1)},${(ay + ny * o1).toFixed(1)}L${(ax + nx * o2).toFixed(1)},${(ay + ny * o2).toFixed(1)}M${(bx + nx * o1).toFixed(1)},${(by + ny * o1).toFixed(1)}L${(bx + nx * o2).toFixed(1)},${(by + ny * o2).toFixed(1)}M${A[0].toFixed(1)},${A[1].toFixed(1)}L${B[0].toFixed(1)},${B[1].toFixed(1)}${tick(A)}${tick(B)}"/>
        <text class="bd-dimt" x="${tx.toFixed(1)}" y="${ty.toFixed(1)}" text-anchor="middle" dominant-baseline="middle" transform="rotate(${ang.toFixed(1)} ${tx.toFixed(1)} ${ty.toFixed(1)})">${label}</text></g>`;
    });
    // bend angle labels on the outside of each bend; markers on the inside
    const mk = [];
    let angs = '';
    pt.bends.forEach((b, k) => {
      const P0 = pts[k], P1 = pts[k + 1], P2 = pts[k + 2];
      const u1 = [X(P1) - X(P0), Y(P1) - Y(P0)], u2 = [X(P2) - X(P1), Y(P2) - Y(P1)];
      const l1 = Math.hypot(...u1) || 1, l2 = Math.hypot(...u2) || 1;
      let ix = u2[0] / l2 - u1[0] / l1, iy = u2[1] / l2 - u1[1] / l1;
      const il = Math.hypot(ix, iy);
      if (il < 1e-3) { ix = -u1[1] / l1; iy = u1[0] / l1; } else { ix /= il; iy /= il; }
      const bx = X(P1), by = Y(P1);
      angs += `<text class="bd-ang" x="${(bx - ix * 26).toFixed(1)}" y="${(by - iy * 26).toFixed(1)}" text-anchor="middle" dominant-baseline="middle">A${k + 1} ${fmt(b.angle, 1)}°</text>`;
      mk.push({ k, x: bx + ix * (sw / 2 + 22), y: by + iy * (sw / 2 + 22) });
    });
    const view = `VIEW ${AX[G.i]}–${AX[G.j]} · MM · ${esc(pt.part_no)}`;
    $('#build-svg').innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Drawing of ${esc(pt.part_no)} built in steps: points, centreline, tube outline, dimensions and DFM markers">
      <text class="bd-view" x="14" y="22">${view}</text>
      <g class="bd-g" data-g="pts"><path class="bd-sharp" d="${path(pts)}"/>${pts.map((q, k) => `<g class="bd-p"><circle class="bd-pt" cx="${X(q).toFixed(1)}" cy="${Y(q).toFixed(1)}" r="4.5"/><text class="bd-ptl" x="${(X(q) + 8).toFixed(1)}" y="${(Y(q) - 8).toFixed(1)}">P${k}</text></g>`).join('')}</g>
      <g class="bd-g" data-g="tube"><path class="bd-tube-o" d="${path(cl)}" stroke-width="${sw.toFixed(1)}"/><path class="bd-tube-i" d="${path(cl)}" stroke-width="${Math.max(1, sw - 2.4).toFixed(1)}"/></g>
      <g class="bd-g" data-g="cl"><path class="bd-cl" pathLength="1" d="${path(cl)}"/></g>
      <g class="bd-g" data-g="cld"><path class="bd-cl-dash" d="${path(cl)}"/></g>
      <g class="bd-g" data-g="dims">${dims}${angs}</g>
    </svg>`;
    groups = Object.fromEntries($$('#build-svg [data-g]').map((g) => [g.dataset.g, g]));
    groups.pts.querySelectorAll('.bd-p').forEach((g) => g.classList.add('bd-g'));

    // markers: keyboard-reachable buttons that open a callout
    const { per } = findingsByBend(pt, rep);
    const callout = $('#build-callout');
    callout.hidden = true;
    $('#build-markers').innerHTML = mk.map(({ k, x, y }) => {
      const f = per[k];
      const lbl = `Bend ${k + 1}${f.length ? `, ${f.length} DFM finding${f.length > 1 ? 's' : ''}` : ', no DFM finding'}`;
      return `<button type="button" class="mk${f.length ? ' hit' : ''}" data-k="${k}" style="left:${(x / W * 100).toFixed(2)}%;top:${(y / H * 100).toFixed(2)}%" aria-expanded="false" aria-controls="build-callout" aria-label="${lbl}">${k + 1}</button>`;
    }).join('');
    markers = $$('#build-markers .mk');
    const close = (focus) => {
      callout.hidden = true;
      markers.forEach((m) => { if (m.getAttribute('aria-expanded') === 'true') { m.setAttribute('aria-expanded', 'false'); if (focus) m.focus(); } });
    };
    markers.forEach((m) => {
      m.addEventListener('click', () => {
        const open = m.getAttribute('aria-expanded') === 'true';
        close(false);
        if (open) return;
        const k = +m.dataset.k, row = pt.lra[k], f = per[k];
        callout.innerHTML = `<div class="bc-head"><span>${L(`Bend ${String(k + 1).padStart(2, '0')} · DFM`, `曲げ ${String(k + 1).padStart(2, '0')} · DFM`)}</span><button type="button" class="bc-x" aria-label="Close">×</button></div>
          <dl><dt>A</dt><dd>${fmt(row.A, 2)}°</dd><dt>R</dt><dd>${fmt(row.R, 2)}°</dd><dt>L</dt><dd>${fmt(row.L, 2)} mm</dd>
          <dt>CLR</dt><dd>${fmt(row.CLR, 1)} mm</dd><dt>${L('D of bend', '曲げ半径比')}</dt><dd>${fmt(row.CLR / pt.od, 2)} D</dd></dl>
          ${f.length ? f.map((x) => `<div class="bc-f"><span>${statusChip(x.status)}<b>${esc(x.rule)}</b> ${esc(x.title)}</span><span>${esc(x.detail)}</span></div>`).join('')
            : `<div class="bc-f">${L(`No rule flagged at this bend${rep && rep.counts ? `; ${rep.counts.pass} checks pass for the part` : ''}.`, `この曲げに指摘なし${rep && rep.counts ? `（部品全体で合格 ${rep.counts.pass}）` : ''}。`)}</div>`}`;
        const mx = parseFloat(m.style.left) / 100 * fit.clientWidth, my = parseFloat(m.style.top) / 100 * fit.clientHeight;
        callout.hidden = false;
        const cw = callout.offsetWidth, ch = callout.offsetHeight;
        let lx = mx + 24, ly = my - ch / 2;
        if (lx + cw > fit.clientWidth) lx = mx - 24 - cw;
        ly = Math.max(-fit.offsetTop + 8, Math.min(fit.clientHeight - ch, ly));
        callout.style.left = `${Math.max(0, lx)}px`; callout.style.top = `${ly}px`;
        m.setAttribute('aria-expanded', 'true');
        callout.querySelector('.bc-x').addEventListener('click', () => close(true));
      });
    });
    callout.onkeydown = (e) => { if (e.key === 'Escape') close(true); };
    $('#build-markers').onkeydown = (e) => { if (e.key === 'Escape') close(true); };

    // side panel: LRA program, cut length, DFM summary, XYZ table
    panel.innerHTML = `<div class="bp-head"><span>${L('LRA program', 'LRA曲げデータ')}</span><span>${esc(pt.part_no)}</span></div>
      <div class="bp-sec"><div class="table-wrap"><table class="data"><thead><tr><th>${L('Bend', '曲げ')}</th><th>L <span class="unit">mm</span></th><th>R <span class="unit">°</span></th><th>A <span class="unit">°</span></th><th>CLR <span class="unit">mm</span></th></tr></thead><tbody>
      ${pt.lra.map((r, k) => `<tr><td>B${k + 1}</td><td>${fmt(r.L, 2)}</td><td>${fmt(r.R, 2)}</td><td>${fmt(r.A, 2)}</td><td>${fmt(r.CLR, 1)}</td></tr>`).join('')}
      </tbody><tfoot><tr><td>${L('Final L', '最終直線')}</td><td>${fmt(pt.final_L, 2)}</td><td></td><td></td><td></td></tr></tfoot></table></div></div>
      <div class="bp-sec"><span class="bp-k">${L('Cut length · developed centreline', '切断長 · 中心線展開長')}</span><div class="cut"><span class="v" data-count="${pt.cut_length}" data-dp="2">${fmt(pt.cut_length, 2)}</span><span class="unit">mm</span></div></div>
      <div class="bp-sec"><span class="bp-k">DFM</span>${rep && rep.counts
        ? `<div>${statusChip('pass')} ${fmt(rep.counts.pass)} · ${statusChip('warn')} ${fmt(rep.counts.warn)} · ${statusChip('fail')} ${fmt(rep.counts.fail)}</div>
           <div class="cap" style="margin:0">${L('Tooling', 'ツーリング')}: ${esc(rep.tooling || '—')}<br>${L('Sequence', '曲げ順')}: ${esc(rep.sequence || '—')}</div>`
        : `<div class="cap" style="margin:0">${L('Pending: regenerate with make artifacts.', '未生成（make artifacts で再生成）。')}</div>`}</div>
      <div class="bp-sec"><details><summary>${L('XYZ intersection points (mm)', 'XYZ交点座標（mm）')}</summary><div class="table-wrap"><table class="data"><thead><tr><th>${L('Point', '点')}</th><th>X</th><th>Y</th><th>Z</th></tr></thead><tbody>
      ${pt.points.map((q, k) => `<tr><td>P${k}</td><td>${fmt(q[0], 2)}</td><td>${fmt(q[1], 2)}</td><td>${fmt(q[2], 2)}</td></tr>`).join('')}</tbody></table></div></details></div>`;
    panel.setAttribute('data-lenis-prevent', '');
    fitSize();
    lastStep = -1;
    if (staticMode) showAll(); else setProgress(p);
  }

  function stepText(k) {
    const [en, ja, f] = STEPS[k];
    const [ten, tja] = f(part, rep);
    $('#sc-num').textContent = `STEP ${String(k + 1).padStart(2, '0')} / ${String(STEPS.length).padStart(2, '0')}`;
    $('#sc-name').innerHTML = L(en, ja);
    $('#sc-text').innerHTML = L(ten, tja);
  }

  function setProgress(v) {
    p = c01(v);
    if (!G) return;
    const n = STEPS.length, q = p * n, step = Math.min(n - 1, Math.floor(q));
    const ptsG = $$('.bd-p', groups.pts);
    const k0 = c01(q) * ptsG.length;
    ptsG.forEach((g, k) => { g.style.opacity = k < k0 ? '1' : '0'; });
    groups.pts.querySelector('.bd-sharp').style.opacity = String(c01(q * 1.2 - 0.2));
    const clp = groups.cl.querySelector('path');
    clp.style.strokeDasharray = '1'; clp.style.strokeDashoffset = String(1 - c01(q - 1));
    groups.cl.style.opacity = q < 2.6 ? '1' : String(c01(1 - (q - 2.6) / 0.3));
    groups.cld.style.opacity = String(c01((q - 2.6) / 0.3));
    groups.tube.style.opacity = String(c01((q - 2) / 0.7));
    const dg = $$('.bd-dimg', groups.dims), at = $$('.bd-ang', groups.dims);
    groups.dims.style.opacity = '1';
    dg.forEach((g, k) => { g.style.opacity = String(c01((q - 3) * (dg.length + 1) - k)); });
    at.forEach((t, k) => { t.style.opacity = String(c01((q - 3.3) * (at.length + 1) - k)); });
    markers.forEach((m, k) => {
      const v2 = c01((q - 4) * (markers.length + 1) - k);
      m.style.opacity = String(v2); m.style.setProperty('--s', (0.4 + 0.6 * v2).toFixed(3));
      m.style.visibility = v2 > 0.05 ? 'visible' : 'hidden';
    });
    if (q < 4 && !$('#build-callout').hidden) { $('#build-callout').hidden = true; markers.forEach((m) => m.setAttribute('aria-expanded', 'false')); }
    // the panel slides in for the last step, and the drawing makes room for it
    const pin = c01((q - 5) / 0.45);
    const narrow = innerWidth <= 900;
    panel.style.transform = narrow ? `translateY(${(1 - pin) * 105}%)` : `translateX(${(1 - pin) * 105}%)`;
    panel.style.visibility = pin > 0.01 ? 'visible' : 'hidden';
    if (!narrow) {
      const pw = panel.offsetWidth, sw2 = host.clientWidth || 1, k2 = (sw2 - pw) / sw2;
      host.style.transform = `translateX(${(-pw / 2 * pin).toFixed(1)}px) scale(${(1 - (1 - k2) * pin).toFixed(3)})`;
    } else host.style.transform = `translateY(${(-18 * pin).toFixed(1)}%) scale(${(1 - 0.35 * pin).toFixed(3)})`;
    card.style.opacity = narrow && pin > 0.3 ? '0' : '1';
    $('#sc-bar').style.transform = `scaleX(${p.toFixed(4)})`;
    if (step !== lastStep) { lastStep = step; stepText(step); }
  }

  function showAll() {
    staticMode = true;
    if (!G) return;
    $$('#build-svg .bd-g, #build-svg .bd-p, #build-svg .bd-dimg, #build-svg .bd-ang, #build-svg .bd-sharp').forEach((g) => { g.style.opacity = ''; });
    groups.cl.style.opacity = '0';
    groups.cld.style.opacity = '1';
    const clp = groups.cl.querySelector('path'); clp.style.strokeDasharray = ''; clp.style.strokeDashoffset = '';
    markers.forEach((m) => { m.style.opacity = ''; m.style.removeProperty('--s'); m.style.visibility = ''; });
    panel.style.transform = ''; panel.style.visibility = ''; host.style.transform = '';
    card.style.opacity = '';
  }

  return {
    render,
    setProgress(v) { staticMode = false; setProgress(v); },
    showAll,
    progress: () => p,
  };
}
