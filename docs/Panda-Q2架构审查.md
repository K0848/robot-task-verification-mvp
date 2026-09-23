# Panda Q2 架构审查

### handoff-panda-q2-review-01

- 审查类型：独立 Q2 架构/研发初审；审查者按本轮新鲜上下文自行读取权威材料、源码和 Spike 产物。
- 时间边界：按实施门禁约定执行 5 分钟初审；未进行代码修改、依赖安装、外发或远程发布。
- 权威输入：`PRD.md` 的 V2.8D、`docs/V2机械臂一致性接入任务计划.md`、`docs/Panda实施与门禁.md` 的 Q2 增量执行契约、`docs/Panda-Q1需求审查.md`、`robot_mvp/panda_model.py`、`scripts/fetch_panda_assets.py`、`scripts/spike_panda.py` 及原生 Spike 产物。
- 审查范围：模型来源/关键依赖、编译几何与姿态契约、抓取/成功规则、兼容/超时/数据所有权；不把尚未实现的完整功能 E2E 当作本轮必需证据。
- 初审结论：**Changes required**；本次唯一复审结论：**Passed for limited scope**。
- 结论边界：初审时把建设中的 runner 缺失列为 Q2-01；复核时 `panda_runner.py` 已新增，正常/受控失败最小测试和来源清单篡改测试均通过。Q2-01、Q2-02 及其直接影响在声明范围内关闭，允许进入 Q3/实现准备；不代表全部后续功能 E2E 已实现或通过。

### handoff-panda-q2-review-02

- 类型：Q2 唯一限定复审结果的新交接锚点；保留上方 `handoff-panda-q2-review-01` 作为初审历史入口，不覆盖初审记录。
- 复审范围：仅核对 Q2-01、Q2-02 及直接影响；不扩展到后续未实现功能，不重复运行测试。
- 结果：**Passed for limited scope**。
- 复审变化：runner 已新增并通过既有最小正常/受控失败测试；模型仅使用双指 joint 同步约束、无 object weld；`SOURCE_MANIFEST_SHA256` 锁定完整 `SOURCES.json`，篡改清单被拒绝。
- 放行边界：允许进入 Q3/实现准备；网页 adapter、完整兼容、超时、比较、资源和完整 E2E 仍按报告中的未验证范围保留。

## 1. 覆盖与证据

| 检查项 | 结论 | 证据 |
|---|---|---|
| 上游来源、许可、资产哈希 | Pass（来源文件层面） | `assets/robots/panda/SOURCES.json` 声明 Menagerie commit `822c2d8f877dd166c5b7d3c9f7e3c3b6589473b7`、Apache-2.0 和 71 个 SHA256；`panda_model.source_manifest()` 对清单文件逐项校验；目录实际 72 个文件，其中第 72 个为清单自身。 |
| 本机关键依赖与原生加载 | Pass（限 S1） | `python -m scripts.spike_panda --output .tmp-tests/panda-q2-independent` 成功；MuJoCo 3.13.0，5 秒仿真，加载约 0.263 秒，总墙钟约 0.828 秒，有限数值通过，`nq=16`、84 geoms、67 meshes。 |
| 原生几何可见性 | Pass（限原生关键帧） | `.tmp-tests/panda-q2-independent/open.png`、`closed.png` 可见完整 Panda 基座、7 段机械臂、手掌、双指、方块、目标和地面；开合状态可辨识。此证据不证明网页姿态一致。 |
| 编译后几何与姿态方案 | Unverified | `load_model()` 使用同一份经校验网格通过 MuJoCo XML 虚拟文件系统编译，Spike 能渲染；但尚无 `scene.json`/`geom_poses` 导出、四元数转换和 Three.js 数值对照证据。 |
| 接触抓取与成功规则 | Pass（最小测试范围）/ Unverified（完整后续验收） | `tests.test_panda_task` 通过；含双指直接接触力、抬升保持、释放间距/脱离、稳定末半秒位置速度断言，并确认模型没有 object weld。正式 TC-01P/02P 证据包仍属后续范围；Spike 仍明确 scope 为“not grasp acceptance”。 |
| 兼容、超时、数据所有权 | Pass（Q2 直接影响）/ Unverified（后续接线） | runner 生成 v2.1 产物并由物理运行拥有接触/判定；CLI/page 超时、adapter 接线、网页回放和旧数据兼容仍不在本次复审。 |
| F03 可见性补充及后续测试可行性 | Pass（契约层）；Unverified（执行层） | `docs/Panda实施与门禁.md` 已明确最小可见对象、run/model ID、采样时刻、阶段、夹爪间距、物体坐标和首帧/夹取/抬升/释放/末帧；TC-05P 可据此设计数值和截图断言，当前已有产物入口但 adapter/页面尚未接通。 |

