# Panda 后端执行记录

### handoff-panda-runtime-01

#### 命令与结果

- `python -m unittest tests.test_panda_runtime tests.test_v2_runtime tests.test_panda_task -v`：13/13 通过。
- `python -m unittest tests.test_panda_runtime tests.test_v2_runtime -q`：10/10 通过。
- `python -m robot_mvp.v2_cli run --model unknown-model --timeout 1`：按预期退出码 2，输出结构化 `invalid_config`，未启动 worker。
- `python -c "from robot_mvp.v2_runtime import new_config; print(new_config(model_id='panda-cube-v1').to_dict())"`：确认 Panda 默认 `max_steps=7000`、`initial_object_x=.45`、`target_x=.45`、`wall_timeout_s=30.0`。
- `git diff --check -- robot_mvp/v2_runtime.py robot_mvp/v2_worker.py robot_mvp/v2_cli.py tests/test_panda_runtime.py`：通过。

#### 变化

- `new_config(model_id="panda-cube-v1")` 使用 Panda 默认任务参数；未指定模型时保持旧平面任务默认值和旧返回字段。
- 增加集中配置校验：模型 ID、有限数值、正 `max_steps`、正 `wall_timeout_s` 和故障模式均在启动前校验；未知模型不会静默回退。
- `V2JobManager.poll()` 增加墙钟超时检查，不依赖 `wait()`；超时、worker 崩溃、退出但没有终态时都会停止/回收进程并返回结构化错误。管道在回收路径关闭，超时后的后续任务可以再次启动。
- CLI 增加 `--model`，默认保持旧模型；`--timeout` 同时映射到 `SimulationConfig.wall_timeout_s` 和等待上限。
- 比较报告校验模型 hash、场景 hash、评估口径、控制器版本和初始状态；除 `grasp_offset` 外的受控配置差异不得形成优劣结论。结果按策略分组，固定初始状态重复标注为重复性检查，不支持泛化结论；旧 TC04 字段继续保留。
- 新增真实 worker 回归：Panda 正常/受控失败、`poll()` 墙钟超时、崩溃、缺失终态、超时后再启动和模型不匹配比较。

#### 已确认

- Panda 真实 worker 正常运行和 `grasp_offset=.08` 受控失败均通过；已有 Panda 物理接触抓放测试通过。
- 旧 `tests/test_v2_runtime.py` 全部通过，未破坏旧平面路径和 TC04 返回字段。
- 没有安装依赖、没有启动可见窗口，也没有修改 `v2_physics.py`、`panda_model.py`、`panda_runner.py`、`v2_adapter.py`、`app.py`、前端或台账文件。

#### 未验证

- 本次仅覆盖后端生命周期与比较边界；未执行浏览器页面端到端、Three.js 矩阵对照、前端资源基线和完整 Q4 页面验收。
- 未做多人并发、真实机器人、视觉误差、sim-to-real 或生产稳定性验证；比较结论仍限于相同模型、场景、评估/控制器版本和声明的仿真样本。
- 测试过程曾观察到 Windows subprocess `ResourceWarning`，发生在被测试进程启动/强制终止竞态期间；终态测试最终通过，回收路径已补充 kill 后 wait 和管道关闭，未将该警告扩大为功能通过证据。

### handoff-panda-runtime-02

#### 命令与结果

- `python -m unittest tests.test_panda_runtime tests.test_v2_runtime tests.test_panda_task -v`：15/15 通过。
- 新增配置边界测试：字符串数值、`bool` 数值、`../escape` 和 `C:\\escape` 均在启动前拒绝。
- 新增 Panda 畸形报告测试：缺失 `model_hash`、`summary.success` 非 bool、`summary.run_id` 串接其他 artifact 时，比较状态为 `rejected`，不产生优劣结论。

#### 变化

- `validate_config()` 只接受有限的 `int`/`float` 数值，明确排除 `bool` 和可被 `float()` 隐式转换的字符串；`max_steps` 仍只接受非 bool 正整数。
- `run_id` 必须是非空安全单目录名，拒绝 `.`、`..`、路径分隔符、绝对路径和盘符，避免 `ArtifactStore.create()` 越过 artifacts root。
- Panda 比较现在要求 `model_hash`、`scene_sha256`、`evaluation`、`controller_version`、`initial_state` 和 `run_id` 相关身份数据存在；逐 artifact 校验 meta/config/summary 的 run ID 一致、artifact 目录名一致且 `summary.success` 为 bool。
- 缺失或畸形 Panda 身份数据进入 `identity_differences.malformed_panda_report` 并拒绝比较；不再把双方缺失字段的 `None` 当作一致。

#### 未扩展范围

