// PipeForge showcase: entry module. Loads data.json, renders every chapter from it,
// wires the EN/日本語 toggle, Lenis + GSAP ScrollTrigger (full motion) or static
// states with simple controls (reduced motion), and lazy-loads the three.js stages.
import * as C from './charts.js';

const { L, T, fmt, esc, pending } = C;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const html = document.documentElement;
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode */ } },
};
const { gsap, ScrollTrigger, SplitText, Lenis } = window;
const hasGSAP = !!(gsap && ScrollTrigger);
if (hasGSAP) gsap.registerPlugin(ScrollTrigger, ...(SplitText ? [SplitText] : []));
const osReduce = matchMedia('(prefers-reduced-motion: reduce)');

const S = {
  data: null, full: false, lenis: null, ctx: null, mm: null, split: null,
  hero: null, bend: null, fixture: null, flow: null, yama: null,
  p: { hero: 1, bend: 1, fixture: C.STATE_P.PASS },
  heroPart: null, bendPart: null, cadIndex: 0,
};

/* ------------------------------------------------------------------ */
/* language                                                             */
/* ------------------------------------------------------------------ */
function setLang(l) {
  html.dataset.lang = l;
  html.lang = l;
  $$('[data-set-lang]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.setLang === l)));
  store.set('pf-lang', l);
  if (S.data) syncChapterLabel();
  if (hasGSAP && S.full) ScrollTrigger.refresh();
}
$$('[data-set-lang]').forEach((b) => b.addEventListener('click', () => setLang(b.dataset.setLang)));
setLang(store.get('pf-lang') === 'ja' ? 'ja' : 'en');

/* ------------------------------------------------------------------ */
/* tooltip (pointer) for any element with data-tip                      */
/* ------------------------------------------------------------------ */
const tipEl = $('#tip');
function showTip(el, x, y) {
  const ja = html.dataset.lang === 'ja' && el.dataset.tipJa;
  tipEl.textContent = ja || el.dataset.tip;
  tipEl.hidden = false;
  const w = tipEl.offsetWidth, h = tipEl.offsetHeight;
  tipEl.style.left = Math.max(8, Math.min(innerWidth - w - 8, x + 14)) + 'px';
  tipEl.style.top = Math.max(8, y - h - 12) + 'px';
}
document.addEventListener('pointermove', (e) => {
  const el = e.target.closest && e.target.closest('[data-tip]');
  if (el) showTip(el, e.clientX, e.clientY); else tipEl.hidden = true;
}, { passive: true });
document.addEventListener('pointerleave', () => { tipEl.hidden = true; });
addEventListener('scroll', () => { tipEl.hidden = true; }, { passive: true });

/* ------------------------------------------------------------------ */
/* helpers                                                              */
/* ------------------------------------------------------------------ */
const dd = (k, v, cls = '') => `<div class="${cls}"><dt>${k}</dt><dd>${v}</dd></div>`;
const unitDeg = (v, dp = 2) => `${fmt(v, dp)}°`;
const mm = (v, dp = 2) => `${fmt(v, dp)} mm`;
const uniq = (a) => a.filter((v, i) => a.indexOf(v) === i);
function partName(p) { return L(esc(p.name), esc(p.name_ja)); }

/* ------------------------------------------------------------------ */
/* 00 hero (static parts: poster, spec, program table)                  */
/* ------------------------------------------------------------------ */
function renderHero(part) {
  $('#hero-partno').textContent = part.part_no;
  // poster: front view (X, Z) of the real centreline, visible until WebGL takes over
  const cl = part.centerline, r = part.od / 2;
  const xs = cl.map((q) => q[0]), zs = cl.map((q) => q[2]);
  const x0 = Math.min(...xs) - r, x1 = Math.max(...xs) + r, z0 = Math.min(...zs) - r, z1 = Math.max(...zs) + r;
  const poster = $('#hero-poster');
  poster.setAttribute('viewBox', `${x0} ${-z1} ${x1 - x0} ${z1 - z0}`);
  poster.innerHTML = `<path d="${cl.map((q, i) => `${i ? 'L' : 'M'}${q[0]},${-q[2]}`).join('')}" stroke-width="${part.od}"/>`;

  const clrs = uniq(part.clr.map((c) => fmt(c, 0))).join(' / ');
  const hd = (k, v, cls = '') => `<dt class="${cls}">${k}</dt><dd class="${cls}">${v}</dd>`;
  $('#hero-spec').innerHTML = [
    hd(L('Part', '品名'), partName(part)),
    hd(L('Material', '材質'), esc(part.material)),
    hd(L('OD × wall', '外径 × 肉厚'), `${fmt(part.od, 1)} × ${fmt(part.wall, 1)} mm`),
    hd(L('CLR', '曲げR'), `${clrs} mm`, 'xs-hide'),
    hd(L('Bends', '曲げ数'), fmt(part.lra.length), 'xs-hide'),
    hd(L('Cut length', '切断長'), mm(part.cut_length)),
  ].join('');

  const rows = part.lra.map((row, i) => `<tr data-bend="${i}"><td>B${i + 1}</td><td>${fmt(row.L, 2)}</td><td>${fmt(row.R, 1)}</td><td>${fmt(row.A, 2)}</td></tr>`).join('');
  $('#hero-program').innerHTML = `<table><thead><tr><th>#</th><th>L mm</th><th>R °</th><th>A °</th></tr></thead><tbody>${rows}<tr><td>END</td><td>${fmt(part.final_L, 2)}</td><td></td><td></td></tr></tbody></table>`;

  const dim = document.createElement('div');
  dim.className = 'dimtag';
  dim.innerHTML = L(`Cut length ${mm(part.cut_length)}`, `切断長 ${mm(part.cut_length)}`);
  $('#hero-dim').appendChild(dim);
  S.heroDimTag = dim;

  // reduced-motion control: 0 = straight blank, k = after bend k
  const range = $('#hero-range');
  range.max = String(part.lra.length);
  range.value = String(part.lra.length);
  const onRange = () => {
    const k = +range.value, nb = part.lra.length;
    const p = k === 0 ? 0.42 : k >= nb ? 1 : 0.46 + 0.5 * (k / nb) - 0.001;
    $('#hero-range-out').innerHTML = k === 0 ? L('Straight blank', '素材（直管）') : k >= nb ? L('Finished part', '完成品') : L(`After bend ${k} of ${nb}`, `曲げ ${k} / ${nb} 完了`);
    range.setAttribute('aria-valuetext', k === 0 ? 'Straight blank' : `After bend ${k} of ${nb}`);
    setHero(p);
  };
  range.addEventListener('input', onRange);
  S.onHeroRange = onRange;
  onHeroPhase({ phase: 'done', bend: -1, frac: 1, fractions: part.lra.map(() => 1), p: 1 });
}

function onHeroPhase(st) {
  const part = S.heroPart, nb = part.lra.length;
  let txt;
  if (st.phase === 'cad') txt = L('CAD · XYZ intersection points', 'CAD · XYZ交点');
  else if (st.phase === 'unbend') txt = L('Unbending to the blank', '素材へ展開中');
  else if (st.phase === 'blank') txt = L(`Blank · cut ${mm(part.cut_length)}`, `素材 · 切断長 ${mm(part.cut_length)}`);
  else if (st.phase === 'bend') {
    const A = part.lra[st.bend].A, a = A * st.frac;
    txt = st.frac > 0.995
      ? L(`Bend ${st.bend + 1} / ${nb} done · A ${fmt(A, 2)}°`, `曲げ ${st.bend + 1} / ${nb} 完了 · A ${fmt(A, 2)}°`)
      : L(`Bend ${st.bend + 1} / ${nb} · A ${fmt(a, 1)}° of ${fmt(A, 2)}°`, `曲げ ${st.bend + 1} / ${nb} · A ${fmt(a, 1)}° / ${fmt(A, 2)}°`);
  } else {
    const err = S.hero && S.hero.endError;
    txt = err != null ? L(`Finished · LRA rebuild ends ${fmt(err, 2)} mm from CAD`, `完成 · LRA再構成とCADの端点差 ${fmt(err, 2)} mm`) : L('Finished part', '完成品');
  }
  const stateEl = $('#hero-state');
  if (stateEl.dataset.key !== txt) { stateEl.innerHTML = txt; stateEl.dataset.key = txt; }
  const prog = $('#hero-program');
  prog.classList.toggle('show', st.phase === 'blank' || st.phase === 'bend' || st.phase === 'done');
  $$('tr[data-bend]', prog).forEach((tr, i) => {
    tr.classList.toggle('on', st.phase === 'bend' && i === st.bend);
    tr.classList.toggle('done', (st.fractions[i] ?? 0) > 0.999 && st.phase !== 'unbend');
  });
}

function setHero(p) {
  S.p.hero = p;
  if (S.hero) S.hero.setProgress(p);
}

/* ------------------------------------------------------------------ */
/* 01 CAD and drawing                                                   */
/* ------------------------------------------------------------------ */
function renderCadTabs(parts) {
  const tabs = $('#part-tabs');
  tabs.innerHTML = parts.map((p, i) => `<button type="button" role="tab" id="tab-${i}" aria-controls="cad-panel" aria-selected="${i === S.cadIndex}" tabindex="${i === S.cadIndex ? 0 : -1}">
    <span class="pn">${esc(p.part_no)}</span><span class="nm">${partName(p)}</span></button>`).join('');
  const btns = $$('button', tabs);
  const select = (i, focus) => {
    S.cadIndex = i;
    btns.forEach((b, k) => { b.setAttribute('aria-selected', String(k === i)); b.tabIndex = k === i ? 0 : -1; });
    $('#cad-panel').setAttribute('aria-labelledby', `tab-${i}`);
    if (focus) btns[i].focus();
    renderCad(parts[i], true);
  };
  btns.forEach((b, i) => {
    b.addEventListener('click', () => select(i));
    b.addEventListener('keydown', (e) => {
      const n = btns.length;
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); select((i + 1) % n, true); }
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); select((i - 1 + n) % n, true); }
      if (e.key === 'Home') { e.preventDefault(); select(0, true); }
      if (e.key === 'End') { e.preventDefault(); select(n - 1, true); }
    });
  });
}

