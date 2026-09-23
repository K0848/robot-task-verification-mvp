from __future__ import annotations

import json
import platform
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import mujoco


SCHEMA_VERSION = "v2.0"
MODEL_NAME = "minimal_planar_pick_place"
MODEL_XML = r"""
<mujoco model="v2_minimal_pick_place">
  <compiler angle="radian" autolimits="true"/>
  <option timestep="0.01" gravity="0 0 -9.81" integrator="implicitfast"/>
  <default>
    <joint damping="2" armature="0.01"/>
    <geom friction="1 0.5 0.1" condim="3"/>
  </default>
  <worldbody>
    <geom name="floor" type="plane" size="2 2 0.1" rgba="0.16 0.18 0.22 1"/>
    <body name="arm" pos="0 0 0.34">
      <joint name="arm_x" type="slide" axis="1 0 0" range="-0.6 0.6"/>
      <joint name="arm_z" type="slide" axis="0 0 1" range="-0.28 0.45"/>
      <geom name="arm_carriage" type="box" size="0.06 0.06 0.04" rgba="0.19 0.55 0.92 1"/>
      <body name="tool" pos="0 0 -0.07">
        <geom name="palm" type="box" size="0.055 0.065 0.02" rgba="0.29 0.78 0.66 1"/>
        <geom name="finger_left" type="box" pos="0 -0.045 -0.045" size="0.012 0.012 0.04" rgba="0.29 0.78 0.66 1"/>
        <geom name="finger_right" type="box" pos="0 0.045 -0.045" size="0.012 0.012 0.04" rgba="0.29 0.78 0.66 1"/>
      </body>
    </body>
    <body name="object" pos="-0.28 0 0.08">
      <freejoint name="object_free"/>
      <geom name="workpiece" type="box" size="0.035 0.035 0.035" mass="0.08" rgba="0.96 0.62 0.24 1"/>
    </body>
    <body name="target" pos="0.28 0 0.035">
      <geom name="target_marker" type="box" size="0.07 0.07 0.005" contype="0" conaffinity="0" rgba="0.96 0.3 0.42 0.45"/>
    </body>
  </worldbody>
  <actuator>
    <position name="arm_x_motor" joint="arm_x" kp="220" ctrlrange="-0.6 0.6"/>
    <position name="arm_z_motor" joint="arm_z" kp="220" ctrlrange="-0.28 0.45"/>
  </actuator>
  <equality>
    <!-- The lock is enabled only after the scripted grasp check. The physics engine
         still integrates the body and constraint; it is not a pre-baked trajectory. -->
    <weld name="grasp_lock" body1="tool" body2="object" active="false" solref="0.02 1" solimp="0.9 0.95 0.01"/>
  </equality>
</mujoco>
"""


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    run_id: str
    model_id: str = MODEL_NAME
    wall_timeout_s: float = 30.0
    strategy_id: str = "baseline"
    grasp_offset: float = 0.0
    initial_object_x: float = -0.28
    target_x: float = 0.28
    max_steps: int = 650
    fault_mode: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def environment_metadata() -> dict[str, Any]:
    return {
        "model_name": MODEL_NAME,
        "mujoco_version": getattr(mujoco, "__version__", "unknown"),
        "schema_version": SCHEMA_VERSION,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "runtime": "native-mujoco",
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _body_position(model: mujoco.MjModel, data: mujoco.MjData, name: str) -> list[float]:
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
    return [round(float(value), 6) for value in data.xpos[body_id]]


def _stage(step: int) -> str:
    if step < 200:
        return "approach"
    if step < 300:
        return "grasp"
    if step < 500:
        return "transport"
    if step < 580:
        return "place"
    return "release"


def _event(run_id: str, offset_ms: int, stage: str, level: str, message: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "offset_ms": offset_ms,
        "timestamp": utc_now(),
        "stage": stage,
        "level": level,
        "message": message,
    }


def run_physics(config: SimulationConfig, artifact_dir: Path, status_writer) -> dict[str, Any]:
    """Run the smallest useful physics slice and write observable artifacts.

    The environment intentionally uses a planar actuator and an explicit grasp
    constraint. This keeps the portfolio project CPU-runnable while preserving
    the important evidence boundary: every replay frame comes from MuJoCo state,
    not from V1's pre-authored snap frames.
    """
    if config.model_id == "panda-cube-v1":
        from robot_mvp.panda_runner import run_panda
        return run_panda(config, artifact_dir, status_writer)
    if config.model_id != MODEL_NAME:
        raise ValueError(f"未知模型：{config.model_id}")
    if config.fault_mode == "crash":
        raise RuntimeError("injected worker crash for TC-03")

    artifact_dir.mkdir(parents=True, exist_ok=True)
    model = mujoco.MjModel.from_xml_string(MODEL_XML)
    data = mujoco.MjData(model)
    object_joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "object_free")
    object_qpos = model.jnt_qposadr[object_joint]
    data.qpos[object_qpos : object_qpos + 3] = [config.initial_object_x, 0.0, 0.08]
    data.qpos[object_qpos + 3 : object_qpos + 7] = [1.0, 0.0, 0.0, 0.0]
    mujoco.mj_forward(model, data)

    initial_state = {
        "qpos": [round(float(value), 8) for value in data.qpos],
        "qvel": [round(float(value), 8) for value in data.qvel],
        "object_position": _body_position(model, data, "object"),
        "target_position": _body_position(model, data, "target"),
    }
    meta = {
        "run_id": config.run_id,
        "created_at": utc_now(),
        "config": config.to_dict(),
        "environment": environment_metadata(),
        "initial_state": initial_state,
        "trajectory_source": "mujoco-runtime",
        "artifact_schema": SCHEMA_VERSION,
    }
    _write_json(artifact_dir / "meta.json", meta)

    events: list[dict[str, Any]] = [_event(config.run_id, 0, "queued", "info", "仿真任务已创建")]
    trajectory_path = artifact_dir / "trajectory.jsonl"
    previous_stage = "queued"
    grasp_locked = False
    released = False
    grasp_failure_recorded = False
    max_steps = max(1, config.max_steps)
    if config.fault_mode == "timeout":
        max_steps = max(max_steps, 1000000)

    with trajectory_path.open("w", encoding="utf-8") as trajectory_file:
        for step in range(max_steps):
            stage = _stage(step)
            if stage != previous_stage:
                events.append(_event(config.run_id, step * 10, stage, "info", f"进入 {stage} 阶段"))
                previous_stage = stage

            # The weld preserves the relative transform captured at grasp time;
            # therefore the tool must compensate for the object's initial offset
            # to place the object, rather than merely moving the tool to target_x.
            transport_tool_x = config.target_x - config.initial_object_x
            tool_x = config.initial_object_x + config.grasp_offset if stage in {"approach", "grasp"} else transport_tool_x
            if stage == "approach":
                tool_z = 0.02
            elif stage == "grasp":
                tool_z = 0.02
            elif stage == "transport":
                tool_z = 0.13
            elif stage == "place":
                tool_z = -0.02
            else:
                tool_z = -0.02
            data.ctrl[0] = tool_x
            data.ctrl[1] = tool_z

            if stage == "grasp" and not grasp_locked:
                tool_position = _body_position(model, data, "tool")
                object_position = _body_position(model, data, "object")
                grasp_distance = abs(tool_position[0] - object_position[0])
                if abs(config.grasp_offset) <= 0.03 and grasp_distance <= 0.035:
                    equality_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_EQUALITY, "grasp_lock")
                    data.eq_active[equality_id] = 1
                    mujoco.mj_forward(model, data)
                    grasp_locked = True
                    events.append(_event(config.run_id, step * 10, stage, "info", "抓取约束已激活"))
                else:
                    if not grasp_failure_recorded:
                        events.append(_event(config.run_id, step * 10, stage, "warning", "抓取位置偏移，未建立抓取约束"))
                        grasp_failure_recorded = True

            if stage == "release" and grasp_locked and not released:
                equality_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_EQUALITY, "grasp_lock")
                data.eq_active[equality_id] = 0
                mujoco.mj_forward(model, data)
                released = True
                events.append(_event(config.run_id, step * 10, stage, "info", "物体已释放，进入稳定观察"))

            mujoco.mj_step(model, data)
            if step % 5 == 0 or step == max_steps - 1:
                object_position = _body_position(model, data, "object")
                target_position = _body_position(model, data, "target")
                tool_position = _body_position(model, data, "tool")
                frame = {
                    "run_id": config.run_id,
                    "step": step,
                    "sim_time_ms": step * 10,
                    "stage": stage,
                    "tool_position": tool_position,
                    "object_position": object_position,
                    "target_position": target_position,
                    "gripper_state": "closed" if stage in {"grasp", "transport", "place"} else "open",
                    "grasp_locked": grasp_locked,
                    "released": released,
                    "qpos": [round(float(value), 8) for value in data.qpos],
                    "qvel": [round(float(value), 8) for value in data.qvel],
                }
                trajectory_file.write(json.dumps(frame, ensure_ascii=False) + "\n")
                status_writer(
                    {
                        "run_id": config.run_id,
                        "status": "running",
                        "stage": stage,
                        "progress": round(min(1.0, (step + 1) / max_steps), 4),
                        "sim_time_ms": step * 10,
                        "updated_at": utc_now(),
                    }
                )

    final_frame = frame
    distance = ((final_frame["object_position"][0] - final_frame["target_position"][0]) ** 2 + (final_frame["object_position"][1] - final_frame["target_position"][1]) ** 2) ** 0.5
    success = bool(grasp_locked and released and distance <= 0.08 and final_frame["object_position"][2] >= 0.025)
    if success:
        failure_classification = None
        observation = "物体建立抓取约束，移动至目标区域并在释放后保持稳定。"
        possible_cause = None
        final_status = "succeeded"
    elif not grasp_locked:
        failure_classification = "grasp"
        observation = "抓取阶段未建立约束，物体没有随工具移动。"
        possible_cause = "抓取偏移参数超过当前任务的受控容差。"
        final_status = "failed"
    else:
        failure_classification = "placement"
        observation = "物体完成搬运，但释放后未落入目标区域或未稳定。"
        possible_cause = "放置位置或释放时序需要进一步验证。"
        final_status = "failed"

    summary = {
        "run_id": config.run_id,
        "final_status": final_status,
        "success": success,
        "duration_ms": (max_steps - 1) * 10,
        "sample_count": 1,
        "success_criteria": {
            "grasp_locked": grasp_locked,
            "released": released,
            "target_distance_m": round(distance, 6),
            "target_distance_threshold_m": 0.08,
            "stable_height_min_m": 0.025,
        },
        "failure": {
            "observation": observation,
            "classification": failure_classification,
            "possible_cause": possible_cause,
            "unknown": None if success else "仅凭本次仿真不能确认控制器或传感器故障。",
        },
        "evidence_scope": "native MuJoCo minimal planar task; not sim-to-real evidence",
        "trajectory_file": "trajectory.jsonl",
        "events_file": "events.jsonl",
    }
    (artifact_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in events) + "\n",
        encoding="utf-8",
    )
    _write_json(artifact_dir / "summary.json", summary)
    status_writer(
        {
            "run_id": config.run_id,
            "status": final_status,
            "stage": "complete",
            "progress": 1.0,
            "sim_time_ms": summary["duration_ms"],
            "updated_at": utc_now(),
        }
    )
    return summary
