// Rotary-draw bending, stylised but to scale: bend die (CLR groove), clamp die,
// pressure die and wiper die on bend 1 of the hero part. Tube length is constant:
// the arc R*theta is drawn from the trailing straight (pipeforge-research T3, T4).
import { THREE, createStage, fitCamera, toScreen, TubeMesh } from './three-kit.js';

const S = 0.01;                 // 1 scene unit = 100 mm
const ARC = 36;
const smooth = (x) => x * x * (3 - 2 * x);
const clamp01 = (x) => Math.max(0, Math.min(1, x));
const D2R = Math.PI / 180;

/**
 * opts: { canvas, labelsEl, od, wall, clr, targetDeg, springbackDeg (null when pending), exaggeration, onUpdate }
 * World frame: bend plane XZ, die axis +Y, tangent point at the origin, die centre at (0, 0, -R).
 * Curve (x, y) of research T3 maps to world (x, 0, -y); a bend of theta is a rotation of +theta about Y.
 */
export function initBend(opts) {
  const { canvas, labelsEl, od, wall, clr, targetDeg } = opts;
  const sb = opts.springbackDeg;
  const ex = opts.exaggeration || 1;
  const stage = createStage(canvas, { fov: 30, exposure: 1.0 });
  const { scene, camera } = stage;

  const R = clr * S, r = (od / 2) * S, ri = (od / 2 - wall) * S;
  const H = r * 1.12;          // tooling half-height: just above the tube so it stays visible from above
  const visTarget = targetDeg * D2R;
  const visOver = sb ? (targetDeg + sb * ex) * D2R : visTarget;
  const Llead = 3.2 * od * S;
  const Ltail0 = R * visOver + 5 * od * S;
  const realDeg = (vis) => {           // visual angle -> real angle (only the springback part is exaggerated)
    if (!sb || vis <= visTarget) return vis / D2R;
    return targetDeg + (vis - visTarget) / (visOver - visTarget) * sb;
  };

  const steel = new THREE.MeshPhysicalMaterial({ color: 0xcfd4da, metalness: 1, roughness: 0.28 });
  const bore = new THREE.MeshStandardMaterial({ color: 0x5d636b, metalness: 0.9, roughness: 0.55 });
  const tool = new THREE.MeshStandardMaterial({ color: 0x3b4048, metalness: 0.75, roughness: 0.42 });
  const toolLight = new THREE.MeshStandardMaterial({ color: 0x737a83, metalness: 0.8, roughness: 0.35 });
  const accent = new THREE.MeshStandardMaterial({ color: 0xf15534, metalness: 0.1, roughness: 0.55 });
  const ghostMat = new THREE.MeshBasicMaterial({ color: 0xf15534, transparent: true, opacity: 0, depthWrite: false });

  const centre = new THREE.Vector3(0, 0, -R);

  // bend die: a lathe with a semicircular groove whose centre sits at the CLR
  const prof = [new THREE.Vector2(0.001, -H), new THREE.Vector2(R, -H), new THREE.Vector2(R, -r * 1.02)];
  for (let k = 0; k <= 16; k++) { const ph = -Math.PI / 2 + Math.PI * k / 16; prof.push(new THREE.Vector2(R - r * 1.02 * Math.cos(ph), r * 1.02 * Math.sin(ph))); }
  prof.push(new THREE.Vector2(R, r * 1.02), new THREE.Vector2(R, H), new THREE.Vector2(0.001, H));
  const dieGroup = new THREE.Group();
  dieGroup.position.copy(centre);
  dieGroup.add(new THREE.Mesh(new THREE.LatheGeometry(prof, 96), tool));
  dieGroup.add(new THREE.Mesh(new THREE.CylinderGeometry(R * 0.22, R * 0.22, H * 2.3, 40), toolLight));
  scene.add(dieGroup);

  // everything that turns with the die; local frame: the lead straight runs along +X at z = +R
  const swing = new THREE.Group();
  swing.position.copy(centre);
  scene.add(swing);
  const mark = new THREE.Mesh(new THREE.BoxGeometry(R * 0.55, 0.004, 0.014), accent);
  mark.position.set(R * 0.1, H + 0.002, R * 0.62);
  mark.rotation.y = Math.PI / 2;
  swing.add(mark);
  const insert = new THREE.Mesh(new THREE.BoxGeometry(Llead, H * 2, r * 1.5), tool);
  insert.position.set(Llead / 2, 0, R - r);
  swing.add(insert);
  const clampDie = new THREE.Group();
  const clampBlock = new THREE.Mesh(new THREE.BoxGeometry(Llead, H * 2, r * 1.6), toolLight);
  clampBlock.position.x = Llead / 2;
  const clampStripe = new THREE.Mesh(new THREE.BoxGeometry(Llead * 0.9, 0.006, r * 0.3), accent);
  clampStripe.position.set(Llead / 2, H + 0.003, 0);
  clampDie.add(clampBlock, clampStripe);
  swing.add(clampDie);
  const clampZ = (open) => R + r * 1.1 + open * r * 1.4;

  // pressure die: outside of the trailing straight (z > 0), travels with the tube
  const Lpd = Ltail0 * 0.86;
  const pressure = new THREE.Mesh(new THREE.BoxGeometry(Lpd, H * 2, r * 1.6), toolLight);
  scene.add(pressure);
  const pdZ = (open) => r * 1.1 + open * r * 1.4;

  // wiper die: inside of the tail (z < 0), its feather edge at the tangent point
  const Lw = 2.6 * od * S;
  const wShape = new THREE.Shape([new THREE.Vector2(-Lw, 0), new THREE.Vector2(0, 0), new THREE.Vector2(0, -r * 1.2), new THREE.Vector2(-Lw, -r * 0.55)]);
  const wiper = new THREE.Mesh(new THREE.ExtrudeGeometry(wShape, { depth: H * 1.6, bevelEnabled: false }), tool);
  wiper.rotation.x = Math.PI / 2;
  wiper.position.set(-0.003, H * 0.8, -r * 0.95);
  scene.add(wiper);

  // tube and the ghost of its loaded shape
  const nSt = 2 + (ARC + 1) + 2;
  const tube = new TubeMesh(nSt, r, ri, 40, steel, bore);
  scene.add(tube.mesh);
  const ghost = new TubeMesh(nSt, r * 1.03, r * 0.99, 32, ghostMat, ghostMat);
  ghost.mesh.renderOrder = 2;
  scene.add(ghost.mesh);
  const tp = new Float32Array(nSt * 3), tt = new Float32Array(nSt * 3);
  const gp = new Float32Array(nSt * 3), gt = new Float32Array(nSt * 3);

  function centreline(theta, Rc, P, T) {
    let i = 0;
    const put = (x, y, tx, ty) => { P[i*3] = x; P[i*3+1] = 0; P[i*3+2] = -y; T[i*3] = tx; T[i*3+1] = 0; T[i*3+2] = -ty; i++; };
    const tail = Ltail0 - Rc * theta;
    put(-tail, 0, 1, 0); put(0, 0, 1, 0);
    for (let k = 0; k <= ARC; k++) { const ph = theta * k / ARC; put(Rc * Math.sin(ph), Rc * (1 - Math.cos(ph)), Math.cos(ph), Math.sin(ph)); }
    const x0 = Rc * Math.sin(theta), y0 = Rc * (1 - Math.cos(theta)), c = Math.cos(theta), s = Math.sin(theta);
    put(x0, y0, c, s); put(x0 + Llead * c, y0 + Llead * s, c, s);
  }

  // dimension: reference line, arm and arc of the tube angle, drawn just above the die
  const arcR = R + r * 4.2;
  const lift = H + 0.01;
  const lineMat = new THREE.LineBasicMaterial({ color: 0xf15534 });
  const refMat = new THREE.LineBasicMaterial({ color: 0x9aa1ab });
  const arcGeo = new THREE.BufferGeometry();
  const arcPos = new Float32Array(65 * 3);
  arcGeo.setAttribute('position', new THREE.BufferAttribute(arcPos, 3));
  const dim = new THREE.Group();
  dim.position.set(centre.x, lift, centre.z);
  const arcLine = new THREE.Line(arcGeo, lineMat);
  const radial = [new THREE.Vector3(0, 0, R + r * 1.6), new THREE.Vector3(0, 0, arcR + r)];
  const refLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints(radial), refMat);
  const arm = new THREE.Line(new THREE.BufferGeometry().setFromPoints(radial), lineMat);
  dim.add(arcLine, refLine, arm);
  scene.add(dim);

  // DOM labels
  const L = (en, ja) => `<span class="l" lang="en">${en}</span><span class="l" lang="ja">${ja}</span>`;
  const mk = (cls, html) => { const d = document.createElement('div'); d.className = 'tag3d ' + cls; d.innerHTML = html; labelsEl.appendChild(d); return d; };
  const w = new THREE.Vector3();
  const labels = [
    { el: mk('', L('Bend die', '曲げ型')), at: () => w.set(centre.x - R * 0.45, H, centre.z - R * 0.3) },
    { el: mk('', L('Clamp die', 'クランプ型')), at: () => swing.localToWorld(w.set(Llead * 0.7, H, clampDie.position.z)) },
    { el: mk('', L('Pressure die', 'プレッシャー型')), at: () => w.set(pressure.position.x - Lpd * 0.25, H, pressure.position.z) },
    { el: mk('', L('Wiper die', 'しわ押さえ型')), at: () => w.set(-Lw * 0.7, H, -r * 2.2) },
  ];
  const angleTag = mk('angle', '');
  let tubeVis = 0;

  let p = 0;
  function apply() {
    // 0-.12 clamp in · .12-.6 draw to the overbend · .6-.72 hold · .72-.86 release · .86-1 compare
    const clampIn = smooth(clamp01(p / 0.12));
    const draw = smooth(clamp01((p - 0.12) / 0.48));
    const rel = smooth(clamp01((p - 0.72) / 0.14));
    const thDie = visOver * draw;
    const thTube = sb ? thDie - (visOver - visTarget) * rel * draw : thDie;
    const Rc = thTube > 1e-6 ? R * thDie / thTube : R;        // arc length conserved: the radius opens
    tubeVis = thTube;

    const open = Math.min(1, 1 - clampIn + rel);
    swing.rotation.y = thDie;
    dieGroup.rotation.y = thDie;
    clampDie.position.z = clampZ(open);
    pressure.position.set(-Lpd / 2 + R * thDie, 0, pdZ(open));

    centreline(thTube, Rc, tp, tt); tube.update(tp, tt);
    centreline(thDie, R, gp, gt); ghost.update(gp, gt);
    ghostMat.opacity = sb ? 0.3 * rel : 0;
    ghost.mesh.visible = ghostMat.opacity > 0.005;

    for (let k = 0; k <= 64; k++) { const a = thTube * k / 64; arcPos[k*3] = arcR * Math.sin(a); arcPos[k*3+1] = 0; arcPos[k*3+2] = arcR * Math.cos(a); }
    arcGeo.attributes.position.needsUpdate = true;
    arcGeo.computeBoundingSphere();
    arm.rotation.y = thTube;
    dim.visible = thTube > 0.01;

    opts.onUpdate && opts.onUpdate({ p, clampIn, draw, rel, dieDeg: realDeg(thDie), tubeDeg: realDeg(thTube) });
    stage.invalidate();
  }

  stage.after.push(() => {
    for (const l of labels) {
      const s = toScreen(stage, l.at());
      if (s) l.el.style.transform = `translate(${s.x}px, ${s.y}px) translate(-50%, -130%)`;
    }
    const a = tubeVis / 2, rr = arcR + r * 2.6;
    const s = toScreen(stage, w.set(centre.x + rr * Math.sin(a), lift, centre.z + rr * Math.cos(a)));
    if (s) angleTag.style.transform = `translate(${s.x}px, ${s.y}px) translate(-50%, -50%)`;
    angleTag.textContent = realDeg(tubeVis).toFixed(1) + '°';
    angleTag.style.opacity = tubeVis > 0.05 ? '1' : '0';
  });

  // camera: footprint of the cell, tail partly off-frame like a real machine bed
  const xmin = -0.72 * Ltail0, xmax = R + Llead * 0.95, zmin = -(2 * R + r * 3), zmax = r * 4;
  const target = new THREE.Vector3((xmin + xmax) / 2, 0, (zmin + zmax) / 2);
  const radius = Math.max(xmax - xmin, zmax - zmin) / 2;
  const dir = new THREE.Vector3(0.25, 1.5, 1.0);
  stage.onResize.push((wd, ht) => { camera.aspect = wd / ht; fitCamera(camera, radius, target, dir, wd / ht < 1.1 ? 1.12 : 0.96); });

  const key = new THREE.DirectionalLight(0xffffff, 1.1);
  key.position.set(1, 3, 2);
  scene.add(key);

  stage.refit();
  apply();
  return { stage, setProgress(x) { p = clamp01(x); apply(); } };
}