## 2. 前置冻结问题核对

### F01 模型来源

- 状态：**Resolved（前置冻结层）**。
- 已核对：固定 commit、仓库目录、Apache-2.0、项目内许可证、71 个清单文件及本地哈希；加载器禁止资产路径越界，并通过内存 assets 加载，满足中文 Windows 路径的既定边界。
- 未宣称：这只证明当前文件与当前 `SOURCES.json` 一致，不证明网页导出或完整任务行为。

### F02 成功阈值

- 状态：**Resolved（前置冻结层）**。
- 已冻结：4 cm 方块、0.04 kg、初始/目标位置、0.002 s 物理步长；抬升 0.04 m 并保持 0.25 s；释放间距至少 0.06 m；目标水平距离不超过 0.04 m、支撑高度误差不超过 0.01 m、线速度不超过 0.03 m/s、角速度不超过 0.2 rad/s，稳定 0.5 s。
- 仍未验证：这些值是否被真实 Panda 评估器按物理步计算并写入产物；不能把冻结视为一次成功运行。

### F03 可见性

- 状态：**Resolved（Q2 契约补充）；Open（S4 实现验收）**。
- Q2 已补充的可观察契约：基座、7 段机械臂、手掌、双指、方块、目标、地面；显示 run ID、model ID、实际采样时刻、阶段、夹爪间距、物体坐标；原生和网页分别检查装配、方向、双指可辨识；关键帧覆盖首帧、夹取、抬升、释放和末帧。
- 后续测试可行性：可拆成 `scene`/`trajectory` 字段断言、同帧位置/四元数数值对照、关键帧截图和降级边界测试；runner 和 v2.1 产物入口已具备，进入 Q3/实现准备。

## 3. 阻断问题

### Q2-01 · Blocker（初审发现，复审关闭）：Panda 执行入口缺失，后续 S2/Q3 无法启动

- 违反契约：Q2 契约及 `v2_physics.py` 规定 `model_id="panda-cube-v1"` 分派至 Panda runner；S2 需要可执行接触抓放和成功评估入口，Q3 需要据此定义最小验证入口。
- 初审证据：当时 `panda_runner.py` 不存在，测试报 `ModuleNotFoundError`；该历史记录保留，不把建设中缺失误写成永久架构结论。
- 复审证据：当前 runner 已存在；`python -m unittest tests.test_panda_task -v` 通过 3 tests / 2.266 秒，包含正常/受控失败、直接接触力、释放间距、稳定末半秒位置速度、无 object weld 和无 `grasp_lock` 断言。
- 处置：**Resolved / closed for Q2 limited scope**。允许进入 Q3/实现准备；完整 TC-01P/02P、adapter、页面和超时验收仍按原未验证边界保留。

### Q2-02 · Major（初审发现，复审关闭）：来源清单可被整体替换，加载器未强制固定上游身份

