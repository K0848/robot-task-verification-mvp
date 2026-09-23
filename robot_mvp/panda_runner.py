"""单 Panda 接触抓放：物理状态、事件与判据均由后端产生。"""
from __future__ import annotations

import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import time

import mujoco
import numpy as np

from robot_mvp.panda_model import CRITERIA, HOME, MODEL_ID, SCENE, initial_data, load_model, solve_ik
from robot_mvp.v2_physics import environment_metadata, utc_now

CONTROLLER_VERSION = "panda-waypoints-1"


def write_json(path: Path, value: dict) -> str:
    data = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    path.write_bytes(data)
    return sha256(data).hexdigest()


def export_scene(model: mujoco.MjModel, identity: dict) -> dict:
    """导出 MuJoCo 编译网格；其重心修正已反映在 geom 的世界变换中。"""
    geoms, meshes = [], {}
    types = {int(mujoco.mjtGeom.mjGEOM_MESH): "mesh", int(mujoco.mjtGeom.mjGEOM_BOX): "box",
             int(mujoco.mjtGeom.mjGEOM_PLANE): "plane"}
    for geom_id in range(model.ngeom):
        if model.geom_group[geom_id] == 3:
            continue
        kind = types[int(model.geom_type[geom_id])]
        mesh_id = int(model.geom_dataid[geom_id]) if kind == "mesh" else None
        mat = int(model.geom_matid[geom_id])
        rgba = model.mat_rgba[mat] if mat >= 0 else model.geom_rgba[geom_id]
        geoms.append({"id": geom_id, "name": model.geom(geom_id).name or f"geom-{geom_id}",
                      "body": model.body(int(model.geom_bodyid[geom_id])).name,
                      "type": kind, "mesh_id": mesh_id, "size": model.geom_size[geom_id].tolist(), "rgba": rgba.tolist()})
        if mesh_id is not None and mesh_id not in meshes:
            va, vn = model.mesh_vertadr[mesh_id], model.mesh_vertnum[mesh_id]
            fa, fn = model.mesh_faceadr[mesh_id], model.mesh_facenum[mesh_id]
            meshes[mesh_id] = {"id": mesh_id,
                "vertices_b64": base64.b64encode(model.mesh_vert[va:va+vn].astype("<f4").tobytes()).decode(),
                "indices_b64": base64.b64encode(model.mesh_face[fa:fa+fn].astype("<u4").tobytes()).decode()}
    return {"schema": "panda-scene-1", "model_hash": identity["model_hash"],
            "meshes": list(meshes.values()), "geoms": geoms}


def contact_forces(model: mujoco.MjModel, data: mujoco.MjData) -> dict:
    ids = {model.body("left_finger").id: "left", model.body("right_finger").id: "right"}
    object_body = model.body("workpiece").id
    forces = {"left": 0., "right": 0.}
    wrench = np.zeros(6)
    for index in range(data.ncon):
        contact = data.contact[index]
        b1, b2 = int(model.geom_bodyid[contact.geom1]), int(model.geom_bodyid[contact.geom2])
        finger = b2 if b1 == object_body else b1 if b2 == object_body else None
        if finger in ids:
            mujoco.mj_contactForce(model, data, index, wrench)
            forces[ids[finger]] += max(0., float(wrench[0]))
    return forces


def peak_memory_bytes() -> int | None:
    # 运行时不新增 psutil 依赖；Windows 原生 API 返回当前进程峰值工作集。
    import ctypes
    if __import__("sys").platform != "win32":
        return None
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize",
                "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    query = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not query(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        return None
    return int(counters.PeakWorkingSetSize)


