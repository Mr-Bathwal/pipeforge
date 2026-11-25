// Shared three.js plumbing: one render loop for every stage, render on demand,
// DPR clamp, pause when off-screen or the tab is hidden, and a hollow-tube mesh
// that can be rebuilt in place every frame (fixed vertex count, no reallocation).
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

export { THREE };

const stages = new Set();
let loopOn = false;

export function webglAvailable() {
  try {
    const c = document.createElement('canvas');
    return !!(window.WebGL2RenderingContext && c.getContext('webgl2')) || !!c.getContext('webgl');
  } catch { return false; }
}

export function createStage(canvas, { fov = 30, near = 0.01, far = 100, shadows = false, exposure = 1 } = {}) {
  const coarse = matchMedia('(pointer: coarse)').matches;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, coarse ? 1.5 : 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.AgXToneMapping;
  renderer.toneMappingExposure = exposure;
  renderer.setClearColor(0x000000, 0);
  if (shadows) { renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap; }

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(renderer), 0.04).texture;
  pmrem.dispose();

  const camera = new THREE.PerspectiveCamera(fov, 1, near, far);
  const stage = {
    renderer, scene, camera, canvas, w: 0, h: 0,
    visible: false, dirty: true, animating: false,
    before: [], after: [], onResize: [],
    invalidate() { stage.dirty = true; },
    /** re-run every onResize hook now (modules call this after registering theirs) */
    refit() { stage.w = 0; stage.h = 0; resize(stage); },
  };
  new ResizeObserver(() => resize(stage)).observe(canvas);
  new IntersectionObserver(([e]) => {
    stage.visible = e.isIntersecting;
    if (stage.visible) stage.dirty = true;
  }, { rootMargin: '10% 0px' }).observe(canvas);
  canvas.addEventListener('webglcontextlost', (e) => { e.preventDefault(); stage.lost = true; });
  canvas.addEventListener('webglcontextrestored', () => { stage.lost = false; stage.dirty = true; });
  resize(stage);
  stages.add(stage);
  startLoop();
  return stage;
}

function resize(stage) {
  const w = stage.canvas.clientWidth, h = stage.canvas.clientHeight;
  if (!w || !h || (w === stage.w && h === stage.h)) return;
  stage.w = w; stage.h = h;
  stage.renderer.setSize(w, h, false);
  stage.camera.aspect = w / h;
  stage.onResize.forEach((f) => f(w, h));
  stage.camera.updateProjectionMatrix();
  stage.dirty = true;
}

let last = 0;
function tick(t) {
  if (document.hidden) return;
  const dt = Math.min(0.05, last ? t - last : 0.016);
  last = t;
  for (const s of stages) {
    if (!s.visible || s.lost) continue;
    if (!s.dirty && !s.animating) continue;
    s.dirty = false;
    for (const f of s.before) f(dt, t);
    s.renderer.render(s.scene, s.camera);
    for (const f of s.after) f(dt, t);
  }
}

function startLoop() {
  if (loopOn) return;
  loopOn = true;
  if (window.gsap) {
    window.gsap.ticker.add((time) => tick(time));       // same frame as ScrollTrigger and Lenis
  } else {
    const loop = (ms) => { tick(ms / 1000); requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
  }
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) { last = 0; stages.forEach((s) => { s.dirty = true; }); }
  });
}

/** Fit a camera so that a sphere of `radius` around `target` stays in frame. */
export function fitCamera(camera, radius, target, dir, margin = 1.08) {
  const vfov = THREE.MathUtils.degToRad(camera.fov);
  const hfov = 2 * Math.atan(Math.tan(vfov / 2) * camera.aspect);
  const dist = (radius * margin) / Math.sin(Math.min(vfov, hfov) / 2);
  camera.position.copy(dir).normalize().multiplyScalar(dist).add(target);
  camera.lookAt(target);
  return dist;
}

/** Project a world point to CSS pixels inside the stage. Returns null if behind the camera. */
const _v = new THREE.Vector3();
export function toScreen(stage, p) {
  _v.copy(p).project(stage.camera);
  if (_v.z > 1) return null;
  return { x: (_v.x + 1) / 2 * stage.w, y: (1 - _v.y) / 2 * stage.h };
}