- 仅修改 runtime、专属测试和本执行记录；未修改 worker、CLI、物理、模型、runner、adapter、app、前端或台账。
- 未新增依赖，未启动可见窗口；浏览器端到端、前端矩阵/资源和真实机器人验证仍沿用上一锚点的未验证边界。

#### 02 生命周期资源修复补充

- 原因：`poll()` 可能在 worker 已写入 `failed`/其他终态、但子进程尚未完成退出时直接返回，导致终态 handle 的进程和 stdout/stderr 管道仍存活。
- 修复：`poll()` 在观察到终态但 `process.poll()` 仍为 `None` 时，先调用统一 `_reap()`；终态返回前保证进程退出并关闭 stdout/stderr。超时路径继续执行 terminate/kill 后 wait。
- 资源断言：`tests/test_panda_runtime.py` 对正常、失败、墙钟超时、后续启动、崩溃、缺失终态及比较使用的终态 handle 均断言进程已退出且 stdout/stderr 已关闭。
- `python -W error::ResourceWarning -m unittest tests.test_panda_runtime tests.test_v2_runtime -q`：12/12 通过，退出码 0，未出现 subprocess 或管道 ResourceWarning。
- `python -W error::ResourceWarning -m unittest discover -s tests -v`：42/42 通过，退出码 0；全量退出阶段仍有既有 `TemporaryDirectory` 隐式清理 warning，来源不在本次授权生命周期文件，未将其伪报为本次 subprocess 修复已消除。后端生命周期定向回归无该 warning。

#### 02 终态日志顺序补充

- worker 异常路径改为先写入并关闭 `error.log`，再发布 `status=failed`；因此父进程看到失败终态并开始回收时，完整 traceback 已经落盘。
- 终态回收改为先自然等待 `0.25s`，仅在 worker 未自行退出时才 terminate/kill，避免成功尾部或错误日志写入被提前中断。
- Crash 回归增加 `error.log` 存在且非空断言；资源断言继续确认所有终态 handle 的进程退出和 stdout/stderr 关闭。
- `python -W error::ResourceWarning -m unittest tests.test_panda_runtime tests.test_v2_runtime -q`：12/12 通过，退出码 0。
- `python -W error::ResourceWarning -m unittest discover -s tests -q`：42/42 通过，退出码 0；仍观察到全量退出阶段既有 `TemporaryDirectory` 隐式清理 warning，非 subprocess/管道 warning，也不属于本次生命周期授权文件。

### handoff-panda-runtime-03

#### F-Q4-01 修复

- Panda 参与比较前调用主控已有的 `robot_mvp.panda_artifacts.validate_panda(artifact_dir, meta, summary, frames, events)`；runtime 读取并传入实际 `scene.json`、`trajectory.jsonl` 和 `events.jsonl`，不复制 helper 校验逻辑。
- scene 损坏、轨迹缺失/非法、events JSON 损坏、`summary.success` 与 `final_status` 冲突、运行 ID/时长/帧或事件边界异常都会返回结构化 `comparison_status=rejected` 和 `rejected_samples[].reason`。
- 无效样本不会进入 `sample_count`、`success_count`、`success_rate` 或 `strategy_groups`；统计值使用 `None` 表示未知，不用 0 伪装实际结果。
- 正常同条件 Panda 样本仍可比较；旧平面 TC04 继续使用原有字段和统计路径。

#### 命令与结果

- `python -W error::ResourceWarning -m unittest tests.test_panda_runtime tests.test_v2_runtime -q`：14/14 通过，退出码 0。
- `python -W error::ResourceWarning -m unittest discover -s tests -q`：46/46 通过，退出码 0；新增 4 项比较完整性用例后总数由 42 增至 46。
- 覆盖 `.tmp-tests/panda-q4-compare-corrupt-scene/`：损坏 scene 被 rejected。
- 覆盖 `.tmp-tests/panda-q4-compare-invalid2/`：success/final_status 冲突被 rejected。
- 专属测试另覆盖独立 scene 损坏、trajectory 缺失、trajectory 非法 JSON、events 非法 JSON、结果冲突和正常同条件比较。
- `git diff --check -- robot_mvp/v2_runtime.py tests/test_panda_runtime.py docs/Panda后端执行记录.md`：通过。

#### 未验证与边界

- 本次只修复比较输入完整性及直接回归；未修改 `panda_artifacts.py` helper 或其他 ownership 文件。
- 全量测试退出阶段仍观察到既有 `TemporaryDirectory` 隐式清理 warning；定向 runtime/Panda 回归在 `-W error::ResourceWarning` 下无 subprocess、stdout/stderr 或终态 handle 资源警告。
- Q4 资源测量口径、缺失资产完整页面旅程和独立复核仍由主控负责，不在本交接中宣称完成。
