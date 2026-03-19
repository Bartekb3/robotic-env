/**
 * Robotic Environment — Three.js viewer
 *
 * Connects to the FastAPI backend via WebSocket, renders the world in real
 * time, and handles camera-frame rendering requests from the /camera endpoint.
 *
 * Coordinate mapping
 * ------------------
 *   sim (x, y)  →  Three.js (x, 0, y)    (Y-up world, flat XZ plane)
 *   sim rotation 0 = north (+Z in Three.js), clockwise
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// =========================================================================== //
//  Renderer & scene                                                            //
// =========================================================================== //

const container = document.getElementById('canvas-container');

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
container.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x87ceeb);
scene.fog = new THREE.Fog(0x87ceeb, 40, 80);

// =========================================================================== //
//  Viewer cameras                                                              //
// =========================================================================== //

const aspect = () => window.innerWidth / window.innerHeight;

// Perspective (angled) camera
const perspCam = new THREE.PerspectiveCamera(55, aspect(), 0.1, 200);
perspCam.position.set(0, 18, 18);
perspCam.lookAt(0, 0, 0);

// Orthographic (top-down) camera — sized on first world state
const orthoCam = new THREE.OrthographicCamera(-10, 10, 10, -10, 0.1, 200);
orthoCam.position.set(0, 50, 0);
orthoCam.lookAt(0, 0, 0);

// OrbitControls only active in angled mode
const controls = new OrbitControls(perspCam, renderer.domElement);
controls.target.set(0, 0, 0);
controls.maxPolarAngle = Math.PI / 2.1;
controls.enabled = false;

let viewMode = 'topdown'; // 'topdown' | 'angled'
const activeCamera = () => viewMode === 'topdown' ? orthoCam : perspCam;

// =========================================================================== //
//  Robot's on-board camera (offscreen)                                        //
// =========================================================================== //

const robotCam = new THREE.PerspectiveCamera(60, 4 / 3, 0.1, 100);
const robotRT = new THREE.WebGLRenderTarget(640, 480);

// =========================================================================== //
//  Lighting                                                                    //
// =========================================================================== //

scene.add(new THREE.AmbientLight(0xffffff, 0.55));

const sun = new THREE.DirectionalLight(0xffffff, 0.9);
sun.position.set(8, 20, 8);
sun.castShadow = true;
sun.shadow.mapSize.set(1024, 1024);
sun.shadow.camera.near = 0.5;
sun.shadow.camera.far = 60;
sun.shadow.camera.left = -15;
sun.shadow.camera.right = 15;
sun.shadow.camera.top = 15;
sun.shadow.camera.bottom = -15;
scene.add(sun);

scene.add(new THREE.HemisphereLight(0x87ceeb, 0x4a7c59, 0.3));

// =========================================================================== //
//  Ground                                                                      //
// =========================================================================== //

const groundGroup = new THREE.Group();
scene.add(groundGroup);
let currentWorldSize = null;

function buildGround(sizeX, sizeY, bgColor) {
  // Remove previous ground geometry
  while (groundGroup.children.length) {
    groundGroup.remove(groundGroup.children[0]);
  }

  scene.background = new THREE.Color(bgColor);
  scene.fog.color = new THREE.Color(bgColor);

  // Floor
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(sizeX, sizeY),
    new THREE.MeshLambertMaterial({ color: 0x5a9e47 })
  );
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  groundGroup.add(floor);

  // Grid
  const gridSize = Math.max(sizeX, sizeY);
  const grid = new THREE.GridHelper(gridSize, gridSize, 0x000000, 0x2a4a2a);
  grid.material.opacity = 0.25;
  grid.material.transparent = true;
  groundGroup.add(grid);

  // World boundary outline
  const edgeGeo = new THREE.EdgesGeometry(new THREE.BoxGeometry(sizeX, 0.02, sizeY));
  const edgeMat = new THREE.LineBasicMaterial({ color: 0xffffff, opacity: 0.35, transparent: true });
  groundGroup.add(new THREE.LineSegments(edgeGeo, edgeMat));

  // Update cameras for new world size
  positionViewerCameras(sizeX, sizeY);
}

function positionViewerCameras(sizeX, sizeY) {
  const maxS = Math.max(sizeX, sizeY);

  // Perspective: angled view
  perspCam.position.set(0, maxS * 0.9, maxS * 0.9);
  perspCam.lookAt(0, 0, 0);
  controls.target.set(0, 0, 0);
  controls.update();

  // Ortho: top-down, fits the world with a small margin
  const half = maxS / 2 * 1.15;
  const a = aspect();
  orthoCam.left   = -half * a;
  orthoCam.right  =  half * a;
  orthoCam.top    =  half;
  orthoCam.bottom = -half;
  orthoCam.position.set(0, 50, 0);
  orthoCam.up.set(0, 0, -1);  // prevents degenerate lookAt; puts sim-north (+y → -Z) at top of screen
  orthoCam.lookAt(0, 0, 0);
  orthoCam.updateProjectionMatrix();
}

// =========================================================================== //
//  Object mesh factories                                                       //
// =========================================================================== //

function makeRobotMesh() {
  const g = new THREE.Group();

  // Body — blue disc
  const body = new THREE.Mesh(
    new THREE.CylinderGeometry(0.38, 0.38, 0.22, 24),
    new THREE.MeshLambertMaterial({ color: 0x1565c0 })
  );
  body.position.y = 0.11;
  body.castShadow = true;
  g.add(body);

  // Direction arrow — yellow cone pointing +Z (forward)
  const arrow = new THREE.Mesh(
    new THREE.ConeGeometry(0.11, 0.32, 8),
    new THREE.MeshLambertMaterial({ color: 0xfdd835 })
  );
  arrow.position.set(0, 0.24, 0.32);
  arrow.rotation.x = Math.PI / 2;
  arrow.castShadow = true;
  g.add(arrow);

  // Camera body — dark box on top-front
  const camBody = new THREE.Mesh(
    new THREE.BoxGeometry(0.17, 0.09, 0.11),
    new THREE.MeshLambertMaterial({ color: 0x212121 })
  );
  camBody.position.set(0, 0.28, 0.18);
  g.add(camBody);

  // Camera lens — small cyan cylinder
  const lens = new THREE.Mesh(
    new THREE.CylinderGeometry(0.035, 0.035, 0.055, 8),
    new THREE.MeshLambertMaterial({ color: 0x29b6f6 })
  );
  lens.position.set(0, 0.28, 0.245);
  lens.rotation.x = Math.PI / 2;
  g.add(lens);

  return g;
}

function makeWallMesh(obj) {
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(obj.width, 1.2, obj.height),
    new THREE.MeshLambertMaterial({ color: new THREE.Color(obj.color) })
  );
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  return mesh;
}

function makeBallMesh(obj) {
  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(obj.radius ?? 0.3, 20, 20),
    new THREE.MeshLambertMaterial({ color: new THREE.Color(obj.color) })
  );
  mesh.castShadow = true;
  return mesh;
}

// Map type string → factory function.  Add entries here for new object types.
const MESH_FACTORY = {
  wall: makeWallMesh,
  ball: makeBallMesh,
};

// =========================================================================== //
//  Scene mesh registry                                                         //
// =========================================================================== //

const meshes = {}; // id → THREE.Object3D

function getOrCreateMesh(obj) {
  if (!meshes[obj.id]) {
    const factory = MESH_FACTORY[obj.type];
    if (!factory) return null;
    const mesh = factory(obj);
    meshes[obj.id] = mesh;
    scene.add(mesh);
  }
  return meshes[obj.id];
}

function removeStaleMeshes(seenIds) {
  for (const id of Object.keys(meshes)) {
    if (!seenIds.has(id)) {
      scene.remove(meshes[id]);
      delete meshes[id];
    }
  }
}

// =========================================================================== //
//  State → scene update                                                        //
// =========================================================================== //

function applyState(state) {
  const { world, robot, objects } = state;

  // Rebuild ground when world size changes
  if (
    !currentWorldSize ||
    currentWorldSize.x !== world.size_x ||
    currentWorldSize.y !== world.size_y
  ) {
    buildGround(world.size_x, world.size_y, world.background_color);
    currentWorldSize = { x: world.size_x, y: world.size_y };
  }

  // ---- Robot ----
  if (!meshes['__robot__']) {
    meshes['__robot__'] = makeRobotMesh();
    scene.add(meshes['__robot__']);
  }
  const rm = meshes['__robot__'];
  rm.position.set(robot.x, 0.0, -robot.y);
  rm.rotation.y = Math.PI - THREE.MathUtils.degToRad(robot.rotation);

  // ---- World objects ----
  const seen = new Set(['__robot__']);

  for (const obj of objects) {
    seen.add(obj.id);
    const mesh = getOrCreateMesh(obj);
    if (!mesh) continue;

    if (obj.type === 'wall') {
      mesh.position.set(obj.x, 0.6, -obj.y);
    } else if (obj.type === 'ball') {
      const r = obj.radius ?? 0.3;
      // Lift ball slightly when grabbed so it visually floats above the robot
      const yOffset = obj.grabbed ? 0.5 : r;
      mesh.position.set(obj.x, yOffset, -obj.y);
    }
  }

  removeStaleMeshes(seen);

  // ---- Robot's on-board camera ----
  const rotRad = THREE.MathUtils.degToRad(robot.rotation);
  const fwdX = Math.sin(rotRad);
  const fwdZ = -Math.cos(rotRad);  // north = -Z in Three.js
  const camHeight = 0.32;
  const camOffset = 1.2;
  robotCam.position.set(robot.x + fwdX * camOffset, camHeight, -robot.y + fwdZ * camOffset);
  robotCam.lookAt(robot.x + fwdX * 10, camHeight, -robot.y + fwdZ * 10);
  robotCam.fov = robot.camera_fov ?? 60;
  robotCam.updateProjectionMatrix();

  // ---- HUD ----
  document.getElementById('h-pos').textContent =
    `(${robot.x.toFixed(2)}, ${robot.y.toFixed(2)})`;
  document.getElementById('h-rot').textContent =
    `${robot.rotation.toFixed(1)}°`;
  document.getElementById('h-held').textContent =
    robot.held_object ?? 'nothing';

  const statusEl = document.getElementById('h-status');
  if (robot.is_moving) {
    statusEl.textContent = 'Moving';
    statusEl.className = 'hud-value hud-moving';
  } else if (robot.is_rotating) {
    statusEl.textContent = 'Rotating';
    statusEl.className = 'hud-value hud-moving';
  } else {
    statusEl.textContent = 'Idle';
    statusEl.className = 'hud-value hud-idle';
  }
}

// =========================================================================== //
//  Robot camera rendering                                                      //
// =========================================================================== //

function renderRobotCamera() {
  const w = robotRT.width;
  const h = robotRT.height;

  renderer.setRenderTarget(robotRT);
  renderer.render(scene, robotCam);
  renderer.setRenderTarget(null);

  // Read pixels (WebGL is bottom-up → flip vertically)
  const pixels = new Uint8Array(w * h * 4);
  renderer.readRenderTargetPixels(robotRT, 0, 0, w, h, pixels);

  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  const imgData = ctx.createImageData(w, h);

  for (let row = 0; row < h; row++) {
    const srcRow = h - 1 - row;
    imgData.data.set(
      pixels.subarray(srcRow * w * 4, (srcRow + 1) * w * 4),
      row * w * 4
    );
  }
  ctx.putImageData(imgData, 0, 0);

  const base64 = canvas.toDataURL('image/png').split(',')[1];
  ws.send(JSON.stringify({ type: 'camera_frame', data: base64 }));
}

// =========================================================================== //
//  WebSocket — with auto-reconnect                                             //
// =========================================================================== //

let ws;

function connect() {
  ws = new WebSocket(`ws://${window.location.host}/ws`);

  ws.addEventListener('open', () => {
    const el = document.getElementById('status');
    el.textContent = 'Connected';
    el.className = 'connected';
  });

  ws.addEventListener('close', () => {
    const el = document.getElementById('status');
    el.textContent = 'Disconnected';
    el.className = 'disconnected';
    setTimeout(connect, 2000);
  });

  ws.addEventListener('message', (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === 'state') {
      applyState(msg.data);
    } else if (msg.type === 'camera_request') {
      renderRobotCamera();
    }
  });
}

connect();

// =========================================================================== //
//  UI controls                                                                 //
// =========================================================================== //

document.getElementById('btn-view').addEventListener('click', () => {
  viewMode = viewMode === 'topdown' ? 'angled' : 'topdown';
  controls.enabled = viewMode === 'angled';
  document.getElementById('btn-view').textContent =
    viewMode === 'topdown' ? 'Switch to Angled View' : 'Switch to Top-Down View';
});

window.addEventListener('resize', () => {
  renderer.setSize(window.innerWidth, window.innerHeight);
  perspCam.aspect = aspect();
  perspCam.updateProjectionMatrix();
  if (currentWorldSize) {
    positionViewerCameras(currentWorldSize.x, currentWorldSize.y);
  }
});

// =========================================================================== //
//  Animation loop                                                              //
// =========================================================================== //

function animate() {
  requestAnimationFrame(animate);
  if (viewMode === 'angled') controls.update();
  renderer.render(scene, activeCamera());
}

animate();
