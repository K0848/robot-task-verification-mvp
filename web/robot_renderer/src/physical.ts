import * as THREE from 'three';
import { type FramePayload, type RendererPayload, type RobotFramePayload } from './payload';
import { physicalProjection, physicalWorld, samplePhysicalFrame, sampleRobotFrame } from './physical-frame';
import { createRobotScene, type RobotDebugPose, type RobotSceneInstance } from './robot-scene';

const STAGES: Record<string, string> = {
  approach: '接近', grasp: '抓取', transport: '搬运', place: '放置', release: '释放',
  descend: '下降', lift: '抬升', retreat: '回撤', settle: '稳定'
};

const STYLE = `<style>
*{box-sizing:border-box}.physical{border:1px solid #40526c;border-radius:12px;padding:14px;background:#101827;color:#e7edf8;font:14px system-ui,sans-serif}.toolbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:8px 0}button,select{background:#22344d;color:#f3f6fc;border:1px solid #7e93b0;border-radius:6px;padding:8px;cursor:pointer}button:disabled{opacity:.45}.viewport{height:390px;position:relative;background:#0c1420;border-radius:8px;overflow:hidden}canvas,svg{width:100%;height:100%;display:block}.muted{color:#afbed4;font-size:12px;line-height:1.6}#seek{width:100%;accent-color:#57caff}#frame-values{font:12px monospace;white-space:pre-wrap;line-height:1.6;margin:8px 0}#fallback-notice{color:#ffcd83}output{font-variant-numeric:tabular-nums}
</style>`;

type Controls = {
  seek: HTMLInputElement;
  play: HTMLButtonElement;
  speed: HTMLSelectElement;
  clock: HTMLOutputElement;
  stage: HTMLSpanElement;
  values: HTMLDivElement;
};

function getControls(root: HTMLElement): Controls {
  const get = <T extends Element>(id: string) => root.querySelector<T>(`#${id}`)!;
  return {
    seek: get('seek'), play: get('play'), speed: get('speed'), clock: get('clock'),
    stage: get('stage'), values: get('frame-values')
  };
}

function stageLabel(stage: string): string {
  return STAGES[stage] ?? stage;
}

function formatPosition(position: readonly number[]): string {
  return position.map((value) => Number(value).toFixed(4)).join(', ');
}

function pandaMarkup(payload: RendererPayload): string {
  return `${STYLE}<section class="physical"><strong>运行回放</strong>
    <div class="muted">拖动时间轴定位动作；鼠标拖动旋转、滚轮缩放。</div>
    <div class="toolbar"><button id="play">播放</button><button id="restart">回到起点</button><button id="reset-camera">复位镜头</button>
      <label>倍速 <select id="speed" aria-label="回放倍速"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option></select></label>
      <output id="clock"></output><span id="stage"></span></div>
    <div id="fallback-notice" role="status"></div><div id="panda-three" class="viewport"><svg id="panda-svg" viewBox="0 0 800 560" aria-label="Panda SVG 简化标记"></svg></div>
    <input id="seek" aria-label="回放时间" type="range" min="0" step="1" value="0">
    <label>事件定位 <select id="panda-events" aria-label="事件定位"><option value="">选择事件跳转</option></select></label>
    <details class="technical"><summary>画面设置与逐帧数据</summary>
      <div class="toolbar"><label>显示方式 <select id="panda-view" aria-label="Panda回放渲染器"><option value="threejs">完整 3D</option><option value="svg">简化侧视图</option></select></label></div>
      <div id="frame-values"></div><div class="muted">运行 <span id="panda-run-id"></span> · 模型 <span id="panda-model-id"></span><br>几何姿态来自同一后端记录帧。简化视图不代表完整机器人几何。</div>
    </details>
  </section>`;
}

