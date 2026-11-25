// Hero: the real PF-HB-2201 handlebar, rebuilt from its LRA program.
// Scroll unbends it to the straight blank, then re-bends it bend by bend.
import { THREE, createStage, fitCamera, toScreen, TubeMesh, lraStations, lraStationCount, machineToCad } from './three-kit.js';

const MM = 0.001;                         // scene units are metres
const smooth = (x) => x * x * (3 - 2 * x);

export function initHero({ canvas, part, onPhase, dimEl }) {
  const stage = createStage(canvas, { fov: 26, shadows: true, exposure: 1.05 });
  const { scene, camera } = stage;
  const nb = part.lra.length;
  const xf = machineToCad(part);

  // CAD (x, y, z) mm -> three (x, z, -y) m : Z up in CAD, Y up in three
  const toThree = (q, out = new THREE.Vector3()) => out.set(q[0] * MM, q[2] * MM, -q[1] * MM);

  const steel = new THREE.MeshPhysicalMaterial({ color: 0xc9ced4, metalness: 1, roughness: 0.3, envMapIntensity: 1.05 });
  const bore = new THREE.MeshStandardMaterial({ color: 0x5d636b, metalness: 0.9, roughness: 0.55 });
  const n = lraStationCount(nb);
  const tube = new TubeMesh(n, (part.od / 2) * MM, (part.od / 2 - part.wall) * MM, 48, steel, bore);
  tube.mesh.castShadow = true;

  const turntable = new THREE.Group();
  const holder = new THREE.Group();          // re-centred every rebuild
  holder.add(tube.mesh);
  turntable.add(holder);
  scene.add(turntable);

  // XYZ intersection points and virtual sharps: the CAD input, faded out once unbending starts
  const cad = new THREE.Group();
  const sharpPts = part.points.map((q) => toThree(q));
  const sharpGeo = new THREE.BufferGeometry().setFromPoints(sharpPts);
  const sharpLine = new THREE.Line(sharpGeo, new THREE.LineDashedMaterial({ color: 0xe8501a, dashSize: 0.012, gapSize: 0.008, transparent: true }));
  sharpLine.computeLineDistances();
  cad.add(sharpLine);
  const dotGeo = new THREE.SphereGeometry(0.0065, 20, 12);
  const dotMat = new THREE.MeshBasicMaterial({ color: 0xe8501a, transparent: true });
  sharpPts.forEach((p) => { const m = new THREE.Mesh(dotGeo, dotMat); m.position.copy(p); cad.add(m); });
  holder.add(cad);

  // light + contact shadow
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(0.6, 1.6, 0.9);
  key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024);
  key.shadow.camera.left = -0.6; key.shadow.camera.right = 0.6; key.shadow.camera.top = 0.6; key.shadow.camera.bottom = -0.6;
  key.shadow.camera.near = 0.5; key.shadow.camera.far = 3;
  key.shadow.radius = 6; key.shadow.bias = -0.0005;
  scene.add(key);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(3, 3), new THREE.ShadowMaterial({ opacity: 0.13, depthWrite: false }));
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -0.085;
  floor.receiveShadow = true;
  scene.add(floor);

  // camera framing: a sphere around the longest state (the straight blank)
  const radius = (part.cut_length / 2) * MM;
  const target = new THREE.Vector3(0, -0.005, 0);
  const viewDir = new THREE.Vector3(0.0, 0.62, 1);
  stage.onResize.push((w, h) => {
    camera.aspect = w / h;
    const wide = w / h > 1.2 && w > 900;
    fitCamera(camera, radius, target, viewDir, wide ? 0.97 : 0.98);
    if (wide) camera.setViewOffset(w, h, -w * 0.02, h * 0.1, w, h);
    else camera.setViewOffset(w, h, 0, h * 0.02, w, h);
  });

  // state
  const fr = new Array(nb).fill(1);
  let p = 0, yaw = -0.35, spin = true, cadAlpha = 1, lastKey = '';
  const box = new THREE.Box3();
  const centre = new THREE.Vector3();
  const tmp = new THREE.Vector3();
  const pts = new Float32Array(n * 3), tans = new Float32Array(n * 3);

  function rebuild() {
    const key = fr.map((f) => f.toFixed(4)).join(',');
    if (key === lastKey) return;
    lastKey = key;
    const s = lraStations(part.lra, part.final_L, fr, xf.sign);
    box.makeEmpty();
    for (let i = 0; i < n; i++) {
      const q = xf.map([s.pts[i*3], s.pts[i*3+1], s.pts[i*3+2]]);
      const d = xf.mapDir([s.tans[i*3], s.tans[i*3+1], s.tans[i*3+2]]);
      toThree(q, tmp); pts[i*3] = tmp.x; pts[i*3+1] = tmp.y; pts[i*3+2] = tmp.z; box.expandByPoint(tmp);
      tans[i*3] = d[0]; tans[i*3+1] = d[2]; tans[i*3+2] = -d[1];
    }
    tube.update(pts, tans);
    box.getCenter(centre);
    holder.position.set(-centre.x, -centre.y, -centre.z);
  }

  // phases of p (0..1): 0-.1 CAD, .1-.38 unbend, .38-.46 blank, .46-.96 re-bend in sequence, then done
  function apply() {
    let phase, bend = -1, frac = 1;
    if (p < 0.1) { fr.fill(1); phase = 'cad'; }
    else if (p < 0.38) { const u = smooth((p - 0.1) / 0.28); fr.fill(1 - u); phase = 'unbend'; frac = 1 - u; }
    else if (p < 0.46) { fr.fill(0); phase = 'blank'; }
    else if (p < 0.96) {
      const q = (p - 0.46) / 0.5 * nb;
      for (let i = 0; i < nb; i++) fr[i] = smooth(Math.max(0, Math.min(1, q - i)));
      bend = Math.min(nb - 1, Math.floor(q)); frac = fr[bend]; phase = 'bend';
    } else { fr.fill(1); phase = 'done'; }
    cadAlpha = p < 0.1 ? 1 : Math.max(0, 1 - (p - 0.1) / 0.06);
    if (phase === 'done') cadAlpha = Math.min(1, (p - 0.96) / 0.04);
    sharpLine.material.opacity = cadAlpha; dotMat.opacity = cadAlpha; cad.visible = cadAlpha > 0.01;
    rebuild();
    onPhase && onPhase({ phase, bend, frac, fractions: fr.slice(), p });
    stage.invalidate();
  }

  stage.before.push((dt) => {
    if (spin) yaw += dt * 0.16;
    turntable.rotation.y = yaw;
  });

  // dimension tag for the blank's cut length
  stage.after.push(() => {
    if (!dimEl) return;
    const show = p >= 0.36 && p < 0.5;
    dimEl.style.opacity = show ? '1' : '0';
    if (!show) return;
    tmp.set(0, -0.045, 0);
    const s = toScreen(stage, tmp);
    if (s) dimEl.style.transform = `translate(${s.x}px, ${s.y}px) translate(-50%, 0)`;
  });

  stage.refit();
  apply();
  return {
    stage,
    endError: xf.endError,
    setProgress(v) { p = Math.max(0, Math.min(1, v)); apply(); },
    setSpin(on) { spin = on; stage.animating = on; stage.invalidate(); },
    setYaw(v) { yaw = v; stage.invalidate(); },
  };
}
