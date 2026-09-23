# Panda Q4 交付审查

### handoff-panda-q4-review-01

- 结果：2026-09-22，独立 Q4 初审完成；核心物理运行、同源几何回放、页面异常恢复和新增损坏报告边界已有实证，但比较输入完整性仍有阻断，门禁结论为 **Changes required**。
- 完成与决定：不把 Q1/Q2/Q3 的限定通过或开发测试数量当作最终放行；本轮仅审查 V2.8D Panda 新增/修改及其继承风险。未修改代码、台账或既有证据，未安装依赖、未外发、未创建 PR。
- 依据：权威 PRD、任务计划、实施门禁、Q2/Q3 报告；当前源码与测试；独立运行 `.tmp-tests/panda-q4-browser/results.json`；正式浏览器证据 `docs/evidence/panda-browser-20260922/results.json`；worker/physics 结果与原生关键帧截图。
- 承接：执行者修复 F-Q4-01 后，仅需对比较完整性及其直接回归复核；资源记录口径和缺失资产边界在补充可复核证据前保持未验证。Q4 阻断复核次数仍按启动契约最多 2 次、每次 10 分钟计算。

## 1. 审查范围与判定口径

审查依据为 `PRD.md` V2.8D、`docs/V2机械臂一致性接入任务计划.md`、`docs/Panda实施与门禁.md` 以及 Q2/Q3 报告。重点覆盖：真实接触抓取而非 weld/qpos 搬运；稳定窗口和失败证据；编译几何与世界姿态同源；debug 只读实际对象；哈希、损坏数据和旧数据边界；页面 poll 超时、终态进程/管道回收和再次运行；同模型同初态比较、样本限制；资产许可与资源记录。

单条状态使用 `Pass / Finding / Unverified / Out of Scope`；门禁使用 `Passed / Passed for limited scope / Changes required / Review incomplete`。截图只证明可见性，不替代数值一致性；通过测试只证明其断言覆盖，不外推到未覆盖的实际链路。

## 2. 独立核验结果

