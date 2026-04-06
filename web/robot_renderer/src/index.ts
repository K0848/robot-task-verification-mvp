import * as THREE from 'three';
import {
  type FramePayload,
  type RendererPayload,
  clamp,
  computeAnimationTime,
  findFailureOffset,
  normalizeDynamicProfile,
  resolveObjectKind,
  sampleFrame
} from './payload';

type Vec3 = { x: number; y: number; z: number };

type SampledState = {
  timeMs: number;
  progress: number;
  stage: string;
  frame: FramePayload;
  objectFrame: FramePayload;
  highlightMode: string;
  failureOffset: number | null;
};

const STYLE_ID = 'robot-renderer-style';
const STYLES = `
.robot-render-shell {
  position: relative;
  width: 100%;
  height: 100%;
  border-radius: 20px;
  overflow: hidden;
  background: radial-gradient(circle at top left, rgba(123, 199, 255, 0.16), transparent 28%), linear-gradient(180deg, #0d1420 0%, #111927 100%);
  border: 1px solid rgba(255,255,255,0.08);
}
.robot-render-canvas {
  width: 100%;
  height: 100%;
}
.robot-render-overlay {
  position: absolute;
  left: 16px;
  top: 14px;
  right: 16px;
  pointer-events: none;
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.robot-render-kicker {
  color: #ffcf99;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.robot-render-title {
  color: #eef2ff;
  font-size: 18px;
  font-weight: 700;
  margin-top: 4px;
}
.robot-render-copy {
  color: #93a1bd;
  font-size: 12px;
  margin-top: 6px;
  line-height: 1.5;
}
.robot-render-badge {
  position: absolute;
  right: 16px;
  bottom: 14px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(12, 18, 30, 0.74);
  border: 1px solid rgba(255,255,255,0.08);
  color: #eef2ff;
  font: 12px/1.4 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
`;

function ensureStyles(): void {
  if (document.getElementById(STYLE_ID)) {
    return;
  }
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = STYLES;
  document.head.appendChild(style);
}

function binPosition(sourceBin: string): Vec3 {
  const positions: Record<string, Vec3> = {
    A1: { x: -3.2, y: 0.6, z: 1.8 },
    A2: { x: -2.6, y: 0.6, z: 1.15 },
    B1: { x: -3.2, y: 0.6, z: 0.45 },
    B2: { x: -2.6, y: 0.6, z: -0.2 },
    C1: { x: -3.2, y: 0.6, z: -0.9 }
  };
  return positions[sourceBin] ?? positions.A1;
}

function slotPosition(targetSlot: string): Vec3 {
  const positions: Record<string, Vec3> = {
    'Tray-01': { x: 3.1, y: 0.62, z: -1.4 },
    'Tray-02': { x: 3.1, y: 0.62, z: -0.5 },
    'Tray-03': { x: 3.1, y: 0.62, z: 0.4 }
  };
  return positions[targetSlot] ?? positions['Tray-01'];
}

function toWorldPosition(pose: { x: number; y: number; z: number }): Vec3 {
  return {
    x: (pose.x - 48) / 13,
    y: 0.92 + pose.z / 18,
    z: (pose.y - 62) / 13
  };
}

function withLiftArc(position: Vec3, stage: string, progress: number): Vec3 {
  const boosted = /接近|转运|抬升|回撤/.test(stage);
  const arc = boosted ? Math.sin(progress * Math.PI) * 0.42 : 0;
  return { ...position, y: position.y + arc };
}

function failureShake(state: SampledState, elapsedSinceMount: number): Vec3 {
  if (state.failureOffset === null || state.timeMs < state.failureOffset) {
    return { x: 0, y: 0, z: 0 };
  }
  const decay = Math.max(0.15, 1 - (state.timeMs - state.failureOffset) / 900);
  const pulse = elapsedSinceMount / 60;
  return {
    x: Math.sin(pulse * 1.7) * 0.05 * decay,
    y: Math.cos(pulse * 2.3) * 0.02 * decay,
    z: Math.cos(pulse * 1.2) * 0.04 * decay
  };
}

