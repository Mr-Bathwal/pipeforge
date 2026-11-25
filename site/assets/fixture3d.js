// Checking fixture for the hero part, built from data.json `fixture`:
// plate (top at z = 0), U-nest blocks at their contact points and yaw, toggle clamps,
// proximity sensors, end stops, the tube, and a stack light that follows the station state.
import { THREE, createStage, fitCamera, toScreen, TubeMesh } from './three-kit.js';
import { STATES, STATE_P, stateAt } from './charts.js';

const MM = 0.001;
const smooth = (x) => x * x * (3 - 2 * x);
const seg = (p, a, b) => smooth(Math.max(0, Math.min(1, (p - a) / (b - a))));

export { STATES, STATE_P, stateAt };

export function initFixture({ canvas, labelsEl, fixture }) {
  const stage = createStage(canvas, { fov: 28, shadows: true, exposure: 1.0 });
  const { scene, camera } = stage;
  const fx = fixture;
  const od = fx.od, c = fx.clearance;
  const v3 = (x, y, z) => new THREE.Vector3(x * MM, z * MM, -y * MM);   // CAD (x, y, z) -> three

  const plateMat = new THREE.MeshStandardMaterial({ color: 0x7d848d, metalness: 0.55, roughness: 0.5 });
  const blockMat = new THREE.MeshStandardMaterial({ color: 0xb8bec6, metalness: 0.6, roughness: 0.38 });
  const darkMat = new THREE.MeshStandardMaterial({ color: 0x30353c, metalness: 0.6, roughness: 0.45 });
  const handleMat = new THREE.MeshStandardMaterial({ color: 0xd2471a, metalness: 0.1, roughness: 0.5 });
  const datumMats = {
    A: new THREE.MeshStandardMaterial({ color: 0x16181b, metalness: 0.3, roughness: 0.5 }),
    B: new THREE.MeshStandardMaterial({ color: 0x1f5e7a, metalness: 0.3, roughness: 0.5 }),
    C: new THREE.MeshStandardMaterial({ color: 0xb23a0b, metalness: 0.3, roughness: 0.5 }),
  };
  const steel = new THREE.MeshPhysicalMaterial({ color: 0xcfd4da, metalness: 1, roughness: 0.3 });
  const bore = new THREE.MeshStandardMaterial({ color: 0x5d636b, metalness: 0.9, roughness: 0.55 });

  const root = new THREE.Group();
  scene.add(root);

  // plate
  const [pw, ph, pt] = fx.plate.size;
  const plate = new THREE.Mesh(new THREE.BoxGeometry(pw * MM, pt * MM, ph * MM), plateMat);
  const pcx = (fx.plate.min[0] + fx.plate.max[0]) / 2, pcy = (fx.plate.min[1] + fx.plate.max[1]) / 2;
  plate.position.copy(v3(pcx, pcy, -pt / 2));
  plate.receiveShadow = true;
  const plateG = new THREE.Group(); plateG.add(plate); root.add(plateG);

  // blocks: base up to the tube's underside, two cheeks up to the centreline (a U nest)
  const blocks = fx.blocks.map((b) => {
    const g = new THREE.Group();
    g.position.copy(v3(b.x, b.y, 0));
    g.rotation.y = b.yaw * Math.PI / 180;
    const rise = new THREE.Group(); g.add(rise);
    const hBase = Math.max(1, b.height - od / 2);
    const base = new THREE.Mesh(new THREE.BoxGeometry(b.length * MM, hBase * MM, b.width * MM), blockMat);
    base.position.y = hBase / 2 * MM;
    base.castShadow = true; base.receiveShadow = true;
    rise.add(base);
    const cw = Math.max(2, (b.width - od - 2 * c) / 2);
    const ch = b.height + od * 0.15;
    for (const s of [-1, 1]) {
      const cheek = new THREE.Mesh(new THREE.BoxGeometry(b.length * MM, ch * MM, cw * MM), blockMat);
      cheek.position.set(0, ch / 2 * MM, s * (od / 2 + c + cw / 2) * MM);
      cheek.castShadow = true;
      rise.add(cheek);
    }
    const d = (b.datum || '').split(',').map((s) => s.trim()).filter(Boolean);
    if (d.length) {
      const pad = new THREE.Mesh(new THREE.BoxGeometry(b.length * 0.9 * MM, 1.2 * MM, (od * 0.7) * MM), datumMats[d[0][0]] || datumMats.A);
      pad.position.y = (hBase + 0.6) * MM;
      rise.add(pad);
    }
    root.add(g);
    const out = { b, g, rise, datum: d, top: (b.height + od / 2 + 14) };

    if (b.clamp) {   // toggle clamp on the +z side, arm swings over the tube
      const zc = (b.width / 2 + 8);
      const pivotY = b.height + od / 2 + 10;
      const post = new THREE.Mesh(new THREE.BoxGeometry(14 * MM, pivotY * MM, 14 * MM), darkMat);
      post.position.set(0, pivotY / 2 * MM, zc * MM);
      post.castShadow = true;
      g.add(post);
      const arm = new THREE.Group();
      arm.position.set(0, pivotY * MM, zc * MM);
      const bar = new THREE.Mesh(new THREE.BoxGeometry(12 * MM, 6 * MM, (zc + 4) * MM), darkMat);
      bar.position.z = -(zc + 4) / 2 * MM;
      const padC = new THREE.Mesh(new THREE.CylinderGeometry(5 * MM, 5 * MM, 9 * MM, 16), handleMat);
      padC.position.set(0, -6 * MM, -zc * MM);
      const handle = new THREE.Mesh(new THREE.BoxGeometry(8 * MM, 8 * MM, 30 * MM), handleMat);
      handle.position.set(0, 6 * MM, 14 * MM);
      handle.rotation.x = -0.5;
      arm.add(bar, padC, handle);
      arm.traverse((m) => { m.castShadow = true; });
      g.add(arm);
      out.arm = arm;
    }
    if (b.sensor) {  // M12 proximity sensor on the -z side, aimed at the tube
      const zs = (b.width / 2 + 10);
      const sg = new THREE.Group();
      const body = new THREE.Mesh(new THREE.CylinderGeometry(6 * MM, 6 * MM, 34 * MM, 20), darkMat);
      body.rotation.x = Math.PI / 2;
      body.position.set(0, b.height * MM, -zs * MM);
      const bracket = new THREE.Mesh(new THREE.BoxGeometry(16 * MM, b.height * MM, 4 * MM), blockMat);
      bracket.position.set(0, b.height / 2 * MM, -(zs + 4) * MM);
      const ledMat = new THREE.MeshStandardMaterial({ color: 0x222222, emissive: 0x000000, roughness: 0.4 });
      const led = new THREE.Mesh(new THREE.SphereGeometry(3.2 * MM, 14, 10), ledMat);
      led.position.set(0, b.height * MM, -(zs + 18) * MM);
      sg.add(body, bracket, led);
      sg.traverse((m) => { m.castShadow = true; });
      g.add(sg);
      out.sensor = { group: sg, led: ledMat, at: () => g.localToWorld(new THREE.Vector3(0, (b.height + 12) * MM, -(zs + 10) * MM)) };
    }
    return out;
  });

  // end stops
  const stops = fx.end_stops.map((e) => {
    const sgn = e.x < 0 ? -1 : 1;
    const h = e.z + od / 2 + 8;
    const m = new THREE.Mesh(new THREE.BoxGeometry(12 * MM, h * MM, 34 * MM), e.id.startsWith('C') ? datumMats.C : darkMat);
    m.position.copy(v3(e.x + sgn * 7, e.y, h / 2));
    m.castShadow = true;
    const g = new THREE.Group(); g.add(m); root.add(g);
    return { e, g, at: () => v3(e.x + sgn * 7, e.y, h + 10) };
  });

  // stack light on the plate corner
  const lamp = (color) => new THREE.MeshStandardMaterial({ color: 0x2a2d31, emissive: color, emissiveIntensity: 0, roughness: 0.3, transparent: true, opacity: 0.95 });
  const lampRed = lamp(0xff3b30), lampAmb = lamp(0xffb000), lampGrn = lamp(0x2fd16b);
  const stack = new THREE.Group();
  const sx = fx.plate.max[0] - 40, sy = fx.plate.max[1] - 30;
  stack.position.copy(v3(sx, sy, 0));
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(4 * MM, 4 * MM, 90 * MM, 12), darkMat);
  pole.position.y = 45 * MM; stack.add(pole);
  [lampGrn, lampAmb, lampRed].forEach((mat, i) => {
    const l = new THREE.Mesh(new THREE.CylinderGeometry(11 * MM, 11 * MM, 18 * MM, 24), mat);
    l.position.y = (100 + i * 19) * MM; stack.add(l);
  });
  root.add(stack);

  // the tube
  const cl = fx.centerline;
  const tube = new TubeMesh(cl.length, od / 2 * MM, (od / 2 - 1.6) * MM, 40, steel, bore);
  const flat = new Float32Array(cl.length * 3);
  cl.forEach((q, i) => { const v = v3(q[0], q[1], q[2]); flat[i*3] = v.x; flat[i*3+1] = v.y; flat[i*3+2] = v.z; });
  tube.update(flat);
  tube.mesh.castShadow = true;
  const tubeG = new THREE.Group(); tubeG.add(tube.mesh); root.add(tubeG);

  // lights and shadow
  const key = new THREE.DirectionalLight(0xffffff, 1.4);
  key.position.set(0.4, 1.4, 0.8);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 1024);
  Object.assign(key.shadow.camera, { left: -0.6, right: 0.6, top: 0.4, bottom: -0.4, near: 0.3, far: 3 });
  key.shadow.radius = 4; key.shadow.bias = -0.0004;
  scene.add(key);

  // labels
  const mk = (cls, html) => { const d = document.createElement('div'); d.className = 'tag3d ' + cls; d.innerHTML = html; labelsEl.appendChild(d); return d; };
  const tags = [];
  blocks.forEach((o) => {
    if (o.datum.length) {
      const letter = o.datum[0][0].toLowerCase();
      tags.push({ el: mk('datum ' + (letter === 'a' ? '' : letter), o.datum.join(' · ')), at: () => o.g.localToWorld(new THREE.Vector3(0, o.top * MM, 0)), kind: o.datum[0][0], o });
    }
    if (o.sensor) tags.push({ el: mk('sensor', o.b.sensor), at: o.sensor.at, kind: 'S', o });
  });
  stops.forEach((s) => tags.push({ el: mk(s.e.id.startsWith('C') ? 'datum c' : '', s.e.id), at: s.at, kind: s.e.id.startsWith('C') ? 'C' : 'E' }));

  // camera
  const target = new THREE.Vector3(0, 0.03, 0.01);
  const dir = new THREE.Vector3(0.12, 0.78, 1.0);
  const radius = Math.max(pw, ph) / 2 * MM;
  stage.onResize.push((w, h) => {
    camera.aspect = w / h;
    const wide = w > 900;
    // the fixture is long and flat: fit its length to the width, the sphere fit wastes height
    const vf = THREE.MathUtils.degToRad(camera.fov), hf = 2 * Math.atan(Math.tan(vf / 2) * camera.aspect);
    const m = wide ? 1.02 : 1.06;
    const dist = Math.max((radius * m) / Math.tan(hf / 2), (ph * MM * 1.6) / Math.tan(vf / 2));
    camera.position.copy(dir).normalize().multiplyScalar(dist).add(target);
    camera.lookAt(target);
    if (wide && w / h < 1.6) camera.setViewOffset(w, h, -w * 0.05, -h * 0.05, w, h);
    else camera.setViewOffset(w, h, 0, -h * 0.02, w, h);
  });

  let p = 1, override = null;
  const order = blocks.map((o, i) => i).sort((a, b) => blocks[a].b.x - blocks[b].b.x);
  function apply() {
    const pl = seg(p, 0, 0.12);
    plateG.visible = pl > 0.001;
    plateG.position.y = (1 - pl) * -0.06;
    plateG.scale.setScalar(0.92 + 0.08 * pl);
    order.forEach((idx, k) => {
      const o = blocks[idx];
      const a = 0.08 + k / order.length * 0.22;
      const s = seg(p, a, a + 0.08);
      o.g.visible = s > 0.001;
      o.rise.scale.y = Math.max(0.001, s);
      const sens = seg(p, 0.32, 0.42);
      if (o.sensor) o.sensor.group.scale.setScalar(Math.max(0.001, sens));
      if (o.arm) {
        const close = seg(p, 0.64, 0.71), reopen = seg(p, 0.9, 0.97);
        o.arm.rotation.x = 1.75 * (1 - close + reopen);
        o.arm.scale.setScalar(Math.max(0.001, sens));
      }
    });
    stops.forEach((s) => { const k = seg(p, 0.32, 0.42); s.g.visible = k > 0.001; s.g.scale.set(1, Math.max(0.001, k), 1); });
    stack.scale.setScalar(Math.max(0.001, seg(p, 0.32, 0.42)));
    stack.visible = p > 0.32;
    const drop = seg(p, 0.42, 0.54);
    tubeG.visible = drop > 0.001;
    tubeG.position.y = (1 - drop) * 0.22;

    const st = override || stateAt(p);
    // sensors: amber when the part is present, green one by one during CHECK and after
    const sensors = blocks.filter((o) => o.sensor);
    sensors.forEach((o, i) => {
      let col = 0x000000;
      if (st === 'ESTOP') col = 0x000000;
      else if (p >= 0.54) col = 0xffb000;
      const okAt = 0.73 + i * 0.025;
      if (st !== 'ESTOP' && p >= okAt && p < 0.97) col = 0x2fd16b;
      o.sensor.led.emissive.setHex(col);
      o.sensor.led.emissiveIntensity = col ? 2.2 : 0;
    });
    lampRed.emissiveIntensity = st === 'ESTOP' || st === 'FAIL' ? 2.4 : 0;
    lampAmb.emissiveIntensity = !override && (st === 'CLAMPING' || st === 'CHECK' || st === 'UNCLAMP') ? 2 : 0;
    lampGrn.emissiveIntensity = !override && st === 'PASS' ? 2.4 : 0;

    tags.forEach((t) => {
      let show = false;
      if (t.kind === 'A') show = p >= 0.54;
      else if (t.kind === 'B') show = p >= 0.58;
      else if (t.kind === 'C') show = p >= 0.62;
      else if (t.kind === 'S') show = p >= 0.4;
      else show = p >= 0.42;
      t.el.style.opacity = show ? '1' : '0';
    });
    stage.invalidate();
  }

  stage.after.push(() => {
    for (const t of tags) {
      const s = toScreen(stage, t.at());
      if (s) t.el.style.transform = `translate(${s.x}px, ${s.y}px) ${t.kind === 'S' ? 'translate(-110%, -10%)' : 'translate(-50%, -100%)'}`;
    }
  });

  stage.refit();
  apply();
  return {
    stage,
    setProgress(x) { p = Math.max(0, Math.min(1, x)); apply(); },
    setOverride(s) { override = s; apply(); },
  };
}