function drawPandaSvg(svg: SVGSVGElement, frame: RobotFramePayload): void {
  const marker = (position: readonly number[], yScale: number) => [400 + position[0] * 500, 500 - position[2] * yScale];
  const tool = marker(frame.tool_position ?? [0, 0, 0], 430);
  const object = marker(frame.object_position ?? [0, 0, 0], 430);
  const target = marker(frame.target_position ?? [0, 0, 0], 430);
  svg.innerHTML = `<rect x="20" y="20" width="760" height="500" fill="#0c1420"/><line x1="40" y1="500" x2="760" y2="500" stroke="#60738b"/>
    <text x="40" y="48" fill="#afbed4">Panda SVG 简化标记 · 完整几何请切回 Three.js</text>
    <circle data-entity="tool" cx="${tool[0]}" cy="${tool[1]}" r="13" fill="#58caff"/><text x="${tool[0] + 16}" y="${tool[1]}" fill="#58caff">工具</text>
    <rect data-entity="object" x="${object[0] - 14}" y="${object[1] - 14}" width="28" height="28" fill="#ffb449"/><text x="${object[0] + 18}" y="${object[1]}" fill="#ffb449">物体</text>
    <rect data-entity="target" x="${target[0] - 24}" y="${target[1] - 18}" width="48" height="36" fill="none" stroke="#55dfae" stroke-dasharray="4"/><text x="${target[0] + 28}" y="${target[1]}" fill="#55dfae">目标</text>
    <text x="40" y="540" fill="#afbed4">sample ${frame.sim_time_ms} ms · stage ${stageLabel(frame.stage)}</text>`;
}

