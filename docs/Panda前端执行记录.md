# Panda 前端执行记录

## handoff-panda-renderer-01

日期：2026-09-22

### 范围与结果

- Q1/Q2/Q3 按 `docs/Panda实施与门禁.md` 的限定通过进入 Q4；本次只实现 Panda 前端几何回放，不替代主控的真实浏览器验收。
- 保留 legacy `frames` 与 SVG/旧小球路径；仅当 payload 同时提供 `robot_scene` 和 `robot_frames` 时切换完整 Panda 路径。
- Panda 路径消费 `robot_scene=scene.json` 对象和 `robot_frames=trajectory.jsonl` 原始行；显示顶层 `run_id/model_id`、实际采样秒数、阶段、夹爪开度、接触信息和几何计数。
- Panda 采样取不晚于 cursor 的最后一条原始记录，不插值；几何、夹爪显示信息和阶段均来自同一记录帧。未加入前端 IK、吸附或业务结果计算。
- MuJoCo 世界使用统一父组 `rotation.x = -PI/2` 映射到 Three.js；mesh 顶点直接使用编译网格坐标，geom 不叠加 mesh 原点偏移。地面、目标、物体和全部可视几何均保留。
- `window.__ROBOT_DEBUG__()` 从实际 Three.js mesh 的 `getWorldPosition()` / `getWorldQuaternion()` 返回姿态、选中 `sample_time_ms`、几何数量和首段帧间隔；不是 payload/DOM 镜像。
- Panda 有 OrbitControls 旋转/缩放、复位镜头、播放/暂停/继续、拖动、倍速、事件定位和生命周期清理；同时提供明确标注的 SVG 简化标记视图。legacy 的 `root.dataset.timeMs/objectPosition` 等字段继续写入。

### 修改文件

- `web/robot_renderer/src/payload.ts`：新增 Panda scene、mesh、geom pose、原始 robot frame typed interfaces，并扩展 `model_id/run_id/robot_scene/robot_frames`。
- `web/robot_renderer/src/physical-frame.ts`：新增离散 Panda 原始帧采样；legacy 采样保留。
- `web/robot_renderer/src/robot-scene.ts`：新增 little-endian base64 网格解码、MuJoCo 轴/四元数转换、完整几何组装、OrbitControls、debug 姿态读取和 dispose。
- `web/robot_renderer/src/physical.ts`：新增 Panda 回放 UI 和真实几何驱动；保留 legacy Three.js/SVG 独立路径。
- `web/robot_renderer/tests/physical-frame.test.ts`：新增 Panda 不插值、按 cursor 取帧测试。
- `web/robot_renderer/tests/robot-scene.test.ts`：新增 float32/uint32 little-endian 解码、轴旋转和 wxyz→xyzw 测试。
- `docs/Panda前端执行记录.md`：本记录。

未修改 `web/robot_renderer/src/index.ts`、Python/app、共享台账和生产依赖。

### 已执行命令与证据

在 `web/robot_renderer` 执行：

```text
npm run check   PASS
npm run test    PASS: 3 files, 12 tests
npm run build   PASS: Vite production build, dist/renderer.js 520.59 kB
```

真实 fixture 只读核对：`.tmp-tests/panda-physics/panda-baseline-0/` 的 `scene.json` 为 `panda-scene-1`，包含 56 meshes、61 geoms；`trajectory.jsonl` 为 421 行，时间范围 2 ms 到 14000 ms，所有记录行均含 61 个 `geom_poses`。

### 未验证与交接

- 未在真实浏览器中启动 Panda iframe、读取实际 WebGL mesh 矩阵、执行截图/可见性、拖动/事件入口和 WebGL 失败恢复；这些由主控继续完成。
- 未做浏览器进程组内存、冷/热启动、帧间隔实测；代码仅通过 debug 方法附带首段记录帧间隔。
- 未验证主控页面对 payload 的最终导入、iframe 高度 820 下的实际可读性；组件默认 viewport 为 390px，可由主控按真实页面调整。
- 代码级保留了 Panda 的 SVG 简化视图与事件定位入口，但尚未在真实浏览器中核对 WebGL 上下文丢失时的自动降级截图。