function renderCad(part, animate) {
  $('#cad-drawing').innerHTML = C.drawing(part);
  const clrs = uniq(part.clr);
  $('#cad-spec').innerHTML = [
    dd(L('Part', '品番'), esc(part.part_no)),
    dd(L('Material', '材質'), esc(part.material)),
    dd(L('OD × wall', '外径 × 肉厚'), `${fmt(part.od, 2)} × ${fmt(part.wall, 2)} mm`),
    dd(L('CLR', '曲げR'), `${clrs.map((c) => fmt(c, 0)).join(' / ')} mm`),
    dd(L('D of bend', '曲げ半径比'), `${clrs.map((c) => fmt(c / part.od, 2)).join(' / ')} D`),
    dd(L('Wall factor', '肉厚係数'), fmt(part.od / part.wall, 1)),
  ].join('');
  $('#xyz-table').innerHTML = $('#xyz-table caption').outerHTML +
    `<thead><tr><th>${L('Point', '点')}</th><th>X</th><th>Y</th><th>Z</th></tr></thead><tbody>` +
    part.points.map((q, i) => `<tr><td>P${i}</td><td>${fmt(q[0], 2)}</td><td>${fmt(q[1], 2)}</td><td>${fmt(q[2], 2)}</td></tr>`).join('') + '</tbody>';
  $('#lra-table').innerHTML = $('#lra-table caption').outerHTML +
    `<thead><tr><th>${L('Bend', '曲げ')}</th><th>L <span class="unit">mm</span></th><th>R <span class="unit">°</span></th><th>A <span class="unit">°</span></th><th>CLR <span class="unit">mm</span></th></tr></thead><tbody>` +
    part.lra.map((r, i) => `<tr><td>B${i + 1}</td><td>${fmt(r.L, 2)}</td><td>${fmt(r.R, 2)}</td><td>${fmt(r.A, 2)}</td><td>${fmt(r.CLR, 1)}</td></tr>`).join('') +
    `</tbody><tfoot><tr><td>${L('Final L', '最終直線')}</td><td>${fmt(part.final_L, 2)}</td><td></td><td></td><td></td></tr></tfoot>`;
  $('#cad-cut').innerHTML = `<span class="k">${L('Cut length (developed centreline)', '切断長（中心線展開長）')}</span><span class="v" data-count="${part.cut_length}" data-dp="2">${fmt(part.cut_length, 2)}</span><span class="unit">mm</span>`;
  if (animate && S.full) animateCad();
}

function animateCad() {
  const root = $('#cad');
  const tube = $$('.draw', root);
  gsap.fromTo(tube, { strokeDasharray: 1, strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 1.4, ease: 'power2.inOut', stagger: 0.15, clearProps: 'strokeDasharray,strokeDashoffset' });
  gsap.fromTo($$('.pop', root), { opacity: 0 }, { opacity: 1, duration: 0.4, stagger: 0.04, delay: 0.5, clearProps: 'opacity' });
  gsap.fromTo($$('#xyz-table tbody tr, #lra-table tbody tr, #lra-table tfoot tr', root), { opacity: 0, x: -12 }, { opacity: 1, x: 0, duration: 0.45, stagger: 0.05, delay: 0.3, ease: 'power2.out', clearProps: 'opacity,transform' });
  countUp($('#cad-cut [data-count]'), 1.2);
}

function renderDfm(dfm) {
  const body = $('#dfm-body');
  if (!dfm) { body.innerHTML = pending('make artifacts'); return; }
  const items = Array.isArray(dfm) ? dfm : Object.entries(dfm).map(([k, v]) => ({ key: k, value: v }));
  body.innerHTML = `<ul class="dfm-list">${items.map((it) => {
    if (it && typeof it === 'object' && 'key' in it && 'value' in it) {
      const v = typeof it.value === 'object' ? JSON.stringify(it.value) : String(it.value);
      return `<li><span class="k">${esc(it.key)}</span>${esc(v)}</li>`;
    }
    const s = typeof it === 'object' ? Object.entries(it).map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(' · ') : String(it);
    return `<li>${esc(s)}</li>`;
  }).join('')}</ul>`;
}

function countUp(el, dur = 1.4) {
  if (!el || !S.full) return;
  const end = +el.dataset.count, dp = +(el.dataset.dp || 0), sign = el.dataset.sign === '1', o = { v: 0 };
  const show = (v) => `${sign && v > 0 ? '+' : ''}${fmt(v, dp)}`;
  el.setAttribute('aria-label', show(end));
  gsap.to(o, { v: end, duration: dur, ease: 'power2.out', onUpdate: () => { el.textContent = show(o.v); }, onComplete: () => { el.textContent = show(end); } });
}