- 违反契约：固定 commit、仓库、目录和 Apache-2.0 应是模型来源校验的一部分，而不只依赖可编辑清单中的哈希。
- 初审证据：加载器只按清单内容校验，清单可与资产同批替换；该历史风险保留。
- 复审证据：`panda_model.py` 新增独立代码常量 `SOURCE_MANIFEST_SHA256`，锁定由固定 Git blob 获取脚本生成的整个 `SOURCES.json`；独立计算结果与常量一致（`029e6727…acd02`）。`test_replaced_source_manifest_is_rejected` 通过，篡改 commit 的清单被拒绝；固定资产逐文件 SHA256 校验和 `fetch_panda_assets.py` 的 Git blob 校验仍保留。
- 处置：**Resolved / closed for Q2 limited scope**。模型身份整体换源风险在本门关闭；后续仍可在 Q3/Q4 继续覆盖损坏输入和运行产物校验，但不重新打开本 Q2 项。

## 4. 契约与所有权审查

- 模型加载器：拥有资产路径、冻结清单指纹、场景配置和模型身份；runner 已输出 scene manifest，完整前端姿态消费仍后续验证。
- 物理运行/评估器：runner 拥有控制、接触力、事件和逐步判定；本次测试证明最小正常/受控失败链路可运行。
- adapter/产物：runner 已生成 v2.1 文件；adapter、网页和损坏输入校验仍保留为后续未验证，不作为本次 Q2-01/02 阻断。
- renderer：Q2 契约要求以后端完整姿态逐帧显示，不自行 IK、插值或吸附；现有前端仍包含旧平面示意路径，不能作为 Panda 几何一致性证据。
- 生命周期：旧 `wait()` 测试和已有页面 `poll()` 路径不等于 Panda 已接通；TC-03P 仍需分别验证 CLI 和页面超时、无终态收敛、管道回收和再次启动。
- 比较：契约已规定同模型 hash、场景、评估/控制器版本和初始状态；当前没有 Panda meta/summary，无法证明比较器实施了这些拒绝条件。

## 5. 门禁、覆盖与未验证

### 门禁结论

**Passed for limited scope**。Q2-01 runner 入口和最小物理测试已复核通过；Q2-02 清单整体指纹锁定及篡改拒绝已复核通过。该结论仅允许进入 Q3/实现准备，不等于完整 Panda 网页、超时、兼容、比较或 E2E 验收通过。

### 已覆盖

- 权威 PRD V2.8D、Q2 任务计划、实施门禁和 Q1 报告的范围/约束/前置问题。
- `panda_model.py` 的场景、阈值、资产校验、虚拟文件系统、IK 入口和模型身份生成。
- `fetch_panda_assets.py` 的固定上游 commit、Git blob 校验、不覆盖不同既有文件逻辑。
- 原生 Spike 的加载、运动、双指闭合、有限数值和两张关键帧图像。
- Q1 F01/F02 前置冻结状态及 Q1 F03 在 Q2 契约中的最小可见对象/字段/关键阶段补充。

### 未验证或明确不在本轮

- 正式 TC-01P/TC-02P 证据包、原生关键帧和完整后续验收；本次最小测试已覆盖直接接触力、释放间距和稳定末半秒断言。
- v2.1 meta/scene/trajectory/events/summary 的实际生成、校验和损坏数据拒绝。
- 编译 mesh 局部原点、缩放、世界姿态、四元数 wxyz 到 Three.js 的实际转换和数值一致性。
- 网页 TC-05P、WebGL 降级、页面轮询超时、资源释放、连续运行不串数据。
- TC-04P 比较保护、P-06 旧数据兼容、P-07 资源预算和 30 fps 目标。
- 真实完整任务性能；Spike 的约 0.828 秒仅是 5 秒运动/闭合片段，不能外推正式任务。

## 6. 承接

1. 进入 Q3/实现准备时，以实际 Panda v2.1 产物验证 F03 的同帧数值断言、关键帧可见性、降级边界和 CLI/页面超时入口。
2. 保留不使用 object weld、qpos 直接搬运或末帧参数指定成功的约束；后续若发现违反，只复审受影响范围。
4. 本报告不修改代码、不安装依赖、不外发；后续只复审未关闭阻断项及其直接影响范围。