| 范围 | 状态 | 独立依据 |
|---|---|---|
| 真实 Panda 接触抓放、无 object weld、无运行时物体 qpos 搬运 | Pass（声明范围） | `robot_mvp/panda_model.py:81-88` 仅在初始状态设置物体 qpos；`robot_mvp/panda_runner.py:153-174` 通过 `mj_step`、接触力、抬升/释放/稳定窗口逐物理步判定；`tests/test_panda_task.py:25-64` 检查等式约束仅为 joint、正常/偏移失败和无 `grasp_lock`。worker 6 轮结果为 baseline 3/3 成功、offset 3/3 失败，14 s 固定条件重复，不支持泛化。
| 稳定窗口与失败实据 | Pass（固定场景） | `panda_runner.py:159-174,194-205` 记录双指力、抬升、实际释放、目标/速度阈值和稳定时长；原生关键帧位于 `.tmp-tests/panda-physics-final/`。失败结果仍由运动/接触事实产生，未用参数名直接指定成功。
| 同源 compiled geometry + 世界姿态 | Pass | `panda_runner.py:25-47,175-188` 从已编译 MuJoCo 模型导出网格并逐帧导出 `geom_poses`；`web/robot_renderer/src/robot-scene.ts:64-111` 解码同源网格、应用记录姿态，debug 读取已绘制对象而不重写 payload；独立浏览器重跑 `actual_mesh_poses` 通过，最大位置误差 `1.8054e-16 m`、旋转误差 `8.4294e-8 rad`。截图 `.tmp-tests/panda-q4-browser/baseline-6500-replay.png` 与原生 `.tmp-tests/panda-physics-final/panda-baseline-0/native-6500.png` 可见同一抬升阶段。
| 播放、拖动、事件定位、同一帧数值 | Pass | `.tmp-tests/panda-q4-browser/results.json` 的 `playback_and_views` 通过，RAF 中位数约 33.3 ms、P95 约 33.4 ms；截图覆盖首帧、抓取/抬升、释放和 SVG 视图；`physical.ts:136-155,185-211` 使用同一选中记录帧更新几何、数值、事件和时间。
| 页面 crash/timeout、poll 回收、故障后再次启动 | Pass（已覆盖入口） | 独立浏览器重跑 `page_crash`、`page_timeout`、`restart_after_fault` 均通过，且 `browser_processes_reaped=true`；`v2_runtime.py:115-161,163-204` 对 poll 终态、超时、异常和缺终态执行 reap/terminate/kill 并关闭 stdout/stderr；`tests/test_panda_runtime.py:44-87` 直接断言进程和管道回收。
| WebGL 不可用 SVG 降级 | Pass | 独立浏览器重跑 `panda_webgl_fallback` 通过；`physical.ts:126-134,157-168` 在 WebGL 初始化失败或上下文丢失时停止播放并切换 SVG，截图为 `.tmp-tests/panda-q4-browser/webgl-fallback.png`。
| 资产来源、许可、来源清单哈希 | Pass（来源层面） | `assets/robots/panda/SOURCES.json` 固定 Menagerie commit `822c2d8f...`、Apache-2.0 和逐文件 SHA256；`panda_model.py:32-47` 校验清单、路径边界和每个文件，当前源文件指纹与 worker 证据一致。未将来源层面通过外推为运行时缺失资产全链路通过。
| 损坏轨迹/姿态/JSON/scene/model 身份 | Pass（已覆盖子集） | `panda_artifacts.py:24-84` 校验 scene hash、schema、模型/运行 ID、网格、帧时间、有限数值和四元数；`tests/test_panda_artifacts.py:45-111` 覆盖空轨迹、缺姿态、乱序、非法四元数、非有限值、scene 损坏、模型错配和 malformed JSON。新增 `v2_view.py:15-39` 显式拒绝 `failure/criteria` 非 dict、非法时长和终态冲突；`tests/test_panda_view.py:13-23` 独立运行通过。
| 旧 V1/平面 V2 兼容与 WebGL 旧路径 | Pass（限定旧路径） | `v2_adapter.py:21-28,62-95` 保留 v2.0 与 v2.1 分派；正式旧平面 `docs/evidence/panda-legacy-20260922/results.json` 4/4 通过。该证据不覆盖所有历史损坏产物组合。
| Python/前端回归 | Pass（测试范围） | 本轮实际运行 `python -m unittest discover -s tests -v`：42/42；新增报告结构边界定向运行：2/2；`npm run check --prefix web/robot_renderer` 通过；`npm run test --prefix web/robot_renderer`：13/13。数量不替代实际页面/物理证据，也不消除下述比较阻断。
| 资源与性能 | Unverified（记录口径需收敛） | 浏览器重跑记录专用 Chromium RSS 增量约 631 MB，低于 1 GB 目标；worker 证据一组记录约 305–306 MB，另一组记录约 695–712 MB，均低于 2 GB 目标但测量口径/运行环境说明不一致。不能把两组互相矛盾的峰值合并为一个稳定基线。

## 3. 阻断 Finding

### F-Q4-01 — Major：比较器未验证实际参与比较的 Panda 产物完整性

- 要求：任务计划 TC-04P 要求同模型/场景/评估版本/初始状态和唯一参数差异才允许比较；P-06 要求损坏 JSON、模型哈希错误等不得产生虚假完整结果。`docs/V2机械臂一致性接入任务计划.md:98-100`；实施契约还要求模型不匹配时拒绝错误比较，`docs/Panda实施与门禁.md:26-32`。
- 触发：调用 `build_comparison_report()` 时，`robot_mvp/v2_runtime.py:248-313` 只读取 `meta.json` 与 `summary.json`，比较 `model_hash`、`scene_sha256`、evaluation/controller 和初始状态，但不调用 `validate_panda()`，不读取/校验 `scene.json`、`trajectory.jsonl`、事件或 `summary.final_status` 与 `summary.success` 的一致性。
- 实际证据：在 `.tmp-tests/panda-q4-compare-corrupt-scene/` 复制两条有效 Panda 运行后仅把第二条 `scene.json` 改为 `{}`，保持 meta 不变，比较器仍返回 `comparison_status=comparable`（`evidence_status` 因样本数为 2 才为 insufficient）；在 `.tmp-tests/panda-q4-compare-invalid2/` 仅把 `summary.success=false`、`final_status=succeeded`，仍返回 `comparison_status=comparable`。这不是假设性疑问，而是当前函数的可复现输入边界。
- 影响：页面“同页比较报告”可在回放产物已损坏或结果终态自相矛盾时继续产生可比性/成功率统计；若达到 3 个输入，现有 `evidence_sufficient` 条件还可能把该不完整集合推进到初步比较信号，违反“损坏数据不得形成受控优劣结论”。正常 8 组浏览器证据仍有效，但不能关闭此数据完整性阻断。
- 建议：Panda 比较入口先对每个输入执行与回放相同的产物完整性校验，至少拒绝 scene hash 内容不匹配、trajectory/events 缺失或非法、model/scene identity 不一致、summary final status 与 success 冲突；再进行同条件和唯一参数比较。补一条“损坏 scene/终态冲突不得 comparable”的回归后重跑直接比较页面。
- 状态：Open；处置：Fix required；未进入复审关闭。