/* ------------------------------------------------------------------ */
/* 02 bending and springback                                            */
/* ------------------------------------------------------------------ */
function bendSetup(d) {
  // Bend 1 of the TubeBEND tube when the data has it (its springback was measured), else the hero part.
  const part = d.parts.find((p) => /tubebend/i.test(p.name)) || S.heroPart;
  S.bendPart = part;
  const sb = d.springback && Number.isFinite(d.springback.target_mean) ? d.springback.target_mean : null;
  const ex = sb ? (sb >= 6 ? 1 : Math.min(5, Math.max(2, Math.round(8 / sb)))) : 1;
  S.bendCfg = { od: part.od, wall: part.wall, clr: part.lra[0].CLR, targetDeg: part.lra[0].A, springbackDeg: sb, exaggeration: ex };
  $('#bend-target').textContent = unitDeg(part.lra[0].A, 1);
  const what = `${esc(part.part_no)} · Ø${fmt(part.od, 1)} × ${fmt(part.wall, 1)} mm ${esc(part.material)} · CLR ${fmt(part.lra[0].CLR, 0)} mm · A ${fmt(part.lra[0].A, 1)}°`;
  $('#bend-note').innerHTML = sb
    ? L(`Bend 1 of ${what}. Springback is the TubeBEND measured mean (${fmt(d.springback.n_runs)} runs), drawn ×${ex} in 3D so the gap is visible; readouts are true values.`,
        `${what} の曲げ1。スプリングバックはTubeBEND実測平均（${fmt(d.springback.n_runs)}本）。3Dでは差が見えるよう×${ex}で表示し、数値は実際の値です。`)
    : L(`Bend 1 of ${what}. Springback magnitude pending: regenerate with <code>make train</code>.`, `${what} の曲げ1。スプリングバック量は未生成（<code>make train</code> で再生成）。`);
  $('#gap-chart').innerHTML = d.springback && d.springback.physics ? C.gapChart(d.springback) : pending('make train');
}

function setBend(p) {
  S.p.bend = p;
  if (S.bend) S.bend.setProgress(p);
  const cfg = S.bendCfg; if (!cfg) return;
  const sm = (x) => x * x * (3 - 2 * x), c01 = (x) => Math.max(0, Math.min(1, x));
  const draw = sm(c01((p - 0.12) / 0.48)), rel = sm(c01((p - 0.72) / 0.14));
  // same mapping as bend3d.js: only the springback part of the angle is drawn exaggerated
  const sb = cfg.springbackDeg || 0, A = cfg.targetDeg;
  const visOver = A + sb * cfg.exaggeration;
  const real = (vis) => (!sb || vis <= A) ? vis : A + (vis - A) / (visOver - A) * sb;
  const visDie = visOver * draw;
  const die = real(visDie), tube = real(visDie - (visOver - A) * rel * draw);
  $('#bend-die').textContent = unitDeg(die, 1);
  $('#bend-tube').textContent = unitDeg(tube, 1);
  const sbEl = $('#bend-sb');
  sbEl.textContent = cfg.springbackDeg ? (rel > 0.02 ? unitDeg(sb * rel, 2) : unitDeg(sb, 2)) : '—';
  sbEl.classList.toggle('accent', rel > 0.02);
  const step = p < 0.12 ? 0 : p < 0.6 ? 1 : p < 0.72 ? 2 : p < 0.86 ? 3 : 4;
  $$('#bend-steps li').forEach((li, i) => li.classList.toggle('on', S.full ? i === step : true));
  $('#gap-card').classList.toggle('show', !S.full || p >= 0.86);
}

/* ------------------------------------------------------------------ */
/* 03 springback ML                                                     */
/* ------------------------------------------------------------------ */
const MODEL = { mean: ['Mean (no model)', '平均値（モデルなし）'], ridge: ['Ridge', 'リッジ回帰'], random_forest: ['Random forest', 'ランダムフォレスト'], xgboost: ['XGBoost', 'XGBoost'] };
const FEAT = { setup: ['setup', '設定値'], 'setup+process': ['setup + process', '設定値＋プロセス'], none: ['none', 'なし'] };
const modelName = (key) => {
  const [m, f] = key.split(' | ');
  const mm_ = MODEL[m] || [m, m];
  const ff = FEAT[f] || [f || '', f || ''];
  return { m: mm_, f: ff };
};
const POLICY = {
  none: ['No compensation', '補正なし'],
  physics: ['Physics estimate (SUS304 assumed)', '理論推定（SUS304と仮定）'],
  offset: ['Constant offset from trial bends', '試し曲げからの一定オフセット'],
  ml: ['ML, setup only', '機械学習（設定値のみ）'],
  ml_in_process: ['ML with process signals', '機械学習（プロセス信号あり）'],
};