/* ------------------------------------------------------------------ */
/* Hollow tube mesh: outer wall, inner wall, two annular end caps.      */
/* Frames are parallel-transported, so the rings never twist.            */
/* ------------------------------------------------------------------ */
export class TubeMesh {
  constructor(nStations, rOut, rIn, radial, outerMat, innerMat) {
    this.n = nStations; this.rad = radial; this.rOut = rOut; this.rIn = rIn;
    const n = nStations, r = radial;
    const vCount = n * r * 2 + 2 * r * 2;
    this.pos = new Float32Array(vCount * 3);
    this.nor = new Float32Array(vCount * 3);
    const idx = [];
    const O = 0, I = n * r, C0 = 2 * n * r, C1 = C0 + 2 * r;
    for (let i = 0; i < n - 1; i++) {
      for (let j = 0; j < r; j++) {
        const a = i * r + j, b = (i + 1) * r + j, c = (i + 1) * r + (j + 1) % r, d = i * r + (j + 1) % r;
        idx.push(O + a, O + d, O + b, O + d, O + c, O + b);
      }
    }
    for (let j = 0; j < r; j++) {           // start cap faces -T
      const o = C0 + j, o2 = C0 + (j + 1) % r, ii = C0 + r + j, i2 = C0 + r + (j + 1) % r;
      idx.push(o, ii, o2, ii, i2, o2);
    }
    for (let j = 0; j < r; j++) {           // end cap faces +T
      const o = C1 + j, o2 = C1 + (j + 1) % r, ii = C1 + r + j, i2 = C1 + r + (j + 1) % r;
      idx.push(o, o2, ii, ii, o2, i2);
    }
    const innerStart = idx.length;
    for (let i = 0; i < n - 1; i++) {
      for (let j = 0; j < r; j++) {
        const a = i * r + j, b = (i + 1) * r + j, c = (i + 1) * r + (j + 1) % r, d = i * r + (j + 1) % r;
        idx.push(I + a, I + b, I + d, I + d, I + b, I + c);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(this.pos, 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('normal', new THREE.BufferAttribute(this.nor, 3).setUsage(THREE.DynamicDrawUsage));
    g.setIndex(idx);
    g.addGroup(0, innerStart, 0);
    g.addGroup(innerStart, idx.length - innerStart, 1);
    this.geometry = g;
    this.mesh = new THREE.Mesh(g, [outerMat, innerMat || outerMat]);
    this.mesh.frustumCulled = false;
    this._T = new Float32Array(n * 3);
  }

  /**
   * points: flat array [x0,y0,z0, x1,...] with n stations.
   * tangents (optional): same layout, unit vectors. Otherwise bisectors of the polyline.
   */
  update(points, tangents) {
    const n = this.n, r = this.rad, P = points, T = this._T;
    if (tangents) T.set(tangents);
    else {
      let px = 1, py = 0, pz = 0;
      for (let i = 0; i < n; i++) {
        let ax = 0, ay = 0, az = 0;
        if (i > 0) { const dx = P[i*3] - P[i*3-3], dy = P[i*3+1] - P[i*3-2], dz = P[i*3+2] - P[i*3-1]; const l = Math.hypot(dx, dy, dz); if (l > 1e-9) { ax += dx / l; ay += dy / l; az += dz / l; } }
        if (i < n - 1) { const dx = P[i*3+3] - P[i*3], dy = P[i*3+4] - P[i*3+1], dz = P[i*3+5] - P[i*3+2]; const l = Math.hypot(dx, dy, dz); if (l > 1e-9) { ax += dx / l; ay += dy / l; az += dz / l; } }
        const l = Math.hypot(ax, ay, az);
        if (l > 1e-9) { px = ax / l; py = ay / l; pz = az / l; }
        T[i*3] = px; T[i*3+1] = py; T[i*3+2] = pz;
      }
    }
    // initial U perpendicular to T0
    let tx = T[0], ty = T[1], tz = T[2];
    let ux, uy, uz;
    if (Math.abs(ty) < 0.9) { ux = tz; uy = 0; uz = -tx; } else { ux = 0; uy = -tz; uz = ty; }   // T x (0,1,0) or T x (1,0,0)
    let l = Math.hypot(ux, uy, uz); ux /= l; uy /= l; uz /= l;
    const pos = this.pos, nor = this.nor, ro = this.rOut, ri = this.rIn;
    const I = n * r, C0 = 2 * n * r, C1 = C0 + 2 * r;
    const cosT = this._cos || (this._cos = Float32Array.from({ length: r }, (_, j) => Math.cos(j / r * Math.PI * 2)));
    const sinT = this._sin || (this._sin = Float32Array.from({ length: r }, (_, j) => Math.sin(j / r * Math.PI * 2)));
    for (let i = 0; i < n; i++) {
      const nx = T[i*3], ny = T[i*3+1], nz = T[i*3+2];
      if (i > 0) {
        // rotate U by the rotation taking T(i-1) to T(i) (Rodrigues)
        const cx = ty * nz - tz * ny, cy = tz * nx - tx * nz, cz = tx * ny - ty * nx;
        const s = Math.hypot(cx, cy, cz), c = tx * nx + ty * ny + tz * nz;
        if (s > 1e-9) {
          const kx = cx / s, ky = cy / s, kz = cz / s;
          const kd = kx * ux + ky * uy + kz * uz;
          const kxux = ky * uz - kz * uy, kxuy = kz * ux - kx * uz, kxuz = kx * uy - ky * ux;
          ux = ux * c + kxux * s + kx * kd * (1 - c);
          uy = uy * c + kxuy * s + ky * kd * (1 - c);
          uz = uz * c + kxuz * s + kz * kd * (1 - c);
        }
        const d = ux * nx + uy * ny + uz * nz;           // re-orthogonalise
        ux -= nx * d; uy -= ny * d; uz -= nz * d;
        l = Math.hypot(ux, uy, uz) || 1; ux /= l; uy /= l; uz /= l;
      }
      tx = nx; ty = ny; tz = nz;
      const vx = ty * uz - tz * uy, vy = tz * ux - tx * uz, vz = tx * uy - ty * ux;   // V = T x U
      const ox = P[i*3], oy = P[i*3+1], oz = P[i*3+2];
      for (let j = 0; j < r; j++) {
        const dx = cosT[j] * ux + sinT[j] * vx, dy = cosT[j] * uy + sinT[j] * vy, dz = cosT[j] * uz + sinT[j] * vz;
        const a = (i * r + j) * 3, b = (I + i * r + j) * 3;
        pos[a] = ox + dx * ro; pos[a+1] = oy + dy * ro; pos[a+2] = oz + dz * ro;
        nor[a] = dx; nor[a+1] = dy; nor[a+2] = dz;
        pos[b] = ox + dx * ri; pos[b+1] = oy + dy * ri; pos[b+2] = oz + dz * ri;
        nor[b] = -dx; nor[b+1] = -dy; nor[b+2] = -dz;
        if (i === 0 || i === n - 1) {
          const base = i === 0 ? C0 : C1, sg = i === 0 ? -1 : 1;
          const co = (base + j) * 3, ci = (base + r + j) * 3;
          pos[co] = pos[a]; pos[co+1] = pos[a+1]; pos[co+2] = pos[a+2];
          pos[ci] = pos[b]; pos[ci+1] = pos[b+1]; pos[ci+2] = pos[b+2];
          nor[co] = nor[ci] = sg * tx; nor[co+1] = nor[ci+1] = sg * ty; nor[co+2] = nor[ci+2] = sg * tz;
        }
      }
    }
    const g = this.geometry;
    g.attributes.position.needsUpdate = true;
    g.attributes.normal.needsUpdate = true;
  }
}

/* ------------------------------------------------------------------ */
/* LRA to centreline, with a bend fraction per bend.                    */
/* Total length is constant: material for an arc of R*A is always there, */
/* so a half-made bend leaves the rest of that arc as straight tube.     */
/* ------------------------------------------------------------------ */
export const ARC_N = 28;
export function lraStationCount(nBends) { return nBends * (2 + ARC_N + 1 + 2) + 2; }

function rot(v, k, ang) {           // rotate v about unit k
  const c = Math.cos(ang), s = Math.sin(ang), d = k[0] * v[0] + k[1] * v[1] + k[2] * v[2];
  return [
    v[0] * c + (k[1] * v[2] - k[2] * v[1]) * s + k[0] * d * (1 - c),
    v[1] * c + (k[2] * v[0] - k[0] * v[2]) * s + k[1] * d * (1 - c),
    v[2] * c + (k[0] * v[1] - k[1] * v[0]) * s + k[2] * d * (1 - c),
  ];
}

/**
 * Walk the LRA program in the machine frame: start at the origin, feed along +X,
 * first bend towards +Y. Returns stations (points + tangents, mm) of fixed count.
 */
export function lraStations(lra, finalL, fractions, sign = 1) {
  const pts = [], tans = [];
  let p = [0, 0, 0], T = [1, 0, 0], N = [0, 1, 0];
  const push = (q, t) => { pts.push(q[0], q[1], q[2]); tans.push(t[0], t[1], t[2]); };
  const add = (a, b, k) => [a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k];
  lra.forEach((row, i) => {
    push(p, T); p = add(p, T, row.L); push(p, T);
    if (row.R) N = rot(N, T, sign * row.R * Math.PI / 180);
    const Afull = row.A * Math.PI / 180, R = row.CLR;
    const f = Math.max(0, Math.min(1, fractions[i] ?? 1));
    const th = Afull * f;
    const c = add(p, N, R);
    for (let k = 0; k <= ARC_N; k++) {
      const ph = th * k / ARC_N, cp = Math.cos(ph), sp = Math.sin(ph);
      const q = [c[0] - N[0] * R * cp + T[0] * R * sp, c[1] - N[1] * R * cp + T[1] * R * sp, c[2] - N[2] * R * cp + T[2] * R * sp];
      push(q, [T[0] * cp + N[0] * sp, T[1] * cp + N[1] * sp, T[2] * cp + N[2] * sp]);
    }
    const ct = Math.cos(th), st = Math.sin(th);
    const T2 = [T[0] * ct + N[0] * st, T[1] * ct + N[1] * st, T[2] * ct + N[2] * st];
    const N2 = [N[0] * ct - T[0] * st, N[1] * ct - T[1] * st, N[2] * ct - T[2] * st];
    p = [c[0] - N[0] * R * ct + T[0] * R * st, c[1] - N[1] * R * ct + T[1] * R * st, c[2] - N[2] * R * ct + T[2] * R * st];
    T = T2; N = N2;
    push(p, T); p = add(p, T, R * (Afull - th)); push(p, T);   // not-yet-bent material stays straight
  });
  push(p, T); p = add(p, T, finalL); push(p, T);
  return { pts, tans, end: p };
}

/**
 * Rigid transform from the machine frame to the part's CAD frame:
 * X -> first feed direction, Y -> first bend direction, origin -> first point.
 * Picks the sign convention of R whose rebuilt end point lands on the CAD end point.
 */
export function machineToCad(part) {
  const P = part.points;
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const nrm = (a) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const d0 = nrm(sub(P[1], P[0]));
  const e = sub(P[2], P[1]);
  const n0 = nrm(sub(e, d0.map((v) => v * dot(e, d0))));
  const b0 = cross(d0, n0);
  const map = (q) => [P[0][0] + d0[0] * q[0] + n0[0] * q[1] + b0[0] * q[2],
                      P[0][1] + d0[1] * q[0] + n0[1] * q[1] + b0[1] * q[2],
                      P[0][2] + d0[2] * q[0] + n0[2] * q[1] + b0[2] * q[2]];
  const mapDir = (q) => [d0[0] * q[0] + n0[0] * q[1] + b0[0] * q[2], d0[1] * q[0] + n0[1] * q[1] + b0[1] * q[2], d0[2] * q[0] + n0[2] * q[1] + b0[2] * q[2]];
  const last = P[P.length - 1];
  let best = null;
  for (const sign of [1, -1]) {
    const { end } = lraStations(part.lra, part.final_L, part.lra.map(() => 1), sign);
    const q = map(end);
    const err = Math.hypot(q[0] - last[0], q[1] - last[1], q[2] - last[2]);
    if (!best || err < best.err) best = { sign, err };
  }
  return { map, mapDir, sign: best.sign, endError: best.err };
}