function sampledState(payload: RendererPayload, elapsedSinceMount: number): SampledState | null {
  const timeMs = computeAnimationTime(payload, elapsedSinceMount);
  const frame = sampleFrame(payload.frames, timeMs);
  if (!frame) {
    return null;
  }
  const profile = normalizeDynamicProfile(payload.dynamic_profile);
  const lagMs = frame.target_state.held ? Math.round(110 / profile.pace_multiplier) : 0;
  const objectFrame = sampleFrame(payload.frames, Math.max(0, timeMs - lagMs)) ?? frame;
  return {
    timeMs,
    progress: payload.animation.duration_ms ? clamp(timeMs / payload.animation.duration_ms, 0, 1) : 0,
    stage: frame.stage,
    frame,
    objectFrame,
    highlightMode: payload.highlight_mode,
    failureOffset: findFailureOffset(payload.events)
  };
}

function setCylinderBetween(mesh: THREE.Mesh, start: THREE.Vector3, end: THREE.Vector3): void {
  const center = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5);
  const direction = new THREE.Vector3().subVectors(end, start);
  const length = Math.max(direction.length(), 0.001);
  mesh.position.copy(center);
  mesh.scale.set(1, length, 1);
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
}

function buildObjectMesh(objectLabel: string): THREE.Mesh {
  const kind = resolveObjectKind(objectLabel);
  if (kind === 'ring') {
    return new THREE.Mesh(
      new THREE.TorusGeometry(0.22, 0.08, 14, 24),
      new THREE.MeshStandardMaterial({ color: '#ffb84d', metalness: 0.35, roughness: 0.5 })
    );
  }
  if (kind === 'disc') {
    return new THREE.Mesh(
      new THREE.CylinderGeometry(0.28, 0.28, 0.18, 24),
      new THREE.MeshStandardMaterial({ color: '#7bc7ff', metalness: 0.25, roughness: 0.56 })
    );
  }
  return new THREE.Mesh(
    new THREE.BoxGeometry(0.42, 0.28, 0.42),
    new THREE.MeshStandardMaterial({ color: '#96e0c7', metalness: 0.2, roughness: 0.6 })
  );
}

class SceneController {
  private readonly root: HTMLElement;
  private readonly payload: RendererPayload;
  private readonly shell: HTMLDivElement;
  private readonly canvasHost: HTMLDivElement;
  private readonly titleEl: HTMLDivElement;
  private readonly copyEl: HTMLDivElement;
  private readonly badgeEl: HTMLDivElement;
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene: THREE.Scene;
  private readonly camera: THREE.PerspectiveCamera;
  private readonly baseMesh: THREE.Mesh;
  private readonly shoulderMesh: THREE.Mesh;
  private readonly elbowMesh: THREE.Mesh;
  private readonly wristMesh: THREE.Mesh;
  private readonly upperArmMesh: THREE.Mesh;
  private readonly foreArmMesh: THREE.Mesh;
  private readonly leftFingerMesh: THREE.Mesh;
  private readonly rightFingerMesh: THREE.Mesh;
  private readonly sourceBinMesh: THREE.Mesh;
  private readonly trayMesh: THREE.Mesh;
  private readonly spotLight: THREE.DirectionalLight;
  private objectMesh: THREE.Mesh;
  private frameId = 0;
  private mountTime = performance.now();
  private resizeObserver: ResizeObserver | null = null;

