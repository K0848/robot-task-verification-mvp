# 🤖 仿真机械臂任务验证平台 MVP

> 一条完整的 Pick & Place 任务验证闭环，用产品化视角把"启动 → 监控 → 复盘 → 对比 → 评测"收敛成一个可演示的仪表盘。

<p align="center">
  <strong>Python + Streamlit + MuJoCo + Three.js · 单机运行 · V1 演示 + V2 真实仿真产物</strong>
</p>

---

## ✨ 亮点特性

| 模块 | 能力 |
|------|------|
| **任务启动** | 选择策略版本 + 预设场景 + 备注关键词（系统自动解析为节奏/聚焦模式） |
| **实时监控** | 2.5D Three.js 机械臂动画 · HUD 布局 · 暂停/继续控制 · 秒级自动刷新 |
| **失败复盘** | 帧级回放 · 时间线定位 · 结构化结论（失败原因 + 关键观察） |
| **版本对比** | 双运行并排比较 · 透明推荐规则（成功优先 → 耗时优先 → 失败推后优先） |
| **基准评测** | 按评测套件批量运行 · 成功率/平均耗时/失败分布/最弱案例一键汇总 |
| **3D 渲染** | 独立 Three.js bundle · 机械臂关节动画 · 夹爪开合 · 物体 snap 跟随 · SVG 自动降级 |
| **V2 物理仿真** | 独立 MuJoCo worker · status 轮询 · 运行 artifact · 受控失败 · 真实轨迹适配 |

## 🎯 适合展示的能力

- 🏗️ 机器人软件产品规划与 MVP 落地
- 🔄 任务验证流程梳理和页面抽象
- 📊 运行数据结构化沉淀与可解释结论
- 🔍 失败案例复盘与策略迭代对比

---

## 🎥 演示视频