## 4. 未验证边界与非阻断意见

1. `source_manifest()` 的缺失/篡改入口已有清单层测试，但本轮没有独立跑“实际加载过程中删除/缺少单个 mesh 后页面错误提示与再次启动”的完整页面旅程；该范围标为 `Unverified`，不把来源清单 Pass 外推为缺资产恢复 Pass。
2. worker/physics 两份资源证据的峰值约 306 MB 对约 696–712 MB 不一致；即使均低于预算，仍需统一测量窗口、进程范围和是否包含父进程后，才能冻结资源基线。
3. 当前 3+3 次是固定初始状态的重复，不是 3 个场景；比较报告代码也明确 `generalization_supported=false`，不能支持策略普遍改善、生产稳定性、视觉误差、真机或 sim-to-real 结论。
4. 本轮不重开无关 V1 页面；旧平面 4 组证据仅保留为兼容回归边界。

## 5. 门禁结论

**Q4：Changes required。**

放行所需最小动作是关闭 F-Q4-01，并对比较器/比较页面做直接回归。物理接触、稳定窗口、同源几何姿态、页面故障恢复、SVG 降级和新增损坏报告结构边界在声明范围内已有通过证据；资源基线和缺资产完整旅程仍需补证，但当前最明确的核心阻断是比较输入完整性未闭合。若修复未改变已审查物理/页面契约，下一次只复核 F-Q4-01 及直接受影响的比较证据，不重复完整 Q4 审查。

## 6. 证据入口

- 独立浏览器重跑：`.tmp-tests/panda-q4-browser/results.json` 及同目录截图。
- 正式作者浏览器证据：`docs/evidence/panda-browser-20260922/results.json`。
- 固定条件 worker/资源：`docs/evidence/panda-workers-20260922/results.json`、`docs/evidence/panda-physics-20260922/results.json`。
- 旧平面回归：`docs/evidence/panda-legacy-20260922/results.json`。
- 原生关键帧：`.tmp-tests/panda-physics-final/panda-baseline-0/`、`.tmp-tests/panda-physics-final/panda-offset-grasp-0/`。
- 比较完整性复现：`.tmp-tests/panda-q4-compare-corrupt-scene/`、`.tmp-tests/panda-q4-compare-invalid2/`。

### handoff-panda-q4-review-02

- 结果：2026-09-22，Q4 第一次限定复核完成；仅复核 F-Q4-01 比较完整性及直接影响、新资源口径和相关新增浏览器证据。F-Q4-01 已关闭，限定门禁结论为 **Passed for limited scope**。
- 完成与决定：Panda 比较现在逐输入读取并校验实际 `scene.json`、`trajectory.jsonl`、`events.jsonl` 和结果终态；非法输入结构化为 rejected，`sample_count=0`、`success_count=null`、`success_rate=null` 且不进入 strategy groups。旧平面比较路径未重审。
- 依据：`docs/Panda后端执行记录.md#handoff-panda-runtime-03`；`robot_mvp/v2_runtime.py:254-305`；`robot_mvp/panda_artifacts.py:24-84`；runtime/v2 严格资源警告回归 14/14；`docs/evidence/panda-browser-20260922/comparison-regression.json`、`context-loss.json`；`docs/evidence/panda-workers-audited-20260922/results.json` 及 `scripts/verify_panda_physics.py`。
- 承接：保留初审的非本范围边界：实际删除在用资产后的完整 UI 恢复仍未验证；资源证据现已可作为独立 worker 基线，不与早期作者进程/Renderer 数据合并。若无新的实质变更，不再重开已关闭范围。

