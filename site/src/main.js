import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/examples/jsm/renderers/CSS2DRenderer.js";

const EXAGGERATION_DEFAULT = 1.5;

async function loadGrid(url) {
  const res = await fetch(url);
  return res.json();
}

// grid.x/grid.y are 1D axes (flat-earth local-meters approx), grid.elev is [row][col],
// grid.u/grid.v are 1D texture-coord axes into imagery.jpg (same approx)
function buildDemMesh(grid, exaggeration, opacity, texture) {
  const { width, height, x, y, elev, u, v } = grid;
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(width * height * 3);
  const uvs = new Float32Array(width * height * 2);

  for (let r = 0; r < height; r++) {
    for (let c = 0; c < width; c++) {
      const i = (r * width + c) * 3;
      positions[i] = x[c];
      positions[i + 1] = elev[r][c] * exaggeration;
      positions[i + 2] = -y[r];

      const j = (r * width + c) * 2;
      uvs[j] = u[c];
      uvs[j + 1] = v[r];
    }
  }

  const indices = [];
  for (let r = 0; r < height - 1; r++) {
    for (let c = 0; c < width - 1; c++) {
      const a = r * width + c;
      const b = a + 1;
      const d = a + width;
      const e = d + 1;
      indices.push(a, d, b, b, d, e);
    }
  }

  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();

  const material = new THREE.MeshStandardMaterial({
    color: texture ? 0xffffff : 0x8fb8d8,
    map: texture ?? null,
    transparent: true,
    opacity,
    side: THREE.DoubleSide,
    roughness: 0.8,
  });

  const mesh = new THREE.Mesh(geometry, material);
  // draw first (depthWrite stays on) so HRRR - drawn after - can still depth-test
  // and blend against it; renderOrder alone is what makes the draw order deterministic
  mesh.renderOrder = 0;
  return mesh;
}

// one box per model grid cell - the native blocky resolution of HRRR/RRFS terrain
function buildHrrrMesh(grid, exaggeration, opacity) {
  const { width, height, x, y, elev, cellSizeX, cellSizeY } = grid;
  const geometry = new THREE.BoxGeometry(cellSizeX, 1, cellSizeY); // flush, no gaps
  const material = new THREE.MeshStandardMaterial({
    color: 0xd98a3d,
    roughness: 0.9,
    transparent: true,
    opacity,
  });
  const mesh = new THREE.InstancedMesh(geometry, material, width * height);
  mesh.renderOrder = 1; // draw after the DEM so lowering opacity reveals it, not the void

  const m = new THREE.Matrix4();
  let i = 0;
  for (let r = 0; r < height; r++) {
    for (let c = 0; c < width; c++) {
      const h = Math.max(elev[r][c] * exaggeration, 1);
      m.makeScale(1, h, 1);
      m.setPosition(x[c], h / 2, -y[r]);
      mesh.setMatrixAt(i, m);
      i++;
    }
  }
  mesh.instanceMatrix.needsUpdate = true;
  return mesh;
}