### handoff-panda-renderer-01 回归修复补充

- 恢复 legacy renderer 原有回归入口：事件定位下拉框、`aria-label`、SVG 的 `data-entity=tool/object/target` 标记、事件跳转不改变结果、WebGL 初始化失败和 `webglcontextlost` 后回退 SVG；回退后播放按钮仍可重新播放 SVG。
- `readDebugPose()` 现在只读取当前实际 mesh 的世界矩阵并执行 `updateMatrixWorld(true)`，不再从传入帧重新调用 `applyFrame()`，避免 debug 调用掩盖渲染更新缺陷。
- 移除 `__ROBOT_DEBUG__()` 中由 trajectory 相邻时间推导的 `frame_interval_ms`；当前没有真实浏览器渲染帧间隔实测，因此不报告该字段。
- 自测：再次运行 `npm run check`、`npm run test`、`npm run build` 均通过（13 tests）；新增 debug 纯读取世界矩阵测试，并使用源码检索确认 legacy 的事件/ARIA/data-entity/context-loss 入口和 Panda debug 不含 payload 重赋值/伪造帧间隔。真实浏览器行为仍由主控验收。

### handoff-panda-renderer-02

日期：2026-09-22

### 本次修复

- Panda WebGL 初始化加入 `try/catch`，并监听 `webglcontextlost`；失败时切换到可继续播放的 SVG 简化视图。
- Panda SVG 改用 trajectory 原始帧的 `tool_position`、`object_position`、`target_position`，不再把最后一个 `geom_pose` 误当末端。SVG 保留 `data-entity=tool/object/target`。
- Panda 写入 `#physical-root` 的 `data-object-position`，同时在帧信息中显示物体 XYZ；`descend/lift/retreat/settle` 映射为中文阶段。
- Panda viewport 调整为更接近任务全景的镜头与视图高度；不裁切完整任务，保留双指可辨识空间。
- OrbitControls 在暂停状态的 `change` 事件直接重绘；Three.js/SVG 手动切换都会暂停并保持当前 cursor/时刻。
- Panda 标题中的 `run_id/model_id` 改为静态占位节点后使用 `textContent` 写入，避免产物字符串进入 `innerHTML`。
- `RobotFramePayload` 补齐 `tool_position` 类型。

### 验证

先执行：

```text
npm run check   PASS
npm run test    PASS: 3 files, 13 tests
npm run build   PASS
```

浏览器验收命令：

```text
python scripts/verify_panda_browser.py --url http://127.0.0.1:8517 --evidence .tmp-tests/panda-frontend-acceptance-skip --skip-faults
```

结果：主控及独立 Q4 实际浏览器核验的全量 8 组结果已通过，证据为 `docs/evidence/panda-browser-20260922/results.json`；实际 context-loss 补测也已通过。实际证据包括：

- 6 个关键帧、61 个真实几何 world matrix：最大位置误差 `1.8054e-16 m`，最大旋转误差 `8.4294e-08 rad`。
- 播放/暂停/继续、视图切换、物体位置、事件定位：通过。
- WebGL fallback：通过；实际 context-loss 补测：通过。
- page errors：空；浏览器进程：已回收。
- 浏览器 RAF 间隔实测中位数 `33.3 ms`、P95 `33.4 ms`；该值来自验收脚本运行，不写入 `__ROBOT_DEBUG__`。

早期一次完整命令曾因脚本故障断言与当时 runtime 错误码不一致而失败：`scripts/verify_panda_browser.py:123` 当时要求 `worker_exception`，而旧 run 返回 `worker_crash`。该结论仅作为历史记录；当前已修正故障等待逻辑并在新 run 后重新断言，主控全量 8 组及实际 context-loss 补测均已通过。本次不修改 Python/脚本。
- 未改 Python 适配；本记录依据用户已确认的 `robot_scene`/`robot_frames` 接入结果和本地 fixture 只读核对。