function renderML(d) {
  const sb = d.springback, cl = d.closed_loop;
  $('#ml-stats').innerHTML = sb ? [
    dd(L('Runs used', '使用データ'), fmt(sb.n_runs)),
    dd(L('Setup groups', '設定グループ'), fmt(sb.n_groups)),
    dd(L('Folds × repeats', '分割 × 反復'), `${fmt(sb.folds)} × ${fmt(sb.repeats)}`),
    dd(L('Mean springback', '平均スプリングバック'), `${fmt(sb.target_mean, 2)}° ± ${fmt(sb.target_sd, 2)}`),
  ].join('') : '';

  // parity
  const pc = $('#parity-chart');
  if (d.parity && d.parity.measured && d.parity.measured.length) {
    const tol = cl && cl.tolerance_deg;
    const P = C.parity(d.parity, tol);
    pc.innerHTML = P.svg;
    const hit = $('[data-parity]', pc), svg = $('svg', pc);
    hit.addEventListener('pointermove', (e) => {
      const r = svg.getBoundingClientRect(), k = P.W / r.width;
      const x = (e.clientX - r.left) * k, y = (e.clientY - r.top) * k;
      let best = -1, bd = 1e9;
      d.parity.measured.forEach((m, i) => { const dx = P.X(m) - x, dy = P.Y(d.parity.predicted[i]) - y, q = dx * dx + dy * dy; if (q < bd) { bd = q; best = i; } });
      if (best >= 0 && bd < 400) {
        hit.dataset.tip = `measured ${fmt(d.parity.measured[best], 3)}° · predicted ${fmt(d.parity.predicted[best], 3)}° · error ${fmt(d.parity.predicted[best] - d.parity.measured[best], 3)}°`;
        hit.dataset.tipJa = `実測 ${fmt(d.parity.measured[best], 3)}° · 予測 ${fmt(d.parity.predicted[best], 3)}° · 誤差 ${fmt(d.parity.predicted[best] - d.parity.measured[best], 3)}°`;
      } else { delete hit.dataset.tip; delete hit.dataset.tipJa; }
    });
    const mn = modelName(d.parity.model);
    $('#parity-cap').innerHTML = L(`Out-of-fold predictions of ${mn.m[0]} (${mn.f[0]}) for ${fmt(d.parity.measured.length)} bends. Dashed line: perfect prediction${tol ? `; shaded band: ±${fmt(tol, 2)}° tolerance` : ''}.`,
      `${mn.m[1]}（${mn.f[1]}）の交差検証外予測、${fmt(d.parity.measured.length)}本。破線は完全一致${tol ? `、帯は公差±${fmt(tol, 2)}°` : ''}。`);
  } else { pc.innerHTML = pending('make train'); $('#parity-cap').textContent = ''; }

  // closed-loop first-pass yield
  const fc = $('#fpy-chart');
  if (cl && cl.fpy) {
    const keys = Object.keys(POLICY).filter((k) => k in cl.fpy).concat(Object.keys(cl.fpy).filter((k) => !(k in POLICY)));
    const rows = keys.map((k) => {
      const [en, ja] = POLICY[k] || [k, k];
      const model = cl.models && cl.models[k] ? ` · ${modelName(cl.models[k]).m[0]}` : '';
      const mae = cl.mae_after && cl.mae_after[k];
      return { key: k, en: esc(en + model), ja: esc(ja + model), value: cl.fpy[k] * 100, sub: mae != null ? `MAE ${fmt(mae, 3)}°` : '',
        tip: `${en}: ${fmt(cl.fpy[k] * 100, 1)} % within ±${fmt(cl.tolerance_deg, 2)}°${mae != null ? `, mean abs. error ${fmt(mae, 3)}°` : ''}` };
    });
    fc.innerHTML = C.hbars(rows, { max: 100, unit: ' %', dp: 1, aria: `First-pass yield within plus or minus ${cl.tolerance_deg} degrees for each compensation policy`, accentKeys: ['ml', 'ml_in_process'] });
    const n = sb ? sb.n_runs : (d.parity ? d.parity.measured.length : null);
    $('#fpy-cap').innerHTML = L(`Share of ${n ? fmt(n) + ' ' : ''}real bends within ±${fmt(cl.tolerance_deg, 2)}° after each policy, out-of-fold.${cl.ml_interval90_deg != null ? ` 90 % of ML residuals are within ±${fmt(cl.ml_interval90_deg, 2)}°.` : ''}`,
      `各補正方式で公差±${fmt(cl.tolerance_deg, 2)}°に入った実曲げの割合（${n ? fmt(n) + '本、' : ''}交差検証外）。${cl.ml_interval90_deg != null ? `機械学習の残差の90 %は±${fmt(cl.ml_interval90_deg, 2)}°以内。` : ''}`);
  } else { fc.innerHTML = pending('make train'); $('#fpy-cap').textContent = ''; }

  // SHAP
  const sc = $('#shap-chart');
  if (Array.isArray(d.shap_setup) && d.shap_setup.length) {
    const rows = d.shap_setup.slice().sort((a, b) => b.mean_abs_shap_deg - a.mean_abs_shap_deg).slice(0, 10)
      .map((s) => ({ key: s.feature, en: esc(s.feature), ja: esc(s.feature), value: s.mean_abs_shap_deg }));
    sc.innerHTML = C.hbars(rows, { unit: '°', dp: 3, aria: 'Mean absolute SHAP value per setup feature, in degrees', accentKeys: [rows[0].key] });
  } else sc.innerHTML = pending('make train');

  // metrics table
  const mt = $('#metrics-table');
  if (sb && sb.springback) {
    const best = Object.values(sb.best || {});
    const val = (o) => (o && typeof o === 'object') ? o.mean : o;
    const pm = (o, dp) => (o && typeof o === 'object') ? `${fmt(o.mean, dp)}<span class="sd">± ${fmt(o.sd, dp)}</span>` : fmt(o, dp);
    const rows = Object.entries(sb.springback).sort((a, b) => val(a[1].mae) - val(b[1].mae));
    mt.innerHTML = `<table class="data"><thead><tr><th>${L('Model', 'モデル')}</th><th>${L('Features', '特徴量')}</th><th>MAE <span class="unit">°</span></th><th>RMSE <span class="unit">°</span></th><th>R²</th></tr></thead><tbody>` +
      rows.map(([k, v]) => {
        const n = modelName(k);
        return `<tr class="${best.includes(k) ? 'best' : ''}"><td class="txt">${L(esc(n.m[0]), esc(n.m[1]))}</td><td class="txt">${L(esc(n.f[0]), esc(n.f[1]))}</td><td>${pm(v.mae, 3)}</td><td>${pm(v.rmse, 3)}</td><td>${pm(v.r2, 2)}</td></tr>`;
      }).join('') + '</tbody></table>' +
      `<p class="cap">${L(`GroupKFold by setup, ${fmt(sb.folds)} folds × ${fmt(sb.repeats)} repeats: mean ± sd over folds. ● marks the best setup-only and setup + process models. The physics row has no training and no spread.`,
        `設定グループ単位のGroupKFold、${fmt(sb.folds)}分割 × ${fmt(sb.repeats)}反復（平均 ± 標準偏差）。●は設定値のみ・設定値＋プロセスの最良モデル。理論推定の行は学習なし・ばらつきなし。`)}</p>`;
  } else mt.innerHTML = pending('make train');
}

/* ------------------------------------------------------------------ */
/* 04 jig and fixture (DOM parts)                                       */
/* ------------------------------------------------------------------ */
function renderFixturePanel(fx) {
  const has = (b, ch) => (b.datum || '').split(',').map((s) => s.trim()).filter((s) => s.startsWith(ch));
  const list = (ch) => fx.blocks.flatMap((b) => has(b, ch).map((dname) => `${dname} (${b.id})`));
  const A = list('A'), B = list('B');
  const Cs = fx.end_stops.filter((e) => e.id.startsWith('C')).map((e) => e.id);
  $('#datum-legend').innerHTML = `
    <div><b>A · ${A.length}</b>${L(`Primary datum. ${A.join(', ')} fix the plane.`, `第1データム。${A.join('、')} で平面を拘束。`)}</div>
    <div class="b"><b>B · ${B.length}</b>${L(`Secondary datum. ${B.join(', ')} fix the direction.`, `第2データム。${B.join('、')} で方向を拘束。`)}</div>
    <div class="c"><b>C · ${Cs.length}</b>${L(`Tertiary datum. End stop ${Cs.join(', ')} fixes the position along the tube.`, `第3データム。端部ストッパ ${Cs.join('、')} で軸方向位置を拘束。`)}</div>`;
  $('#block-table').innerHTML = `<caption>${L(`${fx.blocks.length} blocks for ${esc(fx.part_no)}, tube clearance ${fmt(fx.clearance, 2)} mm, plate ${fx.plate.size.map((v) => fmt(v, 1)).join(' × ')} mm`, `${esc(fx.part_no)} 用 ${fx.blocks.length} 個、すきま ${fmt(fx.clearance, 2)} mm、プレート ${fx.plate.size.map((v) => fmt(v, 1)).join(' × ')} mm`)}</caption>
    <thead><tr><th>ID</th><th>X <span class="unit">mm</span></th><th>Y <span class="unit">mm</span></th><th>${L('Height', '高さ')} <span class="unit">mm</span></th><th>${L('Yaw', '向き')} <span class="unit">°</span></th><th>${L('Datum', 'データム')}</th><th>${L('Clamp', 'クランプ')}</th><th>${L('Sensor', 'センサ')}</th></tr></thead><tbody>` +
    fx.blocks.map((b) => `<tr><td>${esc(b.id)}</td><td>${fmt(b.x, 2)}</td><td>${fmt(b.y, 2)}</td><td>${fmt(b.height, 1)}</td><td>${fmt(b.yaw, 2)}</td><td>${esc(b.datum || '—')}</td><td>${b.clamp ? '●' : '—'}</td><td>${esc(b.sensor || '—')}</td></tr>`).join('') +
    fx.end_stops.map((e) => `<tr><td>${esc(e.id)}</td><td>${fmt(e.x, 2)}</td><td>${fmt(e.y, 2)}</td><td>${fmt(e.z, 1)}</td><td>—</td><td>${e.id.startsWith('C') ? 'C' : '—'}</td><td>—</td><td>—</td></tr>`).join('') + '</tbody>';
  S.flow = C.stateFlow($('#stateflow'));
  let lastNarrow = S.flow.narrow;
  new ResizeObserver(() => {
    const narrow = $('#stateflow').clientWidth < 620;
    if (narrow !== lastNarrow) { lastNarrow = narrow; const cur = S.flowState; S.flow = C.stateFlow($('#stateflow')); S.flowState = null; setFlow(cur || 'IDLE', false); }
  }).observe($('#stateflow'));
}