[▶ 点击观看 Bilibili 演示视频](https://www.bilibili.com/video/BV1BdSfBXESe/)

> 视频展示了完整的 Pick & Place 任务验证流程，包括实时监控、失败复盘、版本对比和基准评测功能。

---

## 📐 项目结构

```text
.
├── app.py                         # Streamlit 主应用入口
├── requirements.txt               # Python 依赖
├── start.bat                      # Windows 一键启动
│
├── robot_mvp/                     # 核心业务包
│   ├── models.py                  #   数据模型（8 个 dataclass）
│   ├── simulator.py               #   场景模拟 · 帧生成 · 状态投影 · 评测汇总
│   ├── storage.py                 #   JSON 持久化层
│   ├── renderer.py                #   Three.js 桥接 + SVG 回退
│   ├── v2_physics.py              #   V2 原生 MuJoCo 任务与成功判定
│   ├── v2_worker.py               #   独立物理执行进程
│   ├── v2_runtime.py              #   worker 生命周期、artifact、比较
│   ├── v2_adapter.py              #   V2 真实轨迹 → 展示 payload
│   └── v2_cli.py                  #   V2 最小验证入口
│
├── web/robot_renderer/            # 独立前端渲染子项目
│   ├── src/
│   │   ├── index.ts               #   Three.js 2.5D 场景
│   │   └── payload.ts             #   渲染协议 · 帧采样 · 动画计算
│   └── tests/
│       └── payload.test.ts        #   前端单测
│
├── tests/
│   ├── test_simulator.py          # V1 Python 单测（17 项）
│   └── test_v2_runtime.py         # V2 worker/产物/比较/回放（5 项）
│
├── data/                          # 运行时数据（首次启动自动生成）
│   └── store.json
├── data/v2_runs/                  # V2 独立运行产物（不混入 store.json）
│
└── md/                            # 项目文档
```

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+（仅 3D 渲染开发时需要）

### 安装 & 启动

```bash
# 1. 克隆仓库
git clone https://github.com/K0848/robot-task-verification-mvp.git
cd robot-task-verification-mvp

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 启动应用
streamlit run app.py
```

V2 Panda 机械臂与夹爪（单方块接触抓放）入口：

```bash
# 仓库自带固定模型资产；仅在资产缺失时获取，不下载数据集
python scripts/fetch_panda_assets.py
npm run build --prefix web/robot_renderer
python -m streamlit run app.py
# 页面进入“V2 物理仿真”，默认 Panda；运行后显示完整几何回放
```

命令行可分别生成两版运行并比较：

```bash
python -m robot_mvp.v2_cli run --model panda-cube-v1 --strategy baseline --timeout 30
python -m robot_mvp.v2_cli run --model panda-cube-v1 --strategy offset-grasp --grasp-offset 0.08 --timeout 30
python -m robot_mvp.v2_cli compare data/v2_runs/<run-a> data/v2_runs/<run-b>
```

运行记录查询与统计（默认只查Panda，不读取V1模拟数据）：

```bash
python -m robot_mvp.v2_cli list --limit 20 --offset 0
python -m robot_mvp.v2_cli show <run-id>
python -m robot_mvp.v2_cli overview
```

`list`为轻量记录查询，`show`核对完整证据；运行中、执行异常和损坏记录不会被当作成功运行。`overview`是当前模型有效运行的描述性汇总，不是benchmark成功率。相同参数的比较会标记为重复性检查；比较拒绝的CLI退出码为2。

历史平面任务入口（不指定 `--model` 保持兼容）：

```bash
python -m robot_mvp.v2_cli run --artifacts data/v2_runs --strategy baseline
python -m robot_mvp.v2_cli run --artifacts data/v2_runs --strategy offset-grasp --grasp-offset 0.08
python -m robot_mvp.v2_cli compare data/v2_runs/<run-a> data/v2_runs/<run-b>
```

V2 使用原生 MuJoCo，worker 在独立进程运行，结果写入独立 artifact 目录。Panda 路径使用双指接触与摩擦搬运方块，旧平面路径仍明确标记为位置示意。前端只回放后端记录，不实时控制机器人。它用于演示执行接入、数据组织、受控比较和失败解释能力，不代表真机精度、视觉感知或 sim-to-real 结果。

> 💡 首次运行会自动初始化 `data/store.json`，包含 10 条示例运行记录、3 个策略版本和 2 个评测套件。

**Windows 用户**也可以直接双击 `start.bat`。

### 构建 3D 渲染器（完整 Panda 回放必需）

```bash
cd web/robot_renderer
npm install
npm run build    # 输出 dist/renderer.js
npm test         # 运行前端单测
```

> V1 可使用 SVG 示意。V2 bundle 缺失会提示构建且保留报告；WebGL 不可用时回退到明确标记的简化视图，不能将其当作完整机械臂显示通过。

---

## 🎬 推荐演示顺序

以下表格是 V1 预设演示，不能作为物理评测证据。Panda 演示请使用 V2 页面：运行 baseline → 回放接触/抬升/释放 → 运行 offset-grasp → 定位失败 → 在本页生成同模型比较报告。

| 步骤 | 操作 | 演示重点 |
|------|------|---------|
| 1 | 总览页开场 | 平台定位、策略版本、KPI 看板 |
| 2 | 启动"标准成功"任务 | 3D 实时动画：机械臂完成完整抓取—放置 |
| 3 | 启动"抓取失败"任务 | 失败场景：力反馈异常 → 物体滑落 |
| 4 | 帧级回放 | 定位失败瞬间，讲解失败原因 |
| 5 | 版本对比 | 两版策略并排，展示推荐逻辑 |
| 6 | 基准评测 | 批量运行，证明"稳定策略"在 5 个场景全部通过 |

> 全套演示 5–8 分钟，覆盖"启动 → 成功 → 失败 → 复盘 → 对比 → 评测"完整链路。

---

## 🧪 测试

```bash
# Python 测试（含旧平面与 Panda 回归，数量以实际输出为准）
python -m unittest discover -s tests -v

# 前端类型、测试与构建
npm run check --prefix web/robot_renderer
cd web/robot_renderer && npm test
```

---

## 🏛️ 技术架构

以下为 V1；V2 在独立 worker 中运行固定 Panda 模型，并将结果写入独立 artifact 目录。

```
Streamlit 页面  →  JsonStore  →  simulator  →  dataclass 模型
       ↓                                          ↓
   renderer.py  ←──────── renderer payload ←──────┘
       ↓
  Three.js bundle（IIFE）  →  2.5D 机械臂场景
       ↓ (fallback)
  Python SVG 模板          →  简化动作视图
```

**核心设计原则：**
- 页面只消费结构化数据，不参与业务推断
- Python 负责"业务真相"，TypeScript 负责"动作体验"
- 渲染降级透明，不改变运行结果；缺少 bundle 时不宣称完整回放可用

---

## 📄 文档索引

| 文档 | 说明 |
|------|------|

---

## 📋 License

项目代码沿用 MIT；`assets/robots/panda/` 中复用的 MuJoCo Menagerie 模型资产按其原始 Apache-2.0 许可提供，详见该目录 `LICENSE` 和 `SOURCES.json`。开源模型、项目接入与生成的仿真结果分别说明，不将上游模型宣称为自研。
