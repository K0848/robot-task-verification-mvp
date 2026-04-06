# 🤖 仿真机械臂任务验证平台 MVP

> 一条完整的 Pick & Place 任务验证闭环，用产品化视角把"启动 → 监控 → 复盘 → 对比 → 评测"收敛成一个可演示的仪表盘。

<p align="center">
  <strong>Python + Streamlit + Three.js · 单机运行 · 模拟数据驱动 · 开箱即用</strong>
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

## 🎯 适合展示的能力

- 🏗️ 机器人软件产品规划与 MVP 落地
- 🔄 任务验证流程梳理和页面抽象
- 📊 运行数据结构化沉淀与可解释结论
- 🔍 失败案例复盘与策略迭代对比

---

## 🎥 演示视频

(./demo.mp4)

> 视频展示了完整的 Pick & Place 任务验证流程，包括实时监控、失败复盘、版本对比和基准评测功能。

---

## 📐 项目结构

```text
.
├── app.py                         # Streamlit 主应用入口
├── PRD.md                         # 产品需求文档
├── requirements.txt               # Python 依赖
├── start.bat                      # Windows 一键启动
│
├── robot_mvp/                     # 核心业务包
│   ├── models.py                  #   数据模型（8 个 dataclass）
│   ├── simulator.py               #   场景模拟 · 帧生成 · 状态投影 · 评测汇总
│   ├── storage.py                 #   JSON 持久化层
│   └── renderer.py                #   Three.js 桥接 + SVG 回退
│
├── web/robot_renderer/            # 独立前端渲染子项目
│   ├── src/
│   │   ├── index.ts               #   Three.js 2.5D 场景
│   │   └── payload.ts             #   渲染协议 · 帧采样 · 动画计算
│   └── tests/
│       └── payload.test.ts        #   前端单测
│
├── tests/
│   └── test_simulator.py          # Python 单测（17 项）
│
├── data/                          # 运行时数据（首次启动自动生成）
│   └── store.json
│
└── md/                            # 项目文档
    └── 项目结构总览.md
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

> 💡 首次运行会自动初始化 `data/store.json`，包含 10 条示例运行记录、3 个策略版本和 2 个评测套件。

**Windows 用户**也可以直接双击 `start.bat`。

### 构建 3D 渲染器（可选）

```bash
cd web/robot_renderer
npm install
npm run build    # 输出 dist/renderer.js
npm test         # 运行前端单测
```

> 如果不构建 Three.js bundle，平台会自动降级为 SVG 视图，所有功能正常可用。

---

## 🎬 推荐演示顺序

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
# Python 测试（17 项）
python -m unittest discover -s tests -v

# 前端测试（5 项）
cd web/robot_renderer && npm test
```

---

## 🏛️ 技术架构

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
- 渲染降级透明，功能不因 bundle 缺失而中断

---

## 📄 文档索引

| 文档 | 说明 |
|------|------|
| [PRD.md](PRD.md) | 产品需求文档（问题定义 · 信息架构 · 数据模型 · 渲染管线 · 测试策略） |
| [md/项目结构总览.md](md/项目结构总览.md) | 面向开发者的代码级架构总览 |

---

## 📋 License

MIT