function fixturePhase(p, fx) {
  const sensors = fx.blocks.filter((b) => b.sensor).map((b) => b.sensor);
  const heights = uniq(fx.blocks.map((b) => fmt(b.height, 1)));
  const nA = fx.blocks.filter((b) => /A/.test(b.datum)).length, nB = fx.blocks.filter((b) => /B/.test(b.datum)).length, nC = fx.end_stops.filter((e) => e.id.startsWith('C')).length;
  if (p < 0.08) return L(`Base plate · ${fx.plate.size.map((v) => fmt(v, 0)).join(' × ')} mm`, `ベースプレート · ${fx.plate.size.map((v) => fmt(v, 0)).join(' × ')} mm`);
  if (p < 0.32) return L(`${fx.blocks.length} blocks rise to the centreline height · ${heights.join(' / ')} mm`, `受けブロック ${fx.blocks.length} 個 · 中心高さ ${heights.join(' / ')} mm`);
  if (p < 0.42) return L(`End stops, sensors ${sensors.join(' ')} and stack light`, `端部ストッパ、センサ ${sensors.join(' ')}、表示灯`);
  if (p < 0.54) return L(`Part drops into the nests · clearance ${fmt(fx.clearance, 2)} mm`, `ワーク投入 · すきま ${fmt(fx.clearance, 2)} mm`);
  if (p < 0.64) return L(`3-2-1 locating · A × ${nA}, B × ${nB}, C × ${nC}`, `3-2-1位置決め · A × ${nA}、B × ${nB}、C × ${nC}`);
  if (p < 0.72) return L(`Clamps close · ${fx.blocks.filter((b) => b.clamp).map((b) => b.id).join(', ')}`, `クランプ · ${fx.blocks.filter((b) => b.clamp).map((b) => b.id).join('、')}`);
  if (p < 0.82) return L(`Sensor check · ${sensors.join(', ')}`, `センサ検査 · ${sensors.join('、')}`);
  if (p < 0.9) return L('Pass · good part', '合格 · 良品');
  return L('Unclamp · ready for the next part', 'クランプ解除 · 次のワークへ');
}

function setFlow(state, animate) {
  if (!S.flow || S.flowState === state) return;
  S.flowState = state;
  S.flow.set(state, animate);
}

function setFixture(p) {
  S.p.fixture = p;
  if (!S.data || !S.data.fixture) return;
  if (S.fixture && !S.estop) S.fixture.setProgress(p);
  const fx = S.data.fixture;
  const ph = $('#fixture-phase'), txt = S.estop ? L('E-stop · all motion halted, reset to IDLE', '非常停止 · 全動作停止、IDLEへリセット') : fixturePhase(p, fx);
  if (ph.dataset.key !== txt) { ph.innerHTML = txt; ph.dataset.key = txt; }
  if (!S.estop) setFlow(C.stateAt(p), S.full);
}

function triggerEstop() {
  clearTimeout(S.estopTimer);
  S.estop = true;
  setFlow('ESTOP', S.full);
  if (S.fixture) S.fixture.setOverride('ESTOP');
  setFixture(S.p.fixture);
  S.estopTimer = setTimeout(() => {
    S.estop = false;
    if (S.fixture) S.fixture.setOverride(null);
    setFlow('IDLE', S.full);
    S.flowState = 'IDLE';
    setTimeout(() => { S.flowState = null; setFixture(S.p.fixture); }, 700);
  }, 2600);
}

/* ------------------------------------------------------------------ */
/* 05 line and kaizen                                                   */
/* ------------------------------------------------------------------ */
const KIND = { manual: ['manual', '手作業'], machine: ['machine', '機械'], walk: ['walk', '歩行'] };
const kindL = (k) => L(...(KIND[k] || [k, k]));

function lineStats(line) {
  const ct = line.stations.map((s) => s.cycle_s);
  const sum = ct.reduce((a, b) => a + b, 0), max = Math.max(...ct);
  const bn = line.stations[ct.indexOf(max)];
  return { sum, max, bn, balance: sum / (line.stations.length * max) * 100 };
}

function renderLine(line) {
  const st = lineStats(line);
  $('#line-spec').innerHTML = [
    dd(L('Takt time', 'タクトタイム'), `${fmt(line.takt_s, 1)} s`),
    dd(L('Demand', '需要'), `${fmt(line.demand_per_day)} /${L('day', '日')}`),
    dd(L('Stations', '工程数'), fmt(line.stations.length)),
    dd(L('Work content Σt', '総作業時間 Σt'), `${fmt(st.sum)} s`),
    dd(L('Line balance', '編成効率'), `${fmt(st.balance, 1)} %`),
    dd(L('Bottleneck', 'ボトルネック'), `${esc(st.bn.key)} ${fmt(st.max)} s`),
  ].join('');
  const scale = Math.max(line.takt_s, st.max) * 1.12;
  const cards = line.stations.map((s, i) => {
    const over = s.cycle_s > line.takt_s;
    return `<article class="station${over ? ' over' : ''}" role="listitem" aria-label="Station ${i + 1}: ${esc(s.name)}, cycle time ${fmt(s.cycle_s)} seconds">
      <div class="st-top"><span>${String(i + 1).padStart(2, '0')} · ${esc(s.key)}</span>${over ? `<span class="st-flag">${L('over takt', 'タクト超過')}</span>` : ''}</div>
      <p class="st-kanji" lang="ja">${esc(s.name_ja)}</p>
      <h3>${esc(s.name)}</h3>
      <div class="st-pic">${C.pictogram(s.key)}</div>
      <div class="ct">
        <div class="ct-row"><span>${L('Cycle time', 'サイクルタイム')}</span><span class="v">${fmt(s.cycle_s)} s</span></div>
        <div class="ct-bar"><span class="fill" style="width:${(s.cycle_s / scale * 100).toFixed(1)}%"></span><span class="takt" style="left:${(line.takt_s / scale * 100).toFixed(1)}%" data-label="takt ${fmt(line.takt_s, 1)} s"></span></div>
      </div>
      <ul class="el-list">${s.elements.map((e) => `<li><span class="sw ${esc(e.kind)}" aria-hidden="true"></span><span>${esc(e.name)} <span class="unit">${kindL(e.kind)}</span></span><span class="s">${fmt(e.s)} s</span></li>`).join('')}</ul>
    </article>`;
  }).join('');
  const summary = `<article class="station summary" role="listitem">
    <div class="st-top"><span>${L('Line summary', 'ライン概要')}</span></div>
    <dl>
      <div><dt class="sum-k">${L('Takt = available time ÷ demand', 'タクト = 稼働時間 ÷ 需要')}</dt><dd class="sum-v">${fmt(line.takt_s, 1)} s</dd></div>
      <div><dt class="sum-k">${L('Bottleneck', 'ボトルネック')}</dt><dd class="sum-v">${esc(st.bn.key)} · ${fmt(st.max)} s</dd></div>
      <div><dt class="sum-k">${L('Line balance Σt ÷ (n × t<sub>max</sub>)', '編成効率 Σt ÷ (n × t<sub>max</sub>)')}</dt><dd class="sum-v">${fmt(st.balance, 1)} %</dd></div>
    </dl>
    <p class="sum-k">${L('Synthetic cycle times. The kaizen below starts from this bottleneck.', '合成サイクルタイム。以下の改善はこのボトルネックから始まります。')}</p>
  </article>`;
  $('#stations').innerHTML = cards + summary;
}

