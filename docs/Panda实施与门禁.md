# Panda 实施与质量门记录

## 启动契约

- 2026-09-22 用户明确调用 ai-product-quality-loop，授权按完整任务计划实施；此前“本轮仅文档”阶段限制已结束。
- 权威范围：[PRD V2.8D](../PRD.md#v28d-完整机械臂与夹爪增量需求)、[完整任务计划](V2机械臂一致性接入任务计划.md)。既有未提交内容属于用户，保留不回滚；不发布远程、不购买服务、不更换系统或新增生产包依赖。
- 主执行者拥有代码、技术决策与共享台账；独立审查使用新鲜上下文子 Agent，默认 gpt-5.6-luna/medium。审查者仅写自己的报告，代码/台账只读。
- Q1/Q2/Q3 各最多初审 1 次＋阻断复审 1 次，每次 5 分钟；Q4 初审 1 次＋阻断复审最多 2 次，每次 10 分钟。未获得可计费金额，不宣称费用为零；以时间/次数限额控制。无输出/超时标 Review incomplete，不算通过。原审查通道不可用时，可用另一新鲜上下文审查者，计入同一次数上限；仍不可用仅暂停依赖其放行的范围。
- 普通实现缺陷由执行者定位修复和相关回归；实质目标变化、生产依赖改动或授权外行为询问用户。闭环 Skill 要求分门保存结果，不重复旧 VIS 已有效的审查。

### handoff-panda-start-01
- 结果：工程授权已恢复，进入 Q1 需求增量审查与 S1 前置准备；尚未宣称任一新模型行为通过。
- 决定：复用原生 MuJoCo/NumPy/Three.js，固定下载必要 Panda 模型与许可资产，不引入训练栈。
- 依据：完整任务计划、当前代码；Q1 报告预定为 `Panda-Q1需求审查.md`。
- 承接：主执行者准备模型验证入口，独立审查者核验新增需求可测试性；随后按 Q2/Q3/Q4 推进。

## Q2 增量执行契约

- 模型资产：`assets/robots/panda/`，上游 commit `822c2d8f877dd166c5b7d3c9f7e3c3b6589473b7`，71 个必需文件约 34 MB。`SOURCES.json` 保存来源和每文件 SHA256，原始 Apache-2.0 许可保留；获取入口验证 Git blob，已有不同文件不覆盖。
- `panda_model.py` 拥有模型来源校验、场景/判据和 IK。原生 Windows 中文路径使用已校验资源的内存虚拟文件系统，不修改系统编码或权限。
- 场景 `panda-cube-scene-1`：4 cm 方块、质量 0.04 kg、初始中心 `[.45,0,.021]m`、目标中心 `[.45,.20,.02]m`；物理步长 .002s。机器人内部双指同步关节约束保留，工具与物体间禁止 weld。
- 判据 `panda-contact-eval-1`：双指接触后抬升至少 .04m 并保持 .25s；实际夹爪间距至少 .06m 且双指与物体无接触才记释放；目标中心水平距离≤.04m、支撑高度误差≤.01m、线速度≤.03m/s、角速度≤.2rad/s 持续 .5s 才稳定。所有值在正式测试前冻结，调试控制动作不调整判定。
- `panda_runner.py` 拥有脚本阶段、动力学运行、事件和逐步判定；使用 IK 生成关节控制目标，物理运行中只写 ctrl，不改物体 qpos 或靠参数指定结果。故障注入保留但不参与正常对比。
- 兼容：现有 `SimulationConfig` 扩展 `model_id`（默认旧平面，保留旧调用），新增 Panda 分派；页面模型选择默认 Panda 并明确区分历史模型。每模型拥有自己的时限/帧采样，不把旧650步当作新任务长度。
- runner 输出原有六种产物及 `scene.json`、`performance.json`。`meta.artifact_schema=v2.1`、model identity、完整初始状态与控制/评估版本；`scene.json` 有内容哈希并由 meta 引用。旧 v2.0 沿用原解析。
- scene：`schema=panda-scene-1`、`model_hash`、`meshes`（id, vertices_b64 float32 LE, indices_b64 uint32 LE）、`geoms`（id, type=mesh/box/plane, mesh_id 或 null, size[3], rgba[4]）。只导出可视组，使用 MuJoCo 编译后的顶点和 geom 世界变换，不二次施加 mesh 编译偏移。
- trajectory：统一现有工具/物体/目标位置和 qpos/qvel，增加 `object_quaternion`、`gripper_width_m`、`contacts`、`geom_poses`（与 scene geoms 同顺序的 position[3]、quaternion[4]，wxyz）。采样后 `mj_forward` 对齐实际 data.time；保存控制输入。几何与采样率只影响显示，稳定判据每物理步计算。
- adapter：校验版本、运行ID、模型/scene哈希、帧长度、数值有限性、时间单调、四元数和映射。转换后保留旧 frames 供 SVG，Panda 附加 `robot_scene` 与 `robot_frames`。异常不能损害读取独立有效 summary 的能力。
- 前端：独立 robot-scene 模块解码网格；MuJoCo 世界整体绕 X 轴 -90°映射到 Three.js，所有部件使用后端完整姿态。整帧采样、不插值关节；工具/夹爪数字与几何取同一帧；首帧、夹取、抬升、释放和末帧均完整可见；支持镜头旋转缩放/复位。
- 前端最小可见对象：基座、7段机械臂、手掌、两根手指、方块、目标与地面。显示 run ID、model ID、实际采样时刻、阶段、夹爪间距及物体坐标；原生图像与网页分别检查装配、方向及双指可辨识。
- 进程：超时在 poll 路径也检查，CLI wait和页面复用；异常或无终态退出收敛，所有管道回收；单任务运行，状态读写沿用有限重试，不扩展多人并发。
- 比较：同模型hash、场景、评估/控制器版本及初始状态，唯一控制参数变化；不允许跨模型混比。按策略展示样本及结果；本批固定条件重复只支持调试与重复性，不宣称泛化或生产稳定性。
- 初始运行预算：单worker≤2GB，浏览器增量≤1GB；10s片段热运行≤30s；约1280×720视图目标30fps。资源不达标先优化，影响产品等待或画面可读性的取舍重新确认。

### handoff-panda-q2-spike-02
- 结果：Q1 独立审查限定通过，S1 原生模型运动/夹爪开合 Spike 自测通过；接触抓放与网页尚未验证。
- 决定：固定上游资产和场景/判据，采用编译后可视几何及逐帧世界姿态导出。
- 依据：`python -m scripts.spike_panda`，`.tmp-tests/panda-spike/result.json` 和 open/closed.png；MuJoCo3.13.0，5s仿真，首次测总耗时约0.84s（含初始化/两张渲染），不可外推完整任务性能。
- 承接：独立 Q2 复核来源/判据与方案，主执行者准备 Q3 的最小验证入口；模型指纹新增加场景XML哈希后需重新运行。

## Q3 验证入口与判定

- H1 模型入口已运行：`python -m scripts.spike_panda --output .tmp-tests/panda-spike`，模型完整加载、机械臂移动、双指闭合断言和原生截图。资产入口 `python scripts/fetch_panda_assets.py` 已完成，日常运行不下载。
- H2 任务入口建设中：`tests/test_panda_task.py` 先定义正式正常/偏移失败、实际抬升、夹爪开度、持续稳定和几何帧断言；runner 完成后用 `python -m unittest discover -s tests -p test_panda_task.py -v`。当前只声明测试设计可执行，未把不存在 runner 时标为通过。
- H2 契约/生命周期：扩展现有 `tests/test_v2_runtime.py`，独立临时目录准备样本，验证 model_id 分派、两版可比性、跨模型拒绝、异常/缺失终态、页面同用 poll 超时；新数据校验测试覆盖模型/scene哈希、损坏/空轨迹、姿态与时间。
- H3 待新增 Panda 浏览器入口，复用 `scripts/verify_v2_browser.py` 的真实 Playwright 路径；前端构建后启动隔离端口，不覆盖旧服务。每用例自行启动或导入对应产物，记录源码/构建指纹及运行ID。
- 几何验收不仅读 DOM：读取 Three.js 实际世界矩阵，和产物中的编译几何姿态经已知轴变换后对照，位置误差≤1e-4m、旋转角差≤1e-3rad。首帧/双指接触前后/抬升/释放/末帧同时做原生截图和网页视觉核对。
- 显示验收：全机主体占主视区可辨范围，手指开合可见，物体不被遮挡；支持镜头缩放旋转/复位，阶段/采样秒数/夹爪间距/物体坐标可读；检查降级不声称完整机器人。
- 资源：模型加载冷/热记录；至少3次每策略串行运行，记录 worker 峰值内存、产物大小，浏览器实际进程组增量与帧间隔；防止遗留进程和几何资源。内存统计可用本机已有诊断工具，不新增生产包。
- 回归最低范围：Python全量（旧22项＋新增）、前端类型/测试/build、旧平面浏览器冒烟、新Panda完整旅程与异常恢复；物理层、坐标变换层、真实页面分别验证不同风险。
- 阻断：接触抓放不成立、伪造结果、姿态不一致、模型/数据错配、失败无法恢复、旧数据损坏。无相关变更的V1无需重审全部页面。普通错误自行修复，不降低测试期望。
- 证据隔离：调试产物写 `.tmp-tests/panda-*`，正式验收写独立运行目录和 `docs/evidence/panda-*`；不删除历史用户数据。尚未实现的测试入口由本批主执行者建立并自测，不交由用户补写。

### handoff-panda-q4-entry-03
- 结果：Q1/Q2/Q3 增量独立审查限定通过，进入 Q4；正式网页行为仍待验证。
- 依据：[Q1](Panda-Q1需求审查.md)、[Q2](Panda-Q2架构审查.md)、[Q3](Panda-Q3测试审查.md)。Q2 来源清单换源风险已通过独立指纹锁定/篡改测试关闭；真实接触任务3项测试通过。
- 物理自测：`.tmp-tests/panda-physics/results.json`，两策略各3轮固定条件重复，正常均成功、偏移均失败；14s仿真单次墙钟约1.2～1.8s，原生关键帧按记录qpos还原并核对geom位置。不作为泛化成功率。
- 分工：主执行者拥有模型/控制/adapter/页面/浏览器验证和台账；后端执行者仅runtime/worker/CLI/专属测试，记录 `Panda后端执行记录.md`；前端执行者仅physical/payload/robot-scene/相关测试，记录 `Panda前端执行记录.md`。共享文件不并发修改。
- 承接：完成端到端页面、矩阵数值、异常数据/超时/恢复和资源验证，再进入限定Q4独立审查；旧VIS不替新模型放行。

## 运行与复验

```powershell
# 资产已随仓库保存；缺失时才获取固定版本。不同内容不会被静默覆盖。
python scripts/fetch_panda_assets.py
npm run build --prefix web/robot_renderer
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8516

# CLI 默认仍为历史平面任务，Panda 需明确选择模型
python -m robot_mvp.v2_cli run --model panda-cube-v1 --strategy baseline --timeout 30
python -m robot_mvp.v2_cli run --model panda-cube-v1 --strategy offset-grasp --grasp-offset 0.08 --timeout 30
python -m robot_mvp.v2_cli compare data/v2_runs/<run-a> data/v2_runs/<run-b>

python -m unittest discover -s tests -v
npm run check --prefix web/robot_renderer
npm run test --prefix web/robot_renderer
```

页面进入“V2 物理仿真”，选择“Panda 机械臂与夹爪”，点击启动；运行后可播放、暂停、拖动、选事件、缩放旋转和复位镜头。再次运行偏移版后，在本页下方选择同模型运行并生成比较报告。旧平面任务保留但不会默认混入 Panda 比较。

浏览器包含故障恢复的验收需在**单独诊断服务**启用开关；日常服务不需要：

```powershell
$env:ROBOTS_ENABLE_FAULT_TESTS='1'
python -m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port 8517
# 另一个终端，使用本机已有 Playwright / psutil 验收库
python scripts/verify_panda_browser.py --url http://127.0.0.1:8517 --evidence .tmp-tests/panda-browser-check
python scripts/verify_v2_browser.py --url http://127.0.0.1:8516 --evidence .tmp-tests/legacy-check
```

物理重复与原生对照：`python -m scripts.verify_panda_physics --output <新的空运行目录> --evidence <证据目录>`。运行目录不能复用已存在的同名 run，以避免覆盖证据；原始轨迹留在 output，仅摘要和截图复制至 evidence。

### handoff-panda-integration-04
- 结果：Q4 作者集成自测通过，独立 Q4 审查进行中；暂不宣布最终放行。
- 完成：同源完整机械臂/夹爪、实际接触任务、单帧回放、页面比较、模型/损坏数据拒绝、报告与回放失败隔离、页面/CLI 超时及终态资源回收。
- 依据：[物理六轮独立worker](evidence/panda-workers-20260922/results.json)、[Panda八组浏览器验收](evidence/panda-browser-20260922/results.json)、[旧平面四组浏览器回归](evidence/panda-legacy-20260922/results.json)。Python42项、前端13项和类型/build通过；逐步证据见后端/前端执行记录。
- 资源：本机6次独立worker执行14s仿真，墙钟约2.05～5.11s，峰值工作集约291～292MiB；每次产物约12.6MiB。Panda浏览器测量窗口中 RAF 中位33.2ms、P95 33.4ms；两次回放后的专用Chromium进程组RSS增量约419MiB（共享页可能重复计数，不是系统整体峰值/长稳测试）。
- 承接：独立审查只验证本批差异与未覆盖相关风险；通过后补齐最终范围、台账和运行入口，不将结果外推到真机或用户价值。

源码/构建证据：工作区基线 HEAD `f02f6d8`，包含既有未提交改动，无提交/推送。上述作者浏览器使用 bundle SHA256 `541b98f26439f9617321b99dff3185b22e622573324b83667e2aa8abe61d8adf`；物理来源指纹已写入 worker 证据 JSON。模型来源清单指纹校验只归一化 CRLF/LF，模型资产仍逐文件按原始字节哈希核对，避免跨系统文本行尾改变来源判定。

### handoff-panda-q4-fix-05
- 结果：独立 Q4 初审 Changes required；当前唯一核心阻断为比较输入完整性 F-Q4-01，修复由后端执行者负责。既有物理/回放/页面恢复结论保留。
- 依据：[独立初审](Panda-Q4交付审查.md#handoff-panda-q4-review-01)。比较需要读取并验证实际scene/trajectory/events及结果终态一致，不能只信meta/summary。
- 资源口径更正：早期 `panda-physics-20260922` 是同一个作者测试进程直接运行并渲染截图，峰值包含父进程渲染器；[说明](evidence/panda-physics-20260922/README.md)。独立worker基线以 [PID核对后六轮结果](evidence/panda-workers-audited-20260922/results.json) 为准：每条performance PID均等于对应JobHandle子进程且不同于截图父进程，约291～292MiB；本轮墙钟约1.76～8.63s/14s仿真，系统负载不同，不合并为保证值。
- 补证：真实 `WEBGL_lose_context` 上下文丢失后同刻降级并继续播放通过，见 [context-loss](evidence/panda-browser-20260922/context-loss.json)；缺单个mesh在隔离副本的来源校验中明确拒绝，不删除用户在用资产。尚不宣称实际删除在用模型后的页面恢复已覆盖。
- 承接：比较修复及直接回归通过后申请第一次限定复核，不重跑已有效的全部视觉/物理审查。

### handoff-panda-delivery-06
- 结果：2026-09-22，S1～S6 本批交付完成；独立 Q4 = **Passed for limited scope**，F-Q4-01 已复核关闭。结论见 [Q4复核](Panda-Q4交付审查.md#handoff-panda-q4-review-02)。
- 完成：本地 Panda 双指接触抓放；同源61个可视几何、421帧/14s回放；正常与偏移失败、页面比较、产物校验/拒绝统计、worker异常/超时/终态回收、旧平面兼容。未新增生产包依赖，未提交或推送。
- 验证：最终全量 Python46项、前端13项与类型/build；Panda8组独立浏览器旅程、6关键帧实际mesh姿态核对、真实context-loss补测、比较完整性修复后的定向页面回归、旧平面4组浏览器回归；独立worker两版各3轮。必要验证已满足，停止扩张检查。
- 资源：以 [PID审计后结果](evidence/panda-workers-audited-20260922/results.json) 为唯一worker基线，本机峰值约291～292MiB，14s仿真墙钟约1.76～8.63s；浏览器作者测量窗口约30fps、两次回放RSS增量约419MiB，独立复测约631MB，均属有界窗口而非长期或并发容量保证。
- 交付入口：按上方“运行与复验”启动；当前普通服务使用本机8516。诊断模式仅用于验收，交付时关闭8517诊断服务；历史数据和正式证据保留。

### 最终证据与限制

| 证据 | 适用范围 |
|---|---|
| [Q4初审与限定复核](Panda-Q4交付审查.md) | 初审发现比较输入完整性漏洞，修复后独立关闭；不替代真实用户/生产验证 |
| [Panda浏览器8组](evidence/panda-browser-20260922/results.json) | 正常、偏移、回放与实际mesh、比较、crash/timeout和再次运行、WebGL不可用 |
| [真实上下文丢失](evidence/panda-browser-20260922/context-loss.json) | 同时刻降级SVG并能继续播放，不作为完整3D可用 |
| [比较修复页面回归](evidence/panda-browser-20260922/comparison-regression.json) | 完整性校验接入后合法记录仍可从页面生成/下载报告；损坏输入由专属测试与独立复现验证 |
| [worker重复与资源](evidence/panda-workers-audited-20260922/results.json) | 固定初始状态、独立进程PID核对；不是多场景成功率 |
| [旧平面回归](evidence/panda-legacy-20260922/results.json) | 历史播放/切换/事件/连续启动/降级及V1总览，不覆盖所有V1页面 |
| [后端执行](Panda后端执行记录.md) / [前端执行](Panda前端执行记录.md) | 相关代码、测试命令、已修复问题与各自证据边界 |

未验证：其他浏览器、窄屏/辅助技术、多会话并发和长期资源稳定性；真实用户收益、视觉感知误差、真机与 sim-to-real；实际删除在用模型资产后的完整页面恢复旅程（隔离副本缺mesh拒绝已测，通用worker错误/页面再次启动已测，不能合并冒称该特定完整旅程通过）。全量测试退出曾出现 Streamlit/AppTest 临时目录隐式清理 warning；runtime严格资源警告测试没有遗留子进程/管道警告，不将框架warning写成已消除。

获取或校验模型失败时运行固定资产获取入口；已有不同内容会报错而不是覆盖。scene/轨迹损坏时显示不可回放，已有独立有效summary仍可查但标记未核对轨迹；比较拒绝损坏输入。bundle缺失时先构建，不把报告可读误称为完整模型可用。

收口检查：普通服务8516健康检查为ok，8517诊断服务已关闭；清理本批两组无后续用途的中间失败截图（未保留回收副本，可通过验证脚本重建），未删除用户数据或正式验收证据。台账和差异检查通过。当前Streamlit1.56.0对既有`components.v1.html`打印弃用告警，但实际浏览器入口可运行；迁移列入后续维护，未擅自升级生产依赖。