function renderPanda(root: HTMLElement, payload: RendererPayload): void {
  root.innerHTML = pandaMarkup(payload);
  root.querySelector<HTMLElement>('#panda-run-id')!.textContent = payload.run_id ?? 'unknown run';
  root.querySelector<HTMLElement>('#panda-model-id')!.textContent = payload.model_id ?? 'unknown model';
  const controls = getControls(root);
  const viewport = root.querySelector<HTMLDivElement>('#panda-three')!;
  const svg = root.querySelector<SVGSVGElement>('#panda-svg')!;
  const view = root.querySelector<HTMLSelectElement>('#panda-view')!;
  const events = root.querySelector<HTMLSelectElement>('#panda-events')!;
  const frames = payload.robot_frames ?? [];
  if (!payload.robot_scene || !frames.length) {
    controls.play.disabled = true;
    controls.values.textContent = '缺少 Panda scene 或轨迹，不能显示完整几何。';
    return;
  }

  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#0c1420');
  const camera = new THREE.PerspectiveCamera(42, 1, .001, 20);
  camera.position.set(1.08, .86, 1.18);
  scene.add(new THREE.HemisphereLight(0xddeeff, 0x253040, 2.1));
  const light = new THREE.DirectionalLight(0xffffff, 2.2);
  light.position.set(1, 3, 2);
  scene.add(light);

  let renderer: THREE.WebGLRenderer | null = null;
  let robot: RobotSceneInstance | null = null;
  let cursor = 0;
  let selected: RobotFramePayload | null = null;
  let playing = false;
  let last = performance.now();
  let raf = 0;
  let disposed = false;

  const duration = frames[frames.length - 1].sim_time_ms;
  controls.seek.max = String(duration);

  const resetCamera = () => {
    camera.position.set(1.08, .86, 1.18);
    if (robot) {
      robot.controls.target.set(.45, .35, -.05);
      robot.controls.update();
    }
    if (renderer && view.value === 'threejs') renderer.render(scene, camera);
  };

  const showSvg = () => {
    const canvas = viewport.querySelector('canvas');
    if (canvas) canvas.hidden = true;
    svg.style.display = 'block';
  };

  const showThree = () => {
    svg.style.display = 'none';
    const canvas = viewport.querySelector('canvas');
    if (canvas) canvas.hidden = false;
    if (renderer) renderer.render(scene, camera);
  };

  const fallback = (reason: string) => {
    playing = false;
    controls.play.textContent = '播放';
    view.value = 'svg';
    view.options[0].disabled = true;
    root.querySelector('#fallback-notice')!.textContent = `3D 不可用，已回退 SVG：${reason}`;
    showSvg();
    paint();
  };

  const paint = () => {
    if (disposed) return;
    selected = sampleRobotFrame(frames, cursor);
    if (!selected) return;
    if (robot) robot.applyFrame(selected);
    drawPandaSvg(svg, selected);
    if (view.value === 'threejs') showThree(); else showSvg();
    controls.seek.value = String(cursor);
    controls.clock.textContent = `${(selected.sim_time_ms / 1000).toFixed(3)} / ${(duration / 1000).toFixed(3)} s`;
    controls.stage.textContent = `阶段：${stageLabel(selected.stage)}`;
    const width = selected.gripper_width_m === undefined ? '未知' : `${selected.gripper_width_m.toFixed(4)} m`;
    const objectPosition = selected.object_position ?? [0, 0, 0];
    controls.values.textContent = `夹爪开度 ${width}\n物体 [${formatPosition(objectPosition)}] m\n几何 ${selected.geom_poses.length} / ${payload.robot_scene!.geoms.length} · sample_time_ms ${selected.sim_time_ms}\ncontacts ${selected.contacts ? JSON.stringify(selected.contacts) : '未知'}`;
    // 暂停时 cursor 是冻结的 UI 时刻；若使用最近离散帧时间，
    // 无关的尺寸重绘可能在没有用户操作时改变可见时间。
    root.dataset.timeMs = String(playing ? selected.sim_time_ms : cursor);
    root.dataset.stage = selected.stage;
    root.dataset.objectPosition = JSON.stringify(objectPosition);
  };

  try {
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    viewport.append(renderer.domElement);
    robot = createRobotScene(scene, camera, renderer.domElement, payload.robot_scene);
    renderer.domElement.addEventListener('webglcontextlost', (event) => {
      event.preventDefault();
      fallback('WebGL 上下文丢失');
    });
  } catch (error) {
    fallback(error instanceof Error ? error.message : String(error));
  }

  payload.events.forEach((event, index) => {
    events.add(new Option(`${(event.offset_ms / 1000).toFixed(2)}s · ${event.message}`, String(index)));
  });

  const resize = new ResizeObserver(() => {
    if (!renderer) return;
    const width = Math.max(viewport.clientWidth, 280);
    const height = Math.max(viewport.clientHeight, 280);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    paint();
  });
  resize.observe(viewport);

  controls.play.onclick = () => {
    if (cursor >= duration) cursor = 0;
    playing = !playing;
    last = performance.now();
    controls.play.textContent = playing ? '暂停' : '播放';
    paint();
  };
  root.querySelector<HTMLButtonElement>('#restart')!.onclick = () => {
    cursor = 0;
    playing = false;
    controls.play.textContent = '播放';
    paint();
  };
  root.querySelector<HTMLButtonElement>('#reset-camera')!.onclick = resetCamera;
  controls.seek.oninput = () => {
    cursor = Number(controls.seek.value);
    playing = false;
    controls.play.textContent = '播放';
    paint();
  };
  events.onchange = () => {
    if (events.value) {
      cursor = payload.events[Number(events.value)].offset_ms;
      playing = false;
      controls.play.textContent = '播放';
      paint();
    }
  };
  view.onchange = () => {
    playing = false;
    controls.play.textContent = '播放';
    paint();
  };
  robot?.controls.addEventListener('change', () => {
    if (!playing && renderer && view.value === 'threejs') renderer.render(scene, camera);
  });

  const tick = (now: number) => {
    if (playing) {
      cursor = Math.min(duration, cursor + (now - last) * Number(controls.speed.value));
      if (cursor >= duration) {
        playing = false;
        controls.play.textContent = '播放';
      }
      paint();
    }
    last = now;
    raf = requestAnimationFrame(tick);
  };

  (window as Window & { __ROBOT_DEBUG__?: () => { geoms: RobotDebugPose[]; sample_time_ms: number | null; mesh_count: number } }).__ROBOT_DEBUG__ = () => ({
    geoms: selected && robot ? robot.readDebugPose(selected) : [],
    sample_time_ms: selected?.sim_time_ms ?? null,
    mesh_count: robot?.geomMeshes.length ?? 0
  });
  const cleanup = () => {
    disposed = true;
    cancelAnimationFrame(raf);
    resize.disconnect();
    delete (window as Window & { __ROBOT_DEBUG__?: unknown }).__ROBOT_DEBUG__;
    robot?.dispose();
    renderer?.dispose();
  };
  window.addEventListener('pagehide', cleanup, { once: true });
  resetCamera();
  paint();
  raf = requestAnimationFrame(tick);
}

