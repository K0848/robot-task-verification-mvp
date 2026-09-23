"""Panda 产物边界校验：拒绝损坏/错配，不填造缺失姿态。"""
import base64
from hashlib import sha256
import json
import math
from pathlib import Path

import numpy as np


def vector(value, length: int, label: str) -> None:
    if not isinstance(value, list) or len(value) != length or any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value
    ):
        raise ValueError(f"{label} 必须为 {length} 个有限数值")


def quaternion(value, label: str) -> None:
    vector(value, 4, label)
    if abs(sum(v*v for v in value)-1) > .001:
        raise ValueError(f"{label} 不是单位四元数")


def validate_panda(artifact_dir: Path, meta: dict, summary: dict, frames: list, events: list) -> dict:
    try:
        encoded = (artifact_dir / "scene.json").read_bytes()
        if sha256(encoded).hexdigest() != meta["scene_sha256"]:
            raise ValueError("场景文件哈希不匹配")
        scene = json.loads(encoded)
        if meta["artifact_schema"] != "v2.1" or scene["schema"] != "panda-scene-1":
            raise ValueError("不支持的 Panda 产物版本")
        if scene["model_hash"] != meta["model"]["model_hash"]:
            raise ValueError("模型与场景身份不匹配")
        if summary["run_id"] != meta["run_id"] or meta["config"]["run_id"] != meta["run_id"]:
            raise ValueError("运行 ID 不一致")
        if not isinstance(summary["success"], bool) or summary["final_status"] != ("succeeded" if summary["success"] else "failed"):
            raise ValueError("结果与终态不一致")
        mesh_ids = set()
        for mesh in scene["meshes"]:
            if mesh["id"] in mesh_ids:
                raise ValueError("重复网格 ID")
            mesh_ids.add(mesh["id"])
            vertices = np.frombuffer(base64.b64decode(mesh["vertices_b64"], validate=True), dtype="<f4")
            indices = np.frombuffer(base64.b64decode(mesh["indices_b64"], validate=True), dtype="<u4")
            if not len(vertices) or len(vertices)%3 or not np.isfinite(vertices).all() or not len(indices) or len(indices)%3 or indices.max() >= len(vertices)//3:
                raise ValueError("非法网格顶点或索引")
        geom_ids = set()
        for geom in scene["geoms"]:
            if geom["id"] in geom_ids:
                raise ValueError("重复几何 ID")
            geom_ids.add(geom["id"])
            vector(geom["size"], 3, "几何尺寸")
            vector(geom["rgba"], 4, "几何颜色")
            if geom["type"] not in {"mesh", "box", "plane"} or (geom["type"] == "mesh" and geom["mesh_id"] not in mesh_ids):
                raise ValueError("未知几何类型或缺失网格")
        if not frames or not geom_ids:
            raise ValueError("缺少完整模型轨迹")
        previous = -1
        duration = summary["duration_ms"]
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
            raise ValueError("非法运行时长")
        for frame in frames:
            t = frame["sim_time_ms"]
            if isinstance(t, bool) or not isinstance(t, (float, int)) or not math.isfinite(t) or not previous < t <= duration:
                raise ValueError("轨迹时间非单调或越界")
            previous = t
            if frame["run_id"] != meta["run_id"] or len(frame["geom_poses"]) != len(geom_ids):
                raise ValueError("轨迹运行 ID 或几何映射长度不一致")
            for key in ("tool_position", "object_position", "target_position"):
                vector(frame[key], 3, key)
            vector([frame["gripper_width_m"]], 1, "夹爪间距")
            quaternion(frame["object_quaternion"], "物体朝向")
            for pose in frame["geom_poses"]:
                vector(pose["position"], 3, "几何位置")
                quaternion(pose["quaternion"], "几何朝向")
        if previous != duration:
            raise ValueError("轨迹末帧与运行时长不一致")
        previous = -1
        for event in events:
            t = event["offset_ms"]
            if event["run_id"] != meta["run_id"] or not isinstance(t, (float, int)) or not math.isfinite(t) or not 0 <= t <= duration or t < previous:
                raise ValueError("事件时间或运行 ID 不一致")
            previous = t
        return scene
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError(f"Panda 产物结构缺失或不合法：{error}") from error
