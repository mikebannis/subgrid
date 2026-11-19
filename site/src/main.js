import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

const EXAGGERATION_DEFAULT = 1.5;

async function loadGrid(url) {
  const res = await fetch(url);
  return res.json();
}

// grid.x/grid.y are 1D axes (flat-earth local-meters approx), grid.elev is [row][col]
function buildDemMesh(grid, exaggeration, opacity) {
  const { width, height, x, y, elev } = grid;
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(width * height * 3);

  for (let r = 0; r < height; r++) {
    for (let c = 0; c < width; c++) {
      const i = (r * width + c) * 3;
      positions[i] = x[c];
      positions[i + 1] = elev[r][c] * exaggeration;
      positions[i + 2] = -y[r];
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
  geometry.setIndex(indices);
  geometry.computeVertexNormals();

  const material = new THREE.MeshStandardMaterial({
    color: 0x8fb8d8,
    transparent: true,
    opacity,
    side: THREE.DoubleSide,
    roughness: 0.8,
  });

  return new THREE.Mesh(geometry, material);
}

// one box per model grid cell - the native blocky resolution of HRRR/RRFS terrain
function buildHrrrMesh(grid, exaggeration, opacity) {
  const { width, height, x, y, elev, cellSizeX, cellSizeY } = grid;
  const geometry = new THREE.BoxGeometry(cellSizeX * 0.96, 1, cellSizeY * 0.96);
  const material = new THREE.MeshStandardMaterial({
    color: 0xd98a3d,
    roughness: 0.9,
    transparent: true,
    opacity,
  });
  const mesh = new THREE.InstancedMesh(geometry, material, width * height);

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

async function main() {
  const [hrrr, dem] = await Promise.all([
    loadGrid("/data/hrrr.json"),
    loadGrid("/data/dem.json"),
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
  camera.position.set(8000, 6000, 10000);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(window.innerWidth, window.innerHeight);
  app.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 500, 0);
  controls.update();

  scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  const sun = new THREE.DirectionalLight(0xffffff, 1.2);
  sun.position.set(-5000, 8000, 4000);
  scene.add(sun);

  const hrrrOpacitySlider = document.getElementById("opacity-hrrr");
  const demOpacitySlider = document.getElementById("opacity-dem");

  let demMesh = buildDemMesh(dem, EXAGGERATION_DEFAULT, parseFloat(demOpacitySlider.value));
  let hrrrMesh = buildHrrrMesh(hrrr, EXAGGERATION_DEFAULT, parseFloat(hrrrOpacitySlider.value));
  scene.add(demMesh, hrrrMesh);

  document.getElementById("toggle-hrrr").addEventListener("change", (e) => {
    hrrrMesh.visible = e.target.checked;
  });
  document.getElementById("toggle-dem").addEventListener("change", (e) => {
    demMesh.visible = e.target.checked;
  });
  hrrrOpacitySlider.addEventListener("input", (e) => {
    hrrrMesh.material.opacity = parseFloat(e.target.value);
  });
  demOpacitySlider.addEventListener("input", (e) => {
    demMesh.material.opacity = parseFloat(e.target.value);
  });
  document.getElementById("exaggeration").addEventListener("input", (e) => {
    const exaggeration = parseFloat(e.target.value);
    const demVisible = demMesh.visible;
    const hrrrVisible = hrrrMesh.visible;
    scene.remove(demMesh, hrrrMesh);
    demMesh.geometry.dispose();
    hrrrMesh.geometry.dispose();
    demMesh = buildDemMesh(dem, exaggeration, parseFloat(demOpacitySlider.value));
    hrrrMesh = buildHrrrMesh(hrrr, exaggeration, parseFloat(hrrrOpacitySlider.value));
    demMesh.visible = demVisible;
    hrrrMesh.visible = hrrrVisible;
    scene.add(demMesh, hrrrMesh);
  });

  window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  renderer.setAnimationLoop(() => {
    controls.update();
    renderer.render(scene, camera);
  });
}

main();