function renderKaizen(d) {
  const k = d.kaizen, line = d.line;
  if (!k) { $('#yama-chart').innerHTML = pending('make sim'); $('#kaizen-chart').innerHTML = pending('make sim'); return; }
  // Yamazumi with before / after toggle
  if (k.yamazumi_before && k.yamazumi_after) {
    S.yama = C.yamazumi($('#yama-chart'), line, k.yamazumi_before, k.yamazumi_after);
    const cap = (state, r) => {
      const over = r.max > line.takt_s;
      $('#yama-cap').innerHTML = L(`${state === 'after' ? 'After rebalancing' : 'Before'}: slowest station ${esc(r.bottleneck)} at ${fmt(r.max)} s, ${over ? 'over' : 'under'} the ${fmt(line.takt_s, 1)} s takt. Hover a block for the work element.`,
        `${state === 'after' ? 'ライン編成後' : '改善前'}：最も遅い工程は ${esc(r.bottleneck)}（${fmt(r.max)} 秒）、タクト ${fmt(line.takt_s, 1)} 秒を${over ? '超過' : '下回る'}。ブロックにカーソルを置くと作業要素を表示。`);
    };
    const legend = `<div class="legend" aria-hidden="true"><span><i class="sw manual"></i>${kindL('manual')}</span><span><i class="sw machine"></i>${kindL('machine')}</span><span><i class="sw walk"></i>${kindL('walk')}</span><span><i class="ln"></i>${L('takt', 'タクト')}</span></div>`;
    $('#yama-chart').insertAdjacentHTML('afterbegin', legend);
    cap('before', S.yama.set('before', false));
    $$('#yama-toggle button').forEach((b) => b.addEventListener('click', () => {
      $$('#yama-toggle button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      cap(b.dataset.yama, S.yama.set(b.dataset.yama, S.full));
    }));
  } else $('#yama-chart').innerHTML = pending('make sim');

  // headline stats
  const rows = k.rows || [];
  const first = rows[0], last = rows[rows.length - 1];
  const stat = (v, unit, en, ja, dp, accent, sign) => `<div class="stat${accent ? ' accent' : ''}"><div class="v"><span data-count="${v}" data-dp="${dp}" data-sign="${sign ? 1 : 0}">${sign && v > 0 ? '+' : ''}${fmt(v, dp)}</span><span class="u">${unit}</span></div><div class="k">${L(en, ja)}</div></div>`;
  $('#kz-stats').innerHTML = (first && last ? [
    stat(k.throughput_gain_pct, '%', `good parts/day, ${esc(last.scenario.replace(/^\d+\s+/, ''))} vs baseline`, '良品数／日（現状比）', 1, true, true),
    stat(last.demand_met_pct, '%', `of demand met (baseline ${fmt(first.demand_met_pct, 1)} %)`, `需要充足率（現状 ${fmt(first.demand_met_pct, 1)} %）`, 1),
    stat(k.scrap_change_pts, 'pts', `scrap rate change (${fmt(first.scrap_pct, 1)} → ${fmt(last.scrap_pct, 1)} %)`, `不良率の変化（${fmt(first.scrap_pct, 1)} → ${fmt(last.scrap_pct, 1)} %）`, 2, false, true),
    stat(k.reps, `× ${fmt(k.days, 1)} d`, 'replications × simulated days per scenario', 'シナリオごとの反復回数 × 模擬日数', 0),
  ] : []).join('');

  if (rows.length) {
    $('#kaizen-chart').innerHTML = `<div class="legend" aria-hidden="true"><span><i style="background:var(--ink-2)"></i>${L('good parts/day, mean', '良品数／日（平均）')}</span><span><i class="ln" style="border-color:var(--ink)"></i>${L('95 % CI', '95 %信頼区間')}</span><span><i class="ln acc"></i>${L('demand', '需要')}</span></div>` + C.kaizenChart(rows, line.demand_per_day);
    $('#kaizen-cap').innerHTML = L(`Each bar: mean of ${fmt(k.reps)} replications × ${fmt(k.days, 1)} days. Labels: good parts/day and share of demand met. BN = bottleneck station. Scenarios are cumulative.`,
      `各棒は ${fmt(k.reps)} 回 × ${fmt(k.days, 1)} 日の平均。ラベルは良品数／日と需要充足率。BN = ボトルネック工程。シナリオは累積です。`);
    $('#kz-steps').innerHTML = rows.map((r) => {
      const { n, name } = C.splitScenario(r.scenario);
      return `<li><span class="sc">${L(`Step ${esc(n)}`, `ステップ ${esc(n)}`)}</span><span class="nm">${L(esc(name), esc(C.SCEN_JA[name] || name))}</span>
        <span class="kv"><span>${fmt(r.per_day, 1)} ± ${fmt(r.per_day_ci95, 1)} /${L('day', '日')}</span><span>${fmt(r.demand_met_pct, 1)} % ${L('demand', '需要')}</span><span>${L('scrap', '不良')} ${fmt(r.scrap_pct, 1)} %</span><span>OEE ${L('bend', '曲げ')} ${fmt(r.oee_bend * 100, 1)} %</span><span>BN ${esc(r.bottleneck)}</span></span>
        ${r.note ? `<span class="note">${esc(r.note)}</span>` : ''}</li>`;
    }).join('');
  } else $('#kaizen-chart').innerHTML = pending('make sim');

  $('#smed-chart').innerHTML = k.smed && k.smed.length ? `<div class="legend" aria-hidden="true"><span><i style="background:var(--s-manual)"></i>${L('internal (machine stopped)', '内段取り（停止中）')}</span><span><i class="ext"></i>${L('external (machine running)', '外段取り（稼働中）')}</span></div>` + C.smedChart(k.smed) : pending('make sim');
  $('#buffer-chart').innerHTML = k.buffer_curve && k.buffer_curve.length ? C.bufferChart(k.buffer_curve) : pending('make sim');
}

/* ------------------------------------------------------------------ */
/* 06 process sheet teaser                                              */
/* ------------------------------------------------------------------ */
function renderSheet(d) {
  const line = d.line, part = S.heroPart, st = lineStats(line);
  const head = (en, ja, v) => `<div>${L(en, ja)}<b>${v}</b></div>`;
  const byKind = (s, kind) => s.elements.filter((e) => e.kind === kind).reduce((a, e) => a + e.s, 0);
  $('#process-sheet').innerHTML = `<div class="sheet-head">
      ${head('Part no.', '品番', esc(part.part_no))}
      ${head('Part name', '品名', partName(part))}
      ${head('Takt', 'タクト', `${fmt(line.takt_s, 1)} s`)}
      ${head('Demand', '日当たり需要', `${fmt(line.demand_per_day)} /${L('day', '日')}`)}
    </div>
    <div class="table-wrap"><table class="data"><caption class="sr-only">Process sheet</caption>
      <thead><tr><th>No.</th><th>工程名</th><th>${L('Process', '工程')}</th><th>${L('Station', '設備')}</th><th>CT <span class="unit">s</span></th><th>${L('Manual', '手作業')} <span class="unit">s</span></th><th>${L('Machine', '機械')} <span class="unit">s</span></th><th>${L('Walk', '歩行')} <span class="unit">s</span></th><th>${L('vs takt', '対タクト')}</th></tr></thead>
      <tbody>${line.stations.map((s, i) => `<tr><td>${(i + 1) * 10}</td><td lang="ja">${esc(s.name_ja)}</td><td>${esc(s.name)}</td><td>${esc(s.key)}</td><td>${fmt(s.cycle_s)}</td><td>${fmt(byKind(s, 'manual'))}</td><td>${fmt(byKind(s, 'machine'))}</td><td>${fmt(byKind(s, 'walk'))}</td><td>${fmt(s.cycle_s / line.takt_s * 100)} %</td></tr>`).join('')}</tbody>
      <tfoot><tr><td></td><td></td><td>${L('Total work content', '総作業時間')}</td><td></td><td>${fmt(st.sum)}</td><td></td><td></td><td></td><td></td></tr></tfoot>
    </table></div>
    <p class="sheet-note">${L('Teaser built from the line model: sequence, cycle time and work content. Control items (管理項目), check methods and reaction plans belong in the full sheet.', 'ラインモデルから作成した抜粋（工程順・サイクルタイム・作業内容）。管理項目・検査方法・異常処置は正式な工程表で扱います。')}</p>`;
  if (d.generated_by) $('#generated-by').textContent = `Data: ${d.generated_by}.`;
}

/* ------------------------------------------------------------------ */
/* three.js stages: lazy, after first paint / when near                 */
/* ------------------------------------------------------------------ */
function webgl() {
  try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch { return false; }
}
const idle = (fn) => ('requestIdleCallback' in window ? requestIdleCallback(fn, { timeout: 700 }) : setTimeout(fn, 250));
function near(el, fn) {
  const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { io.disconnect(); fn(); } }, { rootMargin: '150% 0px' });
  io.observe(el);
}
function no3D(reason) {
  if (reason) console.warn('PipeForge: 3D view unavailable,', reason);
  html.classList.add('no3d');
  $$('.stage-fallback').forEach((e) => { e.hidden = false; });
  if (hasGSAP) ScrollTrigger.refresh();
}
function init3D() {
  if (!webgl()) { no3D(); return; }
  requestAnimationFrame(() => idle(async () => {
    try {
      const m = await import('./hero3d.js');
      S.hero = m.initHero({ canvas: $('#hero-canvas'), part: S.heroPart, onPhase: onHeroPhase, dimEl: S.heroDimTag });
      S.hero.setSpin(S.full);
      if (!S.full) S.hero.setYaw(-0.35);
      S.hero.setProgress(S.p.hero);
      $('#hero-poster').classList.add('is-hidden');
    } catch (e) { no3D(e); }
  }));
  near($('#bend-canvas'), async () => {
    try {
      const m = await import('./bend3d.js');
      S.bend = m.initBend({ canvas: $('#bend-canvas'), labelsEl: $('#bend-labels'), ...S.bendCfg });
      S.bend.setProgress(S.p.bend);
    } catch (e) { no3D(e); }
  });
  if (S.data.fixture) near($('#fixture-canvas'), async () => {
    try {
      const m = await import('./fixture3d.js');
      S.fixture = m.initFixture({ canvas: $('#fixture-canvas'), labelsEl: $('#fixture-labels'), fixture: S.data.fixture });
      S.fixture.setProgress(S.p.fixture);
      if (S.estop) S.fixture.setOverride('ESTOP');
    } catch (e) { no3D(e); }
  });
}