  constructor(root: HTMLElement, payload: RendererPayload) {
    this.root = root;
    this.payload = payload;
    this.shell = document.createElement('div');
    this.shell.className = 'robot-render-shell';
    this.canvasHost = document.createElement('div');
    this.canvasHost.className = 'robot-render-canvas';
    const overlay = document.createElement('div');
    overlay.className = 'robot-render-overlay';
    overlay.innerHTML = `<div class="robot-render-kicker">${payload.view_mode}</div>`;
    this.titleEl = document.createElement('div');
    this.titleEl.className = 'robot-render-title';
    overlay.appendChild(this.titleEl);
    this.copyEl = document.createElement('div');
    this.copyEl.className = 'robot-render-copy';
    overlay.appendChild(this.copyEl);
    this.badgeEl = document.createElement('div');
    this.badgeEl.className = 'robot-render-badge';

    this.shell.appendChild(this.canvasHost);
    this.shell.appendChild(overlay);
    this.shell.appendChild(this.badgeEl);
    this.root.innerHTML = '';
    this.root.appendChild(this.shell);

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color('#0c1420');
    this.scene.fog = new THREE.Fog('#0c1420', 9, 18);

    this.camera = new THREE.PerspectiveCamera(34, 1, 0.1, 60);
    this.camera.position.set(7.2, 5.7, 8.3);
    this.camera.lookAt(0.2, 1.4, 0);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.canvasHost.appendChild(this.renderer.domElement);

    this.scene.add(new THREE.AmbientLight('#8ea4bf', 1.4));
    this.spotLight = new THREE.DirectionalLight('#d9e6ff', 2.4);
    this.spotLight.position.set(5.5, 8.5, 4.2);
    this.spotLight.castShadow = true;
    this.spotLight.shadow.mapSize.set(1024, 1024);
    this.scene.add(this.spotLight);

    const grid = new THREE.GridHelper(10, 20, '#2f4f73', '#1c2e45');
    grid.position.y = 0.02;
    this.scene.add(grid);

    const floor = new THREE.Mesh(
      new THREE.BoxGeometry(10, 0.12, 6),
      new THREE.MeshStandardMaterial({ color: '#1a2434', metalness: 0.05, roughness: 0.95 })
    );
    floor.receiveShadow = true;
    floor.position.set(0, -0.02, 0);
    this.scene.add(floor);

    const table = new THREE.Mesh(
      new THREE.BoxGeometry(8.8, 0.38, 5.1),
      new THREE.MeshStandardMaterial({ color: '#2b3647', metalness: 0.1, roughness: 0.8 })
    );
    table.position.set(0.2, 0.34, 0);
    table.receiveShadow = true;
    this.scene.add(table);

    this.sourceBinMesh = new THREE.Mesh(
      new THREE.BoxGeometry(0.8, 0.32, 0.8),
      new THREE.MeshStandardMaterial({ color: '#33506f', metalness: 0.1, roughness: 0.68 })
    );
    this.sourceBinMesh.castShadow = true;
    this.sourceBinMesh.receiveShadow = true;
    this.scene.add(this.sourceBinMesh);

    this.trayMesh = new THREE.Mesh(
      new THREE.BoxGeometry(1.2, 0.16, 1.0),
      new THREE.MeshStandardMaterial({ color: '#544c61', metalness: 0.18, roughness: 0.63 })
    );
    this.trayMesh.castShadow = true;
    this.trayMesh.receiveShadow = true;
    this.scene.add(this.trayMesh);

    this.baseMesh = new THREE.Mesh(
      new THREE.CylinderGeometry(0.4, 0.5, 0.75, 24),
      new THREE.MeshStandardMaterial({ color: '#8397ac', metalness: 0.55, roughness: 0.38 })
    );
    this.baseMesh.castShadow = true;
    this.baseMesh.position.set(-3.55, 0.78, 1.85);
    this.scene.add(this.baseMesh);

    this.shoulderMesh = new THREE.Mesh(
      new THREE.SphereGeometry(0.18, 20, 20),
      new THREE.MeshStandardMaterial({ color: '#e7edf8', metalness: 0.4, roughness: 0.28 })
    );
    this.shoulderMesh.castShadow = true;
    this.scene.add(this.shoulderMesh);

    const segmentGeometry = new THREE.CylinderGeometry(0.1, 0.12, 1, 18);
    const segmentMaterial = new THREE.MeshStandardMaterial({ color: '#d4dbe8', metalness: 0.35, roughness: 0.34 });
    this.upperArmMesh = new THREE.Mesh(segmentGeometry, segmentMaterial);
    this.upperArmMesh.castShadow = true;
    this.scene.add(this.upperArmMesh);
    this.foreArmMesh = new THREE.Mesh(segmentGeometry, segmentMaterial.clone());
    this.foreArmMesh.castShadow = true;
    this.scene.add(this.foreArmMesh);

    this.elbowMesh = new THREE.Mesh(
      new THREE.SphereGeometry(0.14, 18, 18),
      new THREE.MeshStandardMaterial({ color: '#9ab1c9', metalness: 0.32, roughness: 0.36 })
    );
    this.elbowMesh.castShadow = true;
    this.scene.add(this.elbowMesh);

    this.wristMesh = new THREE.Mesh(
      new THREE.BoxGeometry(0.24, 0.18, 0.24),
      new THREE.MeshStandardMaterial({ color: '#7bc7ff', metalness: 0.3, roughness: 0.32 })
    );
    this.wristMesh.castShadow = true;
    this.scene.add(this.wristMesh);

    const fingerGeometry = new THREE.BoxGeometry(0.08, 0.24, 0.08);
    const fingerMaterial = new THREE.MeshStandardMaterial({ color: '#ffb84d', metalness: 0.18, roughness: 0.42 });
    this.leftFingerMesh = new THREE.Mesh(fingerGeometry, fingerMaterial);
    this.leftFingerMesh.castShadow = true;
    this.scene.add(this.leftFingerMesh);
    this.rightFingerMesh = new THREE.Mesh(fingerGeometry, fingerMaterial.clone());
    this.rightFingerMesh.castShadow = true;
    this.scene.add(this.rightFingerMesh);

    this.objectMesh = buildObjectMesh(payload.scene.object_label);
    this.objectMesh.castShadow = true;
    this.objectMesh.receiveShadow = true;
    this.scene.add(this.objectMesh);

    this.resize();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(this.root);
    this.frameId = window.requestAnimationFrame((ts) => this.renderFrame(ts));
  }