// thin black outline around the top face of every HRRR cell, since the blocks
// sit flush with no gaps and would otherwise blend into one solid slab
function buildHrrrEdges(grid, exaggeration) {
  const { width, height, x, y, elev, cellSizeX, cellSizeY } = grid;
  const hw = cellSizeX / 2;
  const hd = cellSizeY / 2;
  const positions = [];

  for (let r = 0; r < height; r++) {
    for (let c = 0; c < width; c++) {
      const top = Math.max(elev[r][c] * exaggeration, 1) + 1; // +1m to avoid z-fighting
      const cx = x[c];
      const cz = -y[r];
      const corners = [
        [cx - hw, top, cz - hd],
        [cx + hw, top, cz - hd],
        [cx + hw, top, cz + hd],
        [cx - hw, top, cz + hd],
      ];
      for (let i = 0; i < 4; i++) {
        positions.push(...corners[i], ...corners[(i + 1) % 4]);
      }
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  const material = new THREE.LineBasicMaterial({ color: 0x000000 });
  const lines = new THREE.LineSegments(geometry, material);
  lines.renderOrder = 2; // on top of the HRRR blocks themselves
  return lines;
}

const FEET_PER_METER = 3.28084;

// one CSS2D label per HRRR cell showing its elevation in feet
function buildHrrrLabels(grid, exaggeration) {
  const { width, height, x, y, elev } = grid;
  const labels = [];
  for (let r = 0; r < height; r++) {
    for (let c = 0; c < width; c++) {
      const el = document.createElement("div");
      el.className = "elev-label";
      el.textContent = `${Math.round((elev[r][c] * FEET_PER_METER) / 100) * 100} ft`;
      const obj = new CSS2DObject(el);
      const top = Math.max(elev[r][c] * exaggeration, 1);
      obj.position.set(x[c], top + 1, -y[r]);
      labels.push(obj);
    }
  }
  return labels;
}

// highways.ways is a list of {label, x, y, elev} polylines (draped on terrain,
// raised slightly to avoid z-fighting); highways.labels is one point per
// distinct route ref, already picked at its longest segment's midpoint
function buildHighways(highways, exaggeration) {
  const group = new THREE.Group();
  const material = new THREE.LineBasicMaterial({ color: 0xffd400 });
  for (const way of highways.ways) {
    const positions = new Float32Array(way.x.length * 3);
    for (let i = 0; i < way.x.length; i++) {
      positions[i * 3] = way.x[i];
      positions[i * 3 + 1] = way.elev[i] * exaggeration + 2;
      positions[i * 3 + 2] = -way.y[i];
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const line = new THREE.Line(geometry, material);
    line.renderOrder = 2;
    group.add(line);
  }

  const labels = highways.labels.map((l) => {
    const el = document.createElement("div");
    el.className = "hwy-label";
    el.textContent = l.label;
    const obj = new CSS2DObject(el);
    obj.position.set(l.x, l.elev * exaggeration + 2, -l.y);
    return obj;
  });

  return { group, labels };
}

function loadTexture(url) {
  return new THREE.TextureLoader().loadAsync(url).then((tex) => {
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  });
}

async function main() {
  const [hrrr, dem, imageryTexture, pins, highways] = await Promise.all([
    loadGrid("/data/hrrr.json"),
    loadGrid("/data/dem.json"),
    loadTexture("/data/imagery.jpg"),
    loadGrid("/data/pins.json"),
    loadGrid("/data/highways.json"),
  ]);

  const app = document.getElementById("app");
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0e14);

  const camera = new THREE.PerspectiveCamera(
    55,
    window.innerWidth / window.innerHeight,
    1,
    100000,
  );
  camera.position.set(16000, 13000, 20000);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(window.innerWidth, window.innerHeight);
  app.appendChild(renderer.domElement);

  const labelRenderer = new CSS2DRenderer();
  labelRenderer.setSize(window.innerWidth, window.innerHeight);
  labelRenderer.domElement.style.position = "absolute";
  labelRenderer.domElement.style.top = "0";
  labelRenderer.domElement.style.left = "0";
  labelRenderer.domElement.style.pointerEvents = "none";
  document.body.appendChild(labelRenderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 2200, 0);
  controls.update();

  scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  const sun = new THREE.DirectionalLight(0xffffff, 1.2);
  sun.position.set(-5000, 8000, 4000);
  scene.add(sun);

  const pinObjects = pins.map((pin) => {
    const el = document.createElement("div");
    el.className = "pin";
    el.innerHTML = `<div class="pin-dot"></div><div class="pin-text">${pin.name}</div>`;
    const obj = new CSS2DObject(el);
    obj.position.set(pin.x, pin.elev * EXAGGERATION_DEFAULT, -pin.y);
    scene.add(obj);
    return { obj, elev: pin.elev };
  });

  const hrrrOpacitySlider = document.getElementById("opacity-hrrr");
  const imageryToggle = document.getElementById("toggle-imagery");

  // DEM is locked on at full opacity for now - no HUD controls for it
  let demMesh = buildDemMesh(dem, EXAGGERATION_DEFAULT, 1, imageryToggle.checked ? imageryTexture : null);
  let hrrrMesh = buildHrrrMesh(hrrr, EXAGGERATION_DEFAULT, parseFloat(hrrrOpacitySlider.value));
  let hrrrEdges = buildHrrrEdges(hrrr, EXAGGERATION_DEFAULT);
  let hrrrLabels = buildHrrrLabels(hrrr, EXAGGERATION_DEFAULT);
  let { group: hwyGroup, labels: hwyLabels } = buildHighways(highways, EXAGGERATION_DEFAULT);
  scene.add(demMesh, hrrrMesh, hrrrEdges, hwyGroup, ...hrrrLabels, ...hwyLabels);

  document.getElementById("toggle-hrrr").addEventListener("change", (e) => {
    hrrrMesh.visible = e.target.checked;
    hrrrEdges.visible = e.target.checked;
    for (const label of hrrrLabels) label.visible = e.target.checked;
  });
  hrrrOpacitySlider.addEventListener("input", (e) => {
    hrrrMesh.material.opacity = parseFloat(e.target.value);
  });
  document.getElementById("toggle-highways").addEventListener("change", (e) => {
    hwyGroup.visible = e.target.checked;
    for (const label of hwyLabels) label.visible = e.target.checked;
  });
  imageryToggle.addEventListener("change", (e) => {
    demMesh.material.map = e.target.checked ? imageryTexture : null;
    demMesh.material.color.set(e.target.checked ? 0xffffff : 0x8fb8d8);
    demMesh.material.needsUpdate = true;
  });
  const exaggerationValue = document.getElementById("exaggeration-value");
  document.getElementById("exaggeration").addEventListener("input", (e) => {
    const exaggeration = parseFloat(e.target.value);
    exaggerationValue.textContent = `${exaggeration}x`;
    const hrrrVisible = hrrrMesh.visible;
    const hwyVisible = hwyGroup.visible;
    scene.remove(demMesh, hrrrMesh, hrrrEdges, hwyGroup, ...hrrrLabels, ...hwyLabels);
    demMesh.geometry.dispose();
    hrrrMesh.geometry.dispose();
    hrrrEdges.geometry.dispose();
    for (const line of hwyGroup.children) line.geometry.dispose();
    demMesh = buildDemMesh(dem, exaggeration, 1, imageryToggle.checked ? imageryTexture : null);
    hrrrMesh = buildHrrrMesh(hrrr, exaggeration, parseFloat(hrrrOpacitySlider.value));
    hrrrEdges = buildHrrrEdges(hrrr, exaggeration);
    hrrrLabels = buildHrrrLabels(hrrr, exaggeration);
    ({ group: hwyGroup, labels: hwyLabels } = buildHighways(highways, exaggeration));
    hrrrMesh.visible = hrrrVisible;
    hrrrEdges.visible = hrrrVisible;
    for (const label of hrrrLabels) label.visible = hrrrVisible;
    hwyGroup.visible = hwyVisible;
    for (const label of hwyLabels) label.visible = hwyVisible;
    scene.add(demMesh, hrrrMesh, hrrrEdges, hwyGroup, ...hrrrLabels, ...hwyLabels);
    for (const { obj, elev } of pinObjects) {
      obj.position.y = elev * exaggeration;
    }
  });

  window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    labelRenderer.setSize(window.innerWidth, window.innerHeight);
  });

  const compass = document.getElementById("compass");
  renderer.setAnimationLoop(() => {
    controls.update();
    // north is -Z in our local frame (see buildDemMesh/buildHrrrMesh); the compass
    // tracks the camera's azimuth around the orbit target so it always points true north
    const azimuthDeg = THREE.MathUtils.radToDeg(
      Math.atan2(camera.position.x - controls.target.x, camera.position.z - controls.target.z),
    );
    compass.style.transform = `rotate(${azimuthDeg}deg)`;
    renderer.render(scene, camera);
    labelRenderer.render(scene, camera);
  });
}

main();