function legacyMarkup(payload: RendererPayload): string {
  return `${STYLE}<section class="physical"><strong>仿真轨迹回放</strong><div class="muted">工具 / 物体 / 目标区域示意 · 非真实机器人几何重建 · 坐标单位 m</div>
    <div class="toolbar"><span>蓝色：工具</span><span>橙色：物体</span><span>绿色：目标中心</span><label>视图 <select id="view" aria-label="回放渲染器"><option value="threejs">Three.js 3D</option><option value="svg">SVG 侧视图</option></select></label></div>
    <div id="fallback-notice" role="status"></div><div class="viewport"><div id="three" style="height:100%"></div><svg id="svg" viewBox="0 0 800 330" aria-label="物理轨迹侧视图"></svg></div>
    <div class="toolbar"><button id="play">播放</button><button id="restart">回到起点</button><label>倍速 <select id="speed" aria-label="回放倍速"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option></select></label><output id="clock"></output><span id="stage"></span></div>
    <input id="seek" aria-label="回放时间" type="range" min="0" step="10" value="0"><label>事件定位 <select id="events" aria-label="事件定位"><option value="">选择事件跳转（不改变结果）</option></select></label><div id="frame-values"></div></section>`;
}

function renderLegacy(root: HTMLElement, payload: RendererPayload): void {
  root.innerHTML = legacyMarkup(payload);
  const controls = getControls(root);
  const view = root.querySelector<HTMLSelectElement>('#view')!;
  const svg = root.querySelector<SVGSVGElement>('#svg')!;
  const three = root.querySelector<HTMLDivElement>('#three')!;
  const events = root.querySelector<HTMLSelectElement>('#events')!;
  const frames = payload.frames;
  if (!frames.length) { controls.play.disabled = true; return; }

  const duration = frames[frames.length - 1].offset_ms;
  controls.seek.max = String(duration);
  let cursor = 0; let playing = false; let last = performance.now(); let raf = 0;
  let renderer: THREE.WebGLRenderer | null = null;
  const scene = new THREE.Scene(); scene.background = new THREE.Color('#0c1420');
  const camera = new THREE.PerspectiveCamera(40, 1, .01, 20); camera.position.set(1.15, 1.15, 1.5); camera.lookAt(0, .12, 0);
  scene.add(new THREE.AmbientLight(0xffffff, 2), new THREE.GridHelper(1.6, 16));
  const tool = new THREE.Mesh(new THREE.SphereGeometry(.025), new THREE.MeshStandardMaterial({ color: '#58caff' }));
  const object = new THREE.Mesh(new THREE.BoxGeometry(.07, .07, .07), new THREE.MeshStandardMaterial({ color: '#ffb449' }));
  const target = new THREE.Mesh(new THREE.RingGeometry(.072, .08, 48), new THREE.MeshBasicMaterial({ color: '#55dfae', side: THREE.DoubleSide }));
  target.rotation.x = -Math.PI / 2; scene.add(tool, object, target);

  const paint = () => {
    const frame = samplePhysicalFrame(frames, cursor); if (!frame) return;
    const state = frame.target_state;
    tool.position.set(...physicalWorld(frame.arm_pose.x, frame.arm_pose.y, frame.arm_pose.z));
    object.position.set(...physicalWorld(state.object_x, state.object_y, state.object_z ?? 0));
    target.position.set(...physicalWorld(state.dropoff_x, state.dropoff_y, state.dropoff_z ?? 0));
    const [tx, tz] = physicalProjection(frame.arm_pose.x, frame.arm_pose.z);
    const [ox, oz] = physicalProjection(state.object_x, state.object_z ?? 0);
    const [gx, gz] = physicalProjection(state.dropoff_x, state.dropoff_z ?? 0);
    svg.innerHTML = `<line x1="20" y1="310" x2="780" y2="310" stroke="#60738b"/><text x="20" y="25" fill="#afbed4">X–Z 侧视投影 · Y 坐标见下方数值</text><rect data-entity="target" x="${gx - 35}" y="${gz - 18}" width="70" height="36" fill="none" stroke="#55dfae" stroke-dasharray="4"/><circle data-entity="tool" cx="${tx}" cy="${tz}" r="10" fill="#58caff"/><rect data-entity="object" x="${ox - 15.4}" y="${oz - 15.4}" width="30.8" height="30.8" fill="#ffb449"/><text x="720" y="300" fill="#afbed4">X →</text>`;
    three.hidden = view.value !== 'threejs'; svg.style.display = view.value === 'svg' ? 'block' : 'none';
    if (renderer && !three.hidden) renderer.render(scene, camera);
    controls.seek.value = String(cursor); controls.clock.textContent = `${(cursor / 1000).toFixed(2)} / ${(duration / 1000).toFixed(2)} s`; controls.stage.textContent = `阶段：${stageLabel(frame.stage)}`;
    controls.values.textContent = `工具 [${formatPosition([frame.arm_pose.x, frame.arm_pose.y, frame.arm_pose.z])}] m\n物体 [${formatPosition([state.object_x, state.object_y, state.object_z ?? 0])}] m · 目标 [${formatPosition([state.dropoff_x, state.dropoff_y, state.dropoff_z ?? 0])}] m`;
    root.dataset.timeMs = String(cursor); root.dataset.stage = frame.stage; root.dataset.objectPosition = JSON.stringify([state.object_x, state.object_y, state.object_z ?? 0]);
  };
  const fallback = (reason: string) => { playing = false; controls.play.textContent = '播放'; view.value = 'svg'; view.options[0].disabled = true; root.querySelector('#fallback-notice')!.textContent = `3D 不可用，已回退 SVG：${reason}`; paint(); };
  try { renderer = new THREE.WebGLRenderer({ antialias: true }); renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2)); three.append(renderer.domElement); renderer.domElement.addEventListener('webglcontextlost', (event) => { event.preventDefault(); fallback('WebGL 上下文丢失'); }); } catch (error) { fallback(error instanceof Error ? error.message : String(error)); }
  payload.events.forEach((event, index) => events.add(new Option(`${(event.offset_ms / 1000).toFixed(2)}s · ${event.message}`, String(index))));
  const resize = new ResizeObserver(() => { if (!renderer) return; renderer.setSize(Math.max(three.clientWidth, 280), 330); camera.aspect = Math.max(three.clientWidth, 280) / 330; camera.updateProjectionMatrix(); paint(); }); resize.observe(three);
  controls.play.onclick = () => { if (cursor >= duration) cursor = 0; playing = !playing; last = performance.now(); controls.play.textContent = playing ? '暂停' : '播放'; paint(); };
  root.querySelector<HTMLButtonElement>('#restart')!.onclick = () => { cursor = 0; playing = false; controls.play.textContent = '播放'; paint(); };
  controls.seek.oninput = () => { cursor = Number(controls.seek.value); playing = false; controls.play.textContent = '播放'; paint(); };
  events.onchange = () => { if (events.value) { cursor = payload.events[Number(events.value)].offset_ms; playing = false; controls.play.textContent = '播放'; paint(); } };
  view.onchange = () => { playing = false; controls.play.textContent = '播放'; paint(); };
  const tick = (now: number) => { if (playing) { cursor = Math.min(duration, cursor + (now - last) * Number(controls.speed.value)); if (cursor >= duration) { playing = false; controls.play.textContent = '播放'; } paint(); } last = now; raf = requestAnimationFrame(tick); };
  paint(); raf = requestAnimationFrame(tick);
  window.addEventListener('pagehide', () => { cancelAnimationFrame(raf); resize.disconnect(); renderer?.dispose(); scene.traverse((node) => { const mesh = node as THREE.Mesh; mesh.geometry?.dispose(); if (Array.isArray(mesh.material)) mesh.material.forEach((material) => material.dispose()); else mesh.material?.dispose(); }); }, { once: true });
}

export function renderPhysical(root: HTMLElement, payload: RendererPayload): void {
  if (payload.robot_scene && payload.robot_frames?.length) renderPanda(root, payload);
  else renderLegacy(root, payload);
}