/* ------------------------------------------------------------------ */
/* motion: full (Lenis + ScrollTrigger) or reduced (static + controls)  */
/* ------------------------------------------------------------------ */
function wantFull() {
  if (!hasGSAP) return false;
  const o = store.get('pf-motion');
  if (o === 'reduce') return false;
  if (o === 'full') return true;
  return !osReduce.matches;
}

function teardown() {
  if (S.split) { S.split.revert(); S.split = null; }
  if (S.mm) { S.mm.revert(); S.mm = null; }
  if (S.ctx) { S.ctx.revert(); S.ctx = null; }
  if (S.lenis) { gsap.ticker.remove(S.lenisRaf); S.lenis.destroy(); S.lenis = null; }
}

function applyMotion() {
  teardown();
  S.full = wantFull();
  html.classList.toggle('motion', S.full);
  html.classList.toggle('reduced', !S.full);
  $('#motion-btn').setAttribute('aria-pressed', String(!S.full));
  $('#hero-control').hidden = S.full;
  $('#bend-control').hidden = S.full;
  $('#state-step').hidden = S.full;
  // the springback comparison overlays the 3D view while scrubbing, and sits below it when static
  const gapCard = $('#gap-card');
  (S.full ? $('#bend .stage-box') : $('#bend .bend-visual')).appendChild(gapCard);
  if (S.hero) { S.hero.setSpin(S.full); if (!S.full) S.hero.setYaw(-0.35); }
  if (S.full) setupFull(); else setupReduced();
}

const BEND_P = [0, 0.66, 1];
function setupReduced() {
  S.onHeroRange && S.onHeroRange();
  const b = $('#bend-control [aria-pressed="true"]');
  setBend(BEND_P[b ? +b.dataset.bendState : 2]);
  setFixture(C.STATE_P[S.reducedState || 'PASS']);
  if (hasGSAP) ScrollTrigger.refresh();
}

