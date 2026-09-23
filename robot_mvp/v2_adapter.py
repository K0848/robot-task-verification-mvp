from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from robot_mvp.v2_runtime import load_trajectory


def artifact_to_renderer_payload(artifact_dir: Path, *, view_mode: str = "replay") -> dict[str, Any]:
    """Adapt V2's real trajectory to the existing renderer's read-only payload.

    The adapter deliberately exposes the trajectory source and physical positions
    so a UI cannot silently present V1's pre-authored snap frames as V2 evidence.
    """
    meta = json.loads((artifact_dir / "meta.json").read_text(encoding="utf-8"))
    summary = json.loads((artifact_dir / "summary.json").read_text(encoding="utf-8"))
    trajectory = load_trajectory(artifact_dir)
    events = [json.loads(line) for line in (artifact_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    config = meta["config"]
    panda = meta.get("artifact_schema") == "v2.1"
    if meta.get("artifact_schema") not in {"v2.0", "v2.1"}:
        raise ValueError("不支持的运行产物版本")
    robot_scene = None
    if panda:
        from robot_mvp.panda_artifacts import validate_panda
        robot_scene = validate_panda(artifact_dir, meta, summary, trajectory, events)
    frames = []
    for frame in trajectory:
        held = bool(frame["held"]) if panda else bool(frame["grasp_locked"] and not frame["released"])
        frames.append(
            {
                "offset_ms": frame["sim_time_ms"],
                "stage": frame["stage"],
                "arm_pose": {
                    "x": frame["tool_position"][0],
                    "y": frame["tool_position"][1],
                    "z": frame["tool_position"][2],
                },
                "gripper_state": frame["gripper_state"],
                "target_state": {
                    "object_label": "MuJoCo workpiece",
                    "target_slot": "target",
                    "object_x": frame["object_position"][0],
                    "object_y": frame["object_position"][1],
                    "object_z": frame["object_position"][2],
                    "pickup_x": config["initial_object_x"],
                    "pickup_y": 0.0,
                    "pickup_z": meta["initial_state"]["object_position"][2],
                    "dropoff_x": config["target_x"],
                    "dropoff_y": 0.0,
                    "dropoff_z": frame["target_position"][2],
                    "held": held,
                    "placed": bool(frame["stable_duration_s"] >= meta["evaluation"]["stable_window_s"]) if panda else bool(summary["success"] and frame["released"]),
                },
            }
        )
    renderer_events = [
        {"offset_ms": event["offset_ms"], "stage": event["stage"], "level": event["level"], "message": event["message"]}
        for event in events
    ]
    return {
        "run_id": meta["run_id"],
        "model_id": meta["environment"]["model_name"],
        **({"robot_scene": robot_scene, "robot_frames": trajectory} if panda else {}),
        "view_mode": view_mode,
        "title": f"V2 物理仿真回放 · {meta['run_id']}",
        "status": summary["final_status"],
        "success": summary["success"],
        "scenario_label": "Panda 接触抓放" if panda else "V2 MuJoCo minimal planar task",
        "resolved_scenario": "",
        "coordinate_system": "mujoco-world",
        "progress": 1.0,
        "current_stage": "complete",
        "highlight_mode": "failure" if not summary["success"] else "overview",
        "camera_preset": "sim-isometric",
        "dynamic_profile": {"pace": "default", "pace_multiplier": 1.0, "focus": "overview", "matched_keywords": []},
        "trajectory_source": meta["trajectory_source"],
        "environment": meta["environment"],
        "scene": {
            "object_label": "MuJoCo workpiece",
            "source_bin": "simulated-source",
            "target_slot": "target",
            "surface": "MuJoCo floor plane",
        },
        "animation": {
            "mode": "static",
            "duration_ms": summary["duration_ms"],
            "initial_elapsed_ms": 0,
        },
        "frames": frames,
        "trajectory": trajectory,
        "events": renderer_events,
        "report": summary,
    }