def run_panda(config, artifact_dir: Path, status_writer) -> dict:
    if config.fault_mode == "crash":
        raise RuntimeError("injected Panda worker crash")
    started = time.perf_counter()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model, identity = load_model()
    loaded = time.perf_counter() - started
    data = initial_data(model)
    object_joint = model.joint("object_joint")
    qa, va = int(object_joint.qposadr[0]), int(object_joint.dofadr[0])
    data.qpos[qa] = config.initial_object_x
    model.geom_pos[model.geom("target").id, 0] = config.target_x
    mujoco.mj_forward(model, data)
    # 实际初始配置和目标变化也进入模型身份，禁止同名模型不同场景混比。
    identity = dict(identity, runtime_scene={"initial_x": config.initial_object_x, "target_x": config.target_x})
    identity["model_hash"] = sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    scene = export_scene(model, identity)
    scene_hash = write_json(artifact_dir / "scene.json", scene)
    geom_ids = [g["id"] for g in scene["geoms"]]
    meta = {"run_id": config.run_id, "created_at": utc_now(), "config": config.to_dict(),
            "environment": dict(environment_metadata(), model_name=MODEL_ID),
            "model": identity, "artifact_schema": "v2.1", "trajectory_source": "mujoco-runtime",
            "controller_version": CONTROLLER_VERSION, "evaluation": CRITERIA,
            "scene_sha256": scene_hash,
            "initial_state": {"qpos": data.qpos.tolist(), "qvel": data.qvel.tolist(),
                              "ctrl": data.ctrl.tolist(), "time": float(data.time),
                              "object_position": data.body("workpiece").xpos.tolist(),
                              "target_position": [config.target_x, .2, .02]},
            "scope": "single Panda contact task; privileged object pose; no vision or sim-to-real evidence"}
    write_json(artifact_dir / "meta.json", meta)
    x = config.initial_object_x + config.grasp_offset
    tx = config.target_x + config.grasp_offset
    specs = [(2., "approach", [x, 0, .20], 255.), (3.5, "descend", [x, 0, .024], 255.),
             (4.5, "grasp", [x, 0, .024], 0.), (6.5, "lift", [x, 0, .18], 0.),
             (8.5, "transport", [tx, .2, .18], 0.), (10., "place", [tx, .2, .026], 0.),
             (11., "release", [tx, .2, .026], 255.), (12.5, "retreat", [tx, .2, .20], 255.),
             (14., "settle", [tx, .2, .20], 255.)]
    waypoints, seed = [], HOME.copy()
    for end, stage, position, grip in specs:
        goal = solve_ik(model, seed, np.array(position))
        waypoints.append((end, stage, seed.copy(), goal.copy(), grip))
        seed = goal
    events = []
    def event(stage: str, message: str, level: str = "info") -> None:
        events.append({"run_id": config.run_id, "offset_ms": round(data.time * 1000),
                       "timestamp": utc_now(), "stage": stage, "level": level, "message": message})
    lifted, released, stable_s, lift_s = False, False, 0., 0.
    max_lift, previous_stage, stage_index = 0., "", 0
    frames_written = 0
    step_count = config.max_steps
    if config.fault_mode == "timeout":
        step_count = max(step_count, 1000000)
    dt = model.opt.timestep
    next_sample = 0.
    with (artifact_dir / "trajectory.jsonl").open("w", encoding="utf-8") as output:
        for step in range(step_count):
            while stage_index < len(waypoints)-1 and data.time >= waypoints[stage_index][0]:
                stage_index += 1
            end, stage, qstart, qgoal, grip = waypoints[stage_index]
            start = waypoints[stage_index-1][0] if stage_index else 0.
            ratio = min(1., max(0., (data.time-start)/(end-start)))
            data.ctrl[:7] = qstart + (qgoal-qstart) * (3*ratio**2-2*ratio**3)
            data.ctrl[7] = grip
            if stage != previous_stage:
                event(stage, f"进入 {stage} 阶段")
                previous_stage = stage
            mujoco.mj_step(model, data)
            # mj_step 的位置派生量可能仍对应步前状态；显式 forward 对齐同一采样时刻。
            mujoco.mj_forward(model, data)
            forces = contact_forces(model, data)
            obj = data.body("workpiece").xpos.copy()
            gap = float(data.qpos[7] + data.qpos[8])
            bilateral = forces["left"] > .01 and forces["right"] > .01
            height = float(obj[2] - SCENE["object_half_size_m"])
            max_lift = max(max_lift, height)
            lift_s = lift_s + dt if bilateral and height >= CRITERIA["lift_height_m"] else 0.
            if not lifted and lift_s >= CRITERIA["lift_hold_s"]:
                lifted = True
                event(stage, "双指接触支持物体，抬升持续时间达到判据")
            if lifted and not released and stage in {"release", "retreat", "settle"} and gap >= CRITERIA["released_gap_min_m"] and max(forces.values()) < .01:
                released = True
                event(stage, "夹爪实际张开且双指与物体脱离接触")
            distance = float(np.linalg.norm(obj[:2] - [config.target_x, .2]))
            stable = (released and distance <= CRITERIA["target_distance_threshold_m"]
                      and abs(obj[2] - SCENE["object_half_size_m"]) <= CRITERIA["rest_height_tolerance_m"]
                      and np.linalg.norm(data.qvel[va:va+3]) <= CRITERIA["linear_speed_max_m_s"]
                      and np.linalg.norm(data.qvel[va+3:va+6]) <= CRITERIA["angular_speed_max_rad_s"])
            stable_s = stable_s + dt if stable else 0.
            if data.time + 1e-9 >= next_sample or step == step_count-1:
                quat = np.zeros(4)
                poses = []
                for geom_id in geom_ids:
                    mujoco.mju_mat2Quat(quat, data.geom_xmat[geom_id])
                    poses.append({"position": data.geom_xpos[geom_id].tolist(), "quaternion": quat.tolist()})
                frame = {"run_id": config.run_id, "step": step+1, "sim_time_ms": round(data.time*1000),
                    "stage": stage, "tool_position": data.site("pinch").xpos.tolist(),
                    "object_position": obj.tolist(), "object_quaternion": data.body("workpiece").xquat.tolist(),
                    "target_position": [config.target_x, .2, .02], "gripper_width_m": gap,
                    "gripper_state": "open" if gap >= .06 else "closed", "contacts": forces,
                    "grasp_locked": False, "held": bilateral, "released": released,
                    "qpos": data.qpos.tolist(), "qvel": data.qvel.tolist(), "ctrl": data.ctrl.tolist(),
                    "geom_poses": poses, "lifted": lifted, "stable_duration_s": stable_s}
                output.write(json.dumps(frame, separators=(",", ":"), allow_nan=False) + "\n")
                frames_written += 1
                next_sample += 1/30
                status_writer({"run_id": config.run_id, "status": "running", "stage": stage,
                               "progress": (step+1)/step_count, "sim_time_ms": frame["sim_time_ms"], "updated_at": utc_now()})
    success = bool(lifted and released and stable_s >= CRITERIA["stable_window_s"])
    classification = None if success else "grasp" if not lifted else "placement"
    event("complete", "接触抓放与稳定窗口验证通过" if success else "任务未满足完整抓放判据", "info" if success else "warning")
    summary = {"run_id": config.run_id, "final_status": "succeeded" if success else "failed", "success": success,
               "duration_ms": round(data.time*1000), "sample_count": 1,
               "success_criteria": dict(CRITERIA, lifted=lifted, released=released, stable_duration_s=stable_s,
                                        target_distance_m=distance, max_lift_m=max_lift),
               "failure": {"observation": "物体由双指接触抬升、搬运并释放，在目标区持续稳定。" if success else "物体未完成有接触证据的抬升。" if not lifted else "物体抬升后未满足释放或目标内持续稳定判据。",
                           "classification": classification,
                           "possible_cause": None if success else "需结合夹爪开度、接触力和运动轨迹检查控制参数；不由参数名称直接归因。",
                           "unknown": "仅支持当前仿真条件；未验证视觉误差、真机控制器或生产稳定性。"},
               "evidence_scope": meta["scope"], "trajectory_file": "trajectory.jsonl", "events_file": "events.jsonl"}
    (artifact_dir / "events.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events)+"\n", encoding="utf-8")
    write_json(artifact_dir / "summary.json", summary)
    write_json(artifact_dir / "performance.json", {"load_s": loaded, "wall_s": time.perf_counter()-started,
                "sim_s": float(data.time), "frames": frames_written, "peak_working_set_bytes": peak_memory_bytes(),
                "process_id": os.getpid(), "memory_scope": "calling_process_peak_working_set",
                "artifact_bytes": sum(p.stat().st_size for p in artifact_dir.iterdir() if p.is_file())})
    status_writer({"run_id": config.run_id, "status": summary["final_status"], "stage": "complete",
                   "progress": 1., "sim_time_ms": summary["duration_ms"], "updated_at": utc_now()})
    return summary