function setupFull() {
  S.lenis = Lenis ? new Lenis({ lerp: 0.1, anchors: true, autoRaf: false }) : null;
  if (S.lenis) {
    S.lenis.on('scroll', ScrollTrigger.update);
    S.lenisRaf = (t) => { if (S.lenis) S.lenis.raf(t * 1000); };
    gsap.ticker.add(S.lenisRaf);
    gsap.ticker.lagSmoothing(0);
  }
  const below = (el) => el.getBoundingClientRect().top > innerHeight * 0.92;

  S.ctx = gsap.context(() => {
    // 00 hero: pinned; unbend to the blank, re-bend bend by bend
    gsap.timeline({ scrollTrigger: { trigger: '#hero', start: 'top top', end: '+=300%', pin: true, scrub: true,
      onUpdate: (s) => setHero(s.progress), onRefresh: (s) => setHero(s.progress) } })
      .to('.hero-copy', { autoAlpha: 0, y: -48, ease: 'none', duration: 0.08 }, 0.05)
      .to('.scroll-cue', { autoAlpha: 0, ease: 'none', duration: 0.04 }, 0.01)
      .to({}, { duration: 1 }, 0);

    // 02 bending: pinned and scrubbed
    ScrollTrigger.create({ trigger: '#bend', start: 'top top', end: '+=260%', pin: true, scrub: true,
      onUpdate: (s) => setBend(s.progress), onRefresh: (s) => setBend(s.progress) });

    // 04 fixture: pinned exploded assembly + state machine
    if (S.data.fixture) ScrollTrigger.create({ trigger: '#fixture .fixture-pin', start: 'top top', end: '+=300%', pin: true, scrub: true,
      onUpdate: (s) => setFixture(s.progress), onRefresh: (s) => setFixture(s.progress) });

    // 01 drawing draws itself once
    const cad = $('#cad-panel');
    if (cad && below(cad)) {
      gsap.set($$('#cad .draw'), { strokeDasharray: 1, strokeDashoffset: 1 });
      gsap.set($$('#cad .pop, #xyz-table tbody tr, #lra-table tbody tr, #lra-table tfoot tr'), { opacity: 0 });
      ScrollTrigger.create({ trigger: cad, start: 'top 75%', once: true, onEnter: animateCad });
    }

    // reveals
    const rv = $$('.ch-head > *, .credit, .viz-card, .kz-head, .kz-block > .h3, .kz-stats .stat, .kz-steps li, .link-card, .sheet, .datum-legend > div, .dfm > *, .part-tabs')
      .filter((el) => !el.closest('#hero, #bend, .fixture-pin') && below(el));
    if (rv.length) gsap.set(rv, { autoAlpha: 0, y: 28 });
    if (rv.length) ScrollTrigger.batch(rv, { start: 'top 90%', once: true,
      onEnter: (els) => gsap.to(els, { autoAlpha: 1, y: 0, duration: 0.8, ease: 'power3.out', stagger: 0.07, overwrite: true }) });

    // charts grow from their baselines
    ['#parity-chart', '#fpy-chart', '#shap-chart', '#yama-chart', '#kaizen-chart', '#smed-chart', '#buffer-chart'].forEach((sel) => {
      const el = $(sel); if (!el || !below(el)) return;
      const gy = $$('.grow-y, .yseg', el), gx = $$('.grow-x', el), pop = $$('.pop', el);
      if (!gy.length && !gx.length && !pop.length) return;
      if (gy.length) gsap.set(gy, { scaleY: 0, transformOrigin: '50% 100%' });
      if (gx.length) gsap.set(gx, { scaleX: 0, transformOrigin: '0% 50%' });
      if (pop.length) gsap.set(pop, { opacity: 0 });
      ScrollTrigger.create({ trigger: el, start: 'top 82%', once: true, onEnter: () => {
        if (gy.length) gsap.to(gy, { scaleY: 1, duration: 0.9, ease: 'power3.out', stagger: 0.04 });
        if (gx.length) gsap.to(gx, { scaleX: 1, duration: 0.9, ease: 'power3.out', stagger: 0.06 });
        if (pop.length) gsap.to(pop, { opacity: 1, duration: 0.5, stagger: { amount: 0.7 } });
      } });
    });
    const stats = $('#kz-stats');
    if (stats && below(stats)) ScrollTrigger.create({ trigger: stats, start: 'top 85%', once: true, onEnter: () => $$('[data-count]', stats).forEach((el) => countUp(el)) });

    // hero title, once per page load
    if (!S.introDone && scrollY < 40) {
      S.introDone = true;
      if (SplitText) {
        const title = $('#hero-title');
        gsap.set(title, { autoAlpha: 0 });
        const go = () => {
          if (!S.full) { gsap.set(title, { autoAlpha: 1 }); return; }
          S.split = SplitText.create(title, { type: 'lines,chars', mask: 'lines' });
          gsap.set(title, { autoAlpha: 1 });
          gsap.from(S.split.chars, { yPercent: 110, duration: 1.1, ease: 'power4.out', stagger: 0.04 });
        };
        (document.fonts ? document.fonts.ready : Promise.resolve()).then(go);
      }
      gsap.from('.hero-copy .eyebrow, .hero-sub, .hero-lede, .hero-for, .hero-hmi', { autoAlpha: 0, y: 16, duration: 0.9, stagger: 0.08, delay: 0.35, ease: 'power3.out', clearProps: 'transform' });
    }
  });

  // 05 line: horizontal pinned scroll on wide screens, vertical cards on phones
  S.mm = gsap.matchMedia();
  S.mm.add('(min-width: 761px)', () => {
    const track = $('#stations');
    const dist = () => Math.max(0, track.scrollWidth - innerWidth);
    const tw = gsap.to(track, { x: () => -dist(), ease: 'none',
      scrollTrigger: { trigger: '#stations-pin', start: 'top top', end: () => '+=' + dist(), pin: true, scrub: true, invalidateOnRefresh: true } });
    $$('.station', track).forEach((st) => {
      const fill = $('.ct-bar .fill', st);
      if (fill) gsap.fromTo(fill, { scaleX: 0 }, { scaleX: 1, duration: 0.9, ease: 'power2.out',
        scrollTrigger: { trigger: st, containerAnimation: tw, start: 'left 85%', toggleActions: 'play none none reverse' } });
    });
  });
  S.mm.add('(max-width: 760px)', () => {
    $$('#stations .station').forEach((st) => {
      if (st.getBoundingClientRect().top > innerHeight) gsap.from(st, { y: 30, autoAlpha: 0, duration: 0.7, ease: 'power3.out', scrollTrigger: { trigger: st, start: 'top 90%', once: true } });
    });
  });
  ScrollTrigger.refresh();
}

/* ------------------------------------------------------------------ */
/* controls, chapter tracking, progress                                 */
/* ------------------------------------------------------------------ */
function wireControls() {
  $('#motion-btn').addEventListener('click', () => { store.set('pf-motion', S.full ? 'reduce' : 'full'); applyMotion(); });
  osReduce.addEventListener('change', () => { store.set('pf-motion', null); applyMotion(); });
  $$('#bend-control button').forEach((b) => b.addEventListener('click', () => {
    $$('#bend-control button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    setBend(BEND_P[+b.dataset.bendState]);
  }));
  $('#state-step').addEventListener('click', () => {
    const cur = C.stateAt(S.p.fixture);
    const next = C.STATES[(C.STATES.indexOf(cur) + 1) % C.STATES.length];
    S.reducedState = next;
    setFixture(C.STATE_P[next]);
  });
  $('#estop-btn').addEventListener('click', triggerEstop);
}

function setActive(i) {
  if (S.active === i) return;
  S.active = i;
  $$('.rail a').forEach((a) => {
    const on = +a.dataset.rail === i;
    a.classList.toggle('is-active', on);
    if (on) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
  });
  syncChapterLabel();
}
function syncChapterLabel() {
  const a = $(`.rail a[data-rail="${S.active || 0}"]`);
  if (!a) return;
  $('#now-num').textContent = a.querySelector('.rail-num').textContent;
  $('#now-name').innerHTML = a.querySelector('.rail-name').innerHTML;
}
function trackChapters() {
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => { if (e.isIntersecting) setActive(+e.target.dataset.chapter); });
  }, { rootMargin: '-45% 0px -54% 0px' });
  $$('main > section.chapter').forEach((s) => io.observe(s));
  setActive(0);
  let raf = 0;
  const bar = $('#progress-bar');
  const upd = () => { raf = 0; const h = html.scrollHeight - innerHeight; bar.style.transform = `scaleX(${h > 0 ? Math.min(1, scrollY / h) : 0})`; };
  addEventListener('scroll', () => { if (!raf) raf = requestAnimationFrame(upd); }, { passive: true });
  upd();
}

/* ------------------------------------------------------------------ */
/* boot                                                                 */
/* ------------------------------------------------------------------ */
async function boot() {
  let d;
  try {
    const r = await fetch('data.json', { cache: 'no-cache' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    d = await r.json();
  } catch (e) {
    const msg = document.createElement('p');
    msg.className = 'noscript';
    msg.setAttribute('role', 'alert');
    msg.textContent = `data.json could not be loaded (${e.message}). Serve the site folder over HTTP, for example: python -m http.server`;
    $('#main').prepend(msg);
    return;
  }
  S.data = d;
  S.heroPart = d.parts.find((p) => p.part_no === (d.fixture && d.fixture.part_no)) || d.parts.find((p) => p.part_no === 'PF-HB-2201') || d.parts[0];
  S.cadIndex = Math.max(0, d.parts.indexOf(S.heroPart));
  renderHero(S.heroPart);
  renderCadTabs(d.parts);
  renderCad(d.parts[S.cadIndex], false);
  renderDfm(d.dfm);
  bendSetup(d);
  renderML(d);
  if (d.fixture) renderFixturePanel(d.fixture);
  else { $('#stateflow').innerHTML = pending('make artifacts'); $('#estop-btn').hidden = true; }
  if (d.line) { renderLine(d.line); renderKaizen(d); renderSheet(d); }
  wireControls();
  trackChapters();
  applyMotion();
  init3D();
  if (document.fonts && hasGSAP) document.fonts.ready.then(() => { if (S.full) ScrollTrigger.refresh(); });
  if (/[?&]debug\b/.test(location.search)) window.__pipeforge = S;   // inspection hook, off by default
}
boot();
