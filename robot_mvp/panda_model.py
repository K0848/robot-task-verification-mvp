"""固定 Panda 模型和单方块场景；外观与动力学共用编译后的模型。"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

ASSET_ROOT = Path(__file__).resolve().parents[1] / "assets" / "robots" / "panda"
MODEL_ID = "panda-cube-v1"
# 获取脚本对固定上游 Git blob 校验后生成的来源清单指纹，防止资产和清单一起被换源。
SOURCE_MANIFEST_SHA256 = "ca5dc8d60bb03310ff4a11f9df128925d26b68e069d290a0e65c8b7fd9305bf2"
HOME = np.array([0., 0., 0., -1.57079, 0., 1.57079, -.7853])
# 单方块演示配置：单位米、千克、秒；正式用例冻结后不可按结果临时放宽。
SCENE = {
    "version": "panda-cube-scene-1", "timestep_s": .002,
    "object_half_size_m": .02, "object_mass_kg": .04,
    "object_position": [.45, 0., .021], "target_position": [.45, .20, .02],
    "target_half_size_m": .06, "friction": [1., .005, .0001],
}
CRITERIA = {
    "version": "panda-contact-eval-1", "lift_height_m": .04, "lift_hold_s": .25,
    "target_distance_threshold_m": .04, "rest_height_tolerance_m": .01,
    "linear_speed_max_m_s": .03, "angular_speed_max_rad_s": .2,
    "stable_window_s": .5, "released_gap_min_m": .06,
}


def source_manifest(root: Path = ASSET_ROOT) -> dict:
    path = root / "SOURCES.json"
    if not path.exists():
        raise ValueError("Panda 模型资产缺失，请先运行 python scripts/fetch_panda_assets.py")
    encoded = path.read_bytes()
    # 清单只归一化 Windows 行尾；模型文件仍按原始字节校验，跨系统获取不改变来源。
    if sha256(encoded.replace(b"\r\n", b"\n")).hexdigest() != SOURCE_MANIFEST_SHA256:
        raise ValueError("Panda 来源清单与冻结版本不一致")
    source = json.loads(encoded)
    for name, expected in source["sha256"].items():
        asset = (root / name).resolve()
        if not asset.is_relative_to(root.resolve()):
            raise ValueError("模型资产路径越界")
        if not asset.is_file() or sha256(asset.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Panda 模型资产缺失或哈希不匹配：{name}")
    return source


def load_model() -> tuple[mujoco.MjModel, dict]:
    source = source_manifest()
    root = ET.fromstring((ASSET_ROOT / "panda.xml").read_text(encoding="utf-8"))
    root.find("compiler").set("meshdir", "assets")
    root.find("option").set("timestep", str(SCENE["timestep_s"]))
    # 上游 home 的 qpos 只含机器人；增加自由物体后由 initial_data 显式初始化。
    root.remove(root.find("keyframe"))
    world = root.find("worldbody")
    ET.SubElement(world, "geom", name="floor", type="plane", size="1 1 .1", rgba=".24 .29 .35 1")
    ET.SubElement(world, "light", pos="0 -1 2", diffuse=".8 .8 .8")
    cube = ET.SubElement(world, "body", name="workpiece", pos=" ".join(map(str, SCENE["object_position"])))
    ET.SubElement(cube, "freejoint", name="object_joint")
    size = " ".join([str(SCENE["object_half_size_m"])] * 3)
    ET.SubElement(cube, "geom", name="workpiece_geom", type="box", size=size,
                  mass=str(SCENE["object_mass_kg"]), rgba="1 .55 .12 1",
                  friction=" ".join(map(str, SCENE["friction"])), condim="4")
    ET.SubElement(world, "geom", name="target", type="box", pos=".45 .20 .001",
                  size=".06 .06 .001", contype="0", conaffinity="0", rgba=".1 .75 .4 .5")
    hand = root.find(".//body[@name='hand']")
    ET.SubElement(hand, "site", name="pinch", pos="0 0 .1034", size=".003", rgba="0 0 0 0")
    # MuJoCo 原生文件接口在 Windows 中文路径上可能打开失败；由 Python 读入
    # 已校验网格再交给虚拟文件系统，模型本身仍使用同一份上游资源。
    assets = {name: (ASSET_ROOT / name).read_bytes() for name in source["sha256"] if name.startswith("assets/")}
    model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"), assets=assets)
    identity = {"model_id": MODEL_ID, "source": source, "scene": SCENE,
                "scene_xml_sha256": sha256(ET.tostring(root, encoding="utf-8")).hexdigest()}
    identity["model_hash"] = sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    identity["joint_names"] = [model.joint(i).name for i in range(model.njnt)]
    return model, identity


def initial_data(model: mujoco.MjModel) -> mujoco.MjData:
    data = mujoco.MjData(model)
    data.qpos[:7] = HOME
    data.qpos[7:9] = .04
    data.ctrl[:7] = HOME
    data.ctrl[7] = 255
    mujoco.mj_forward(model, data)
    return data


def solve_ik(model: mujoco.MjModel, seed: np.ndarray, position: np.ndarray) -> np.ndarray:
    """固定朝下的夹爪姿态，阻尼最小二乘求目标关节角；不写入运行中的状态。"""
    data = initial_data(model)
    data.qpos[:7] = seed
    site = model.site("pinch").id
    target_rotation = np.diag([1., -1., -1.])
    jacp, jacr = np.zeros((3, model.nv)), np.zeros((3, model.nv))
    for _ in range(250):
        mujoco.mj_forward(model, data)
        rotation = data.site_xmat[site].reshape(3, 3)
        error = np.r_[position - data.site_xpos[site],
                      .5 * sum(np.cross(rotation[:, i], target_rotation[:, i]) for i in range(3))]
        if np.linalg.norm(error) < 1e-5:
            return data.qpos[:7].copy()
        mujoco.mj_jacSite(model, data, jacp, jacr, site)
        jac = np.vstack([jacp[:, :7], jacr[:, :7]])
        delta = jac.T @ np.linalg.solve(jac @ jac.T + .001 * np.eye(6), error)
        data.qpos[:7] = np.clip(data.qpos[:7] + np.clip(delta, -.1, .1),
                                model.jnt_range[:7, 0] + .001, model.jnt_range[:7, 1] - .001)
    raise ValueError(f"目标位姿无法到达：{position.tolist()}，误差 {np.linalg.norm(error):.6f}")