  private resize(): void {
    const width = Math.max(this.root.clientWidth, 280);
    const height = Math.max(this.root.clientHeight, 280);
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }

  private renderFrame(timestamp: number): void {
    const elapsedSinceMount = timestamp - this.mountTime;
    const state = sampledState(this.payload, elapsedSinceMount);
    if (state) {
      this.applyState(state, elapsedSinceMount);
      this.renderer.render(this.scene, this.camera);
    }
    this.frameId = window.requestAnimationFrame((ts) => this.renderFrame(ts));
  }

  private applyState(state: SampledState, elapsedSinceMount: number): void {
    const profile = normalizeDynamicProfile(this.payload.dynamic_profile);
    const baseTop = new THREE.Vector3(-3.55, 1.18, 1.85);
    const currentArm = withLiftArc(toWorldPosition(state.frame.arm_pose), state.stage, state.progress);
    const shake = failureShake(state, elapsedSinceMount);
    const endEffector = new THREE.Vector3(currentArm.x + shake.x, currentArm.y + shake.y, currentArm.z + shake.z);
    const elbow = new THREE.Vector3(
      THREE.MathUtils.lerp(baseTop.x, endEffector.x, 0.45),
      Math.max(baseTop.y, endEffector.y) + 0.8,
      THREE.MathUtils.lerp(baseTop.z, endEffector.z, 0.45) + 0.18
    );

    this.shoulderMesh.position.copy(baseTop);
    this.elbowMesh.position.copy(elbow);
    this.wristMesh.position.copy(endEffector);
    setCylinderBetween(this.upperArmMesh, baseTop, elbow);
    setCylinderBetween(this.foreArmMesh, elbow, endEffector);

    const fingerGap = state.frame.gripper_state === 'open' ? 0.18 : 0.08;
    this.leftFingerMesh.position.set(endEffector.x - fingerGap, endEffector.y - 0.14, endEffector.z);
    this.rightFingerMesh.position.set(endEffector.x + fingerGap, endEffector.y - 0.14, endEffector.z);

    const sourcePosition = binPosition(this.payload.scene.source_bin);
    this.sourceBinMesh.position.set(sourcePosition.x, sourcePosition.y, sourcePosition.z);
    const trayPosition = slotPosition(this.payload.scene.target_slot);
    this.trayMesh.position.set(trayPosition.x, trayPosition.y, trayPosition.z);

    const desiredKind = resolveObjectKind(this.payload.scene.object_label);
    const currentKind = resolveObjectKind(this.objectMesh.userData.kind ?? '');
    if (desiredKind !== currentKind) {
      this.scene.remove(this.objectMesh);
      this.objectMesh.geometry.dispose();
      (this.objectMesh.material as THREE.Material).dispose();
      this.objectMesh = buildObjectMesh(this.payload.scene.object_label);
      this.objectMesh.userData.kind = desiredKind;
      this.objectMesh.castShadow = true;
      this.objectMesh.receiveShadow = true;
      this.scene.add(this.objectMesh);
    } else {
      this.objectMesh.userData.kind = desiredKind;
    }

    const objectPoseSource = state.objectFrame.target_state.held ? state.frame.target_state : state.objectFrame.target_state;
    const objectWorld = state.objectFrame.target_state.held
      ? new THREE.Vector3(endEffector.x, endEffector.y - 0.28, endEffector.z)
      : new THREE.Vector3(...Object.values(toWorldPosition({ x: objectPoseSource.object_x, y: objectPoseSource.object_y, z: objectPoseSource.placed ? 4 : 2 })) as [number, number, number]);
    if (state.objectFrame.target_state.placed) {
      const settle = Math.exp(-state.progress * 6) * Math.sin(state.timeMs / 90) * 0.04;
      objectWorld.y = 1.02 + settle;
    }
    if (!this.payload.success && state.failureOffset !== null && state.timeMs >= state.failureOffset) {
      objectWorld.x += shake.x * 1.3;
      objectWorld.z += shake.z * 1.3;
    }
    this.objectMesh.position.copy(objectWorld);
    this.objectMesh.rotation.set(0.18, state.objectFrame.target_state.held ? state.timeMs / 600 : 0, 0);

    const objectMaterial = this.objectMesh.material as THREE.MeshStandardMaterial;
    const gripperMaterial = this.wristMesh.material as THREE.MeshStandardMaterial;
    const fingerLeftMaterial = this.leftFingerMesh.material as THREE.MeshStandardMaterial;
    const fingerRightMaterial = this.rightFingerMesh.material as THREE.MeshStandardMaterial;
    objectMaterial.emissive.set(this.payload.highlight_mode === 'place' || this.payload.highlight_mode === 'failure' ? '#5d3300' : '#000000');
    gripperMaterial.emissive.set(this.payload.highlight_mode === 'grasp' ? '#27496a' : '#000000');
    fingerLeftMaterial.emissive.set(this.payload.highlight_mode === 'grasp' ? '#563200' : '#000000');
    fingerRightMaterial.emissive.set(this.payload.highlight_mode === 'grasp' ? '#563200' : '#000000');
    this.spotLight.color.set(!this.payload.success && this.payload.highlight_mode === 'failure' ? '#ffb5c1' : '#d9e6ff');

    const focusTarget = this.payload.highlight_mode === 'place'
      ? new THREE.Vector3(trayPosition.x, 1.15, trayPosition.z)
      : this.payload.highlight_mode === 'grasp'
        ? endEffector.clone()
        : this.payload.highlight_mode === 'failure' && !this.payload.success
          ? objectWorld.clone()
          : new THREE.Vector3(0.4, 1.25, 0);
    const cameraOffset = this.payload.highlight_mode === 'place'
      ? new THREE.Vector3(6.3, 5.2, 6.5)
      : this.payload.highlight_mode === 'grasp'
        ? new THREE.Vector3(5.2, 4.9, 5.8)
        : this.payload.highlight_mode === 'failure'
          ? new THREE.Vector3(4.8, 4.7, 6.2)
          : new THREE.Vector3(7.2, 5.7, 8.3);
    const desiredCameraPos = focusTarget.clone().add(cameraOffset);
    this.camera.position.lerp(desiredCameraPos, 0.06);
    this.camera.lookAt(focusTarget);

    const paceLabel = profile.pace === 'fast' ? '快节奏' : profile.pace === 'slow' ? '慢速讲解' : '默认节奏';
    const compareLabel = this.payload.compare_label ? `${this.payload.compare_label} · ` : '';
    this.titleEl.textContent = `${compareLabel}${this.payload.title} · ${state.stage}`;
    this.copyEl.textContent = `${this.payload.scenario_label} · ${paceLabel} · ${this.payload.scene.object_label} -> ${this.payload.scene.target_slot}`;
    this.badgeEl.textContent = `${Math.round(state.progress * 100)}% · ${this.payload.status}`;
  }

  destroy(): void {
    if (this.frameId) {
      window.cancelAnimationFrame(this.frameId);
    }
    this.resizeObserver?.disconnect();
    this.renderer.dispose();
  }
}

declare global {
  interface Window {
    RobotRenderer?: {
      render: (root: HTMLElement, payload: RendererPayload) => void;
    };
  }
}

function render(root: HTMLElement, payload: RendererPayload): void {
  ensureStyles();
  const previous = (root as HTMLElement & { __controller?: SceneController }).__controller;
  previous?.destroy();
  const controller = new SceneController(root, payload);
  (root as HTMLElement & { __controller?: SceneController }).__controller = controller;
}

window.RobotRenderer = { render };