## 7. Q4 第一次限定复核

### F-Q4-01 复核：Resolved

- 要求：TC-04P/P-06 要求比较前验证 Panda 产物完整性，损坏 scene、trajectory、events 或结果终态冲突不得进入比较统计。
- 修复核对：`robot_mvp/v2_runtime.py:270-305` 在 Panda 输入路径调用 `validate_panda(path, meta, summary, frames, events)`；`_load_jsonl` 读取真实轨迹和事件，校验失败进入 `rejected_samples` 并立即返回 rejected 结果。无效输入明确为 `sample_count=0`、`success_count=None`、`success_rate=None`、空 `strategy_groups`，没有把无效样本伪装成 0 成功样本或混入分组。
- 直接证据：执行记录报告 `.tmp-tests/panda-q4-compare-corrupt-scene/` 和 `.tmp-tests/panda-q4-compare-invalid2/` 已被 rejected；新增专属用例进一步覆盖 scene 损坏、trajectory 缺失/非法 JSON、events 非法 JSON、结果终态冲突和正常同条件比较，断言 rejected、无统计和 `rejected_samples` 非空。独立运行 `python -W error::ResourceWarning -m unittest tests.test_panda_runtime tests.test_v2_runtime -q`：14/14 通过。
- 页面直接影响：`docs/evidence/panda-browser-20260922/comparison-regression.json` 的 `comparison_page_after_integrity_fix` 为 pass，且无 page errors；本次未重跑已通过的 8 组页面旅程。
- 状态：Resolved；处置：Accept；门禁阻断关闭。

### 新资源口径复核：Pass（限定资源基线）

- `docs/evidence/panda-workers-audited-20260922/results.json` 为当前唯一独立 worker 基线：6 轮均记录 `sim_s≈14`，每轮 `process_id`，`memory_scope=calling_process_peak_working_set`；脚本 `scripts/verify_panda_physics.py:31-45` 断言性能记录 PID 等于 `handle.process.pid`、worker 已退出，且 PID 不等于生成原生截图的父进程 PID。
- 6 轮峰值约 305.27–306.19 MB，均低于实施门禁的 2 GB worker 目标；墙钟约 1.76–8.63 s/14 s 仿真，产物大小约 13.24 MB。性能证据中的 `robot_mvp/panda_runner.py`、模型、验证脚本和资产清单 SHA256 与当前文件一致。
- 早期 `panda-physics-20260922` 的约 696–712 MB 已由其 README 明确为同一作者进程直接运行并包含原生 Renderer，不再与独立 worker 基线合并或改写；该差异不再阻塞当前资源口径。
- 状态：Pass（限定为独立 worker 峰值与当前固定 6 轮）；不外推为生产容量或并发基线。

### 直接影响边界

- `source_manifest` 隔离副本删除 `finger_0.obj` 的拒绝测试已纳入通过证据，且确认未触碰在用资产；这证明缺失资产的加载器层边界。
- 实际删除正在使用的资产后，从页面加载失败到可恢复再次启动的完整 UI 旅程仍未验证，沿用 `Unverified`；本次不把它扩大成 F-Q4-01 阻断，也不声称完整资产恢复通过。
- `context-loss.json` 的真实 WebGL 上下文丢失补测为 pass；该证据只覆盖直接 WebGL 降级影响，不改变初审其他范围结论。

## 8. 限定复核后的门禁状态

**Q4：Passed for limited scope。**

本次限定复核允许在声明范围内承接：Panda 产物完整性校验、损坏输入拒绝/统计隔离、比较页面直接回归，以及独立 worker 资源口径。仍不能外推为完整生产容量、并发稳定性、实际删除在用资产后的 UI 恢复、真实机器人、视觉误差或 sim-to-real 结论。除非出现新的实质变更或证据推翻，不重开初审已通过范围。
