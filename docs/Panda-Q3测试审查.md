# Panda Q3 测试与 Harness 独立审查

### handoff-panda-q3-review-01

- 审查角色：独立 Q3 测试/Harness 审查者
- 审查性质：Q3 唯一一次限定复核；本次仅复核门禁范围修正和新增最小 Panda 入口，不泛化重审。
- 审查时间：2026-09-22，复核预算 5 分钟
- 审查范围：PRD V2.8D、完整任务计划、`docs/Panda实施与门禁.md` 的 Q2/Q3 契约、`tests/test_panda_task.py`、新增 `robot_mvp/panda_runner.py`、现有 `tests/test_v2_runtime.py`、`scripts/verify_v2_browser.py`，以及最小入口 `python -m scripts.spike_panda` 的已记录运行结果。
- 审查边界：本报告只评 Q3 测试设计、最小验证入口、失败恢复设计和证据可观察性；不替 Q2 做架构/资产放行，不降低 Q4 接触、矩阵、恢复和资源验收，不修改代码、不新增依赖、不外发。

### handoff-panda-q3-review-02

- 类型：Q3 唯一一次限定复核的结论记录。
- 初审历史：保留并链接 [handoff-panda-q3-review-01](#handoff-panda-q3-review-01)。
- 记录说明：本节仅校正门禁范围与结论归档格式，不开启第三轮审查，不重新运行测试，也不审查新增修改。

## 结论

**Q3：Passed for limited scope。**

本次复核确认：质量闭环允许在“最小入口建设任务、所有者、可观察字段、判定标准和后续入口”已经明确时，限定进入 Q4；Q3 不要求功能尚未实现时已经存在完整 E2E 通过证据。此前把未实现 runner、网页矩阵验证和页面恢复列为当前 Q3 进入阻塞，已校正为不适当的门禁判断。

当前 Q3 可交接范围：

1. H1 Panda 模型入口已有记录证据：模型加载、机械臂运动、双指闭合和原生截图。
2. H2 最小 Panda 任务入口已建立并实际通过：正常/受控偏移失败、轨迹时间、几何帧、夹爪开度、抬升、释放和稳定窗口均有最小断言。
3. Q3 契约已为接触证据、几何实际矩阵、数据校验、页面异常恢复和资源检查指定字段/标准/责任入口；这些是 Q4 实现与验收任务，不是功能尚未完成即阻塞 Q3 的理由。

这不是 Panda 功能或整体 V2 的最终放行。Q4 仍必须完成并验证接触证据强化、Three.js 实际世界矩阵对照、Panda 页面/资产失败恢复及其余契约回归；本报告不降低这些验收要求。

## 覆盖核对

| 核心需求/风险 | 当前测试或入口 | 独立性与可观察性判断 | Q3 状态 |
|---|---|---|---|
| 完整 Panda 模型可加载、机械臂运动、双指开合 | `scripts/spike_panda.py`；Q2 交接记录的实际运行结果 | 有独立 CLI 入口、原生截图和数值断言；明确声明不等于抓取成功 | Pass（H1 限定范围） |
| 正常/受控偏移任务入口可运行 | `tests/test_panda_task.py` + `robot_mvp.panda_runner.run_panda` | 临时目录、独立 run id；实际运行 1/1 通过。runner 输出 contacts、geom_poses、稳定判据和完整产物 | Pass（H2 最小入口） |
| 接触抓取判定的测试设计 | Q2/Q3 契约、runner 字段与 `test_panda_task.py` | 字段、所有者、标准和后续入口已定义；当前最小测试仍未直接断言接触对/接触时段与双指—物体相对运动 | Finding（Q4 前增强） |
| 运行产物、时间、几何姿态可回查 | runner 的 `scene.json`、`trajectory.jsonl`、`meta.json`、`summary.json` | 最小入口已产生真实字段；当前测试只检查几何数量和有限时间，未完成 scene 清单/ID/四元数/矩阵的强对照 | Finding（Q4 前增强） |
| worker 崩溃、超时、进程回收、页面再次启动 | 旧 `test_v2_runtime.py` TC-03；Q3 契约中的 Panda 扩展任务 | 最小责任入口和判定方向已给出；Panda 页面/资产路径尚未形成最终运行证据 | Unverified（Q4 验证任务） |
| 同条件比较、唯一参数差异、证据不足 | 旧 `test_v2_runtime.py` TC-04；计划 TC-04P | 旧平面已有独立证据；Panda model hash、scene、评估版本和初始状态拒绝规则已有契约任务，尚待实现回归 | Unverified（Q4 验证任务） |
| Panda 网页显示与后端同源 | Q3 契约、待复用的 Playwright 路径 | 矩阵读取入口、字段和误差标准已定义；现有旧浏览器脚本尚未覆盖 Panda robot scene | Unverified（Q4 验证任务） |
| 历史 v2.0/V1 兼容、损坏数据明确失败 | Q3 契约和旧路径 | 空轨迹、非法四元数、时间乱序、hash 错配及降级提示已有测试建设方向，尚未形成 Panda 回归证据 | Unverified（Q4 验证任务） |
| 资源与连续运行 | 任务计划 P-07/Q3 契约 | 冷/热加载、三次串行运行、内存/帧间隔/产物和释放标准已明确，尚未实测 | Unverified（Q4 验证任务） |

## 本次复核发现的测试设计问题

以下问题有具体依据，需保留并在 Q4 实现/验收前修正；它们不阻塞当前 Q3 限定进入，因为对应的契约已经给出责任模块、字段、判定标准和最小入口建设任务。

### F-Q3-D01（Major，Q4 核心行为测试增强）：接触证据尚未被 Panda 单测直接断言

- 证据：`tests/test_panda_task.py:21-34` 检查成功、抬升、释放、稳定时长、物体高度、夹爪开度和 `geom_poses` 数量，但未直接检查 `contacts` 中的双指—物体接触对/接触时段，也未检查接触期间双指与物体的相对运动和释放后的分离。
- 违反要求：PRD V2.8D 和 TC-01P/TC-02P 要区分控制指令与真实抓取结果，禁止用粘连或参数直接指定成功。
- 影响：最小测试可能漏掉“summary 成功但没有真实接触”或“使用固定约束替代接触”的实现错误。
- Q4 改进：使用 runner 已输出的 `contacts`、`gripper_width_m`、物体位姿和事件，在正常与受控失败各增加最小直接断言；检查禁止的工具—物体 weld/吸附不是成功依据。无需穷举扰动矩阵。
- 状态：Open，Q4 验收前必须关闭；不阻塞当前 Q3 限定进入。

### F-Q3-D02（Major，Q4 核心一致性测试增强）：尚未实际读取 Three.js 世界矩阵

- 证据：Q3 契约要求读取 Three.js 实际世界矩阵，与同一记录帧的编译几何姿态经已知轴变换后按位置 `≤1e-4 m`、旋转 `≤1e-3 rad` 对照；当前 `physical-frame.test.ts` 只覆盖旧简化位置投影，`verify_v2_browser.py` 仍只覆盖旧平面 payload/DOM 属性。
- 影响：DOM 数值正确不能排除网格局部原点、编译 mesh 变换、四元数顺序、轴变换或部件装配方向错误。
- Q4 改进：按契约增加 Panda Playwright/数值入口，在首帧、接触前后、抬升、释放和末帧读取实际 mesh world matrix，与 `scene.json`/`trajectory.jsonl` 同帧数据对照；截图只证明可见性，不替代矩阵对照。
- 状态：Open，Q4 验收前必须关闭；不阻塞当前 Q3 限定进入。

### F-Q3-D03（Major，Q4 恢复测试增强）：Panda 页面/资产失败恢复尚无运行证据

- 证据：现有 `test_v2_runtime.py:44-52` 仅覆盖旧平面 worker crash/timeout，`verify_v2_browser.py` 仅覆盖旧平面启动、切换和 WebGL fallback；Q3 契约要求 Panda 缺资产、模型/scene hash 错配、页面 poll 超时、异常无终态后收敛并可再次启动。
- 影响：Panda 页面可能在 CLI 可运行时轮询卡住、资产缺失时误用旧模型、异常后遗留 worker 或无法重试。
- Q4 改进：按已定义的 Panda CLI/页面责任入口分别验证一次 crash、timeout、缺资产或 hash mismatch，检查错误码/提示、进程回收、有效 summary 可读性和再次启动。保持单任务串行，不要求并发压力测试。
- 状态：Open，Q4 验收前必须关闭；不阻塞当前 Q3 限定进入。

## 真正阻塞 Q3 的判定

**本次复核没有发现仍然阻塞 Q3 限定进入的问题。**

按质量闭环，真正会阻塞 Q3 的是以下任一项：

- 连最小入口都不存在，无法定义由谁建立、如何运行和如何判定；
- 核心需求没有可观察字段、失败条件或通过/停止标准；
- 关键测试责任、隔离边界或失败处理无人负责，导致实现者无法据此自主验证；
- 入口存在但无法运行，且没有明确的最小建设任务和完成条件。

本次复核中，原先的 runner 缺口已由新增 `panda_runner.py` 和实际通过的 `test_panda_task.py` 解除；接触、矩阵和恢复虽尚未有最终 Q4 运行证据，但 Q3 契约已经明确了字段、所有者、标准和入口建设任务，因此应作为 Q4 交付前验证任务，而非当前 Q3 阻塞。

## Q2 同步观察（不替 Q2 放行）

- Q2 交接给出的模型来源、场景、判据、数据字段和运行边界作为本次 Q3 输入；本复核不重新批准资产来源、控制架构或数据契约。
- `python -m scripts.spike_panda` 的已记录证据支持 H1 运动/夹爪 Spike；新增 runner 和 Panda 单测支持 H2 最小任务入口，不外推为 Q2 或 Q4 的完整行为通过。
- 若 Q2 后续复核改变模型 hash、判据或字段所有权，须只对受影响的 Q4 测试设计和证据补做复核；不因本次 Q3 限定通过而继承放行。

## 本次复核运行证据与边界

已实际核验：

- `python -m unittest discover -s tests -p 'test_panda_task.py' -v`：1/1 通过。
- 新 runner 已实际存在，并输出契约规定的 `contacts`、`geom_poses`、`scene.json`、稳定判据和 summary 字段；本次仅核对最小入口，不将字段存在等同于完整 Q4 验收。
- 旧 `test_v2_runtime.py` 的 5/5 和前端既有单测 9/9 仍只作为历史平面/renderer 回归证据，不扩展到 Panda 完整页面。
- `python -m scripts.spike_panda`：沿用 Q2 交接记录，支持模型加载、运动、双指闭合和原生截图；脚本自身明确不宣称抓取验收。

本次未重跑、也不因未重跑而阻塞 Q3：Panda 页面 Playwright 旅程、实际 Three.js 矩阵对照、Panda 页面/资产失败恢复、损坏/错配数据和 P-07 资源基线；这些均保留为 Q4 交付前必须验证的范围。

## Q4 承接条件

1. 保留当前 `test_panda_task.py` 作为最小 H2 入口，在其上补齐 F-Q3-D01 的接触/释放直接断言。
2. 建立 F-Q3-D02 的真实 Three.js world matrix 对照，覆盖契约规定的关键记录帧和误差标准。
3. 建立 F-Q3-D03 的 Panda CLI/页面异常恢复回归，并补齐 model/scene hash、损坏数据、旧数据和资源基线的相关验证。
4. Q4 只需复核上述未关闭的实施证据和受影响回归，不重复完整 Q3 审查；不要求穷举所有扰动、浏览器、并发或真实机器人场景。

**最终交接状态：** H1 `Pass`；H2 `Pass for minimum entry`；H3 `Unverified pending Q4 implementation evidence`。Q3 门禁结论为 `Passed for limited scope`，允许进入 Q4，不等于 Panda 功能、页面一致性或整体 V2 放行。
