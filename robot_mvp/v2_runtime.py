from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from robot_mvp.v2_physics import SimulationConfig


V2_SCHEMA_VERSION = "v2.0"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    last_error: Exception | None = None
    for _ in range(20):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (PermissionError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(0.01)
    if last_error is not None:
        raise last_error
    raise FileNotFoundError(path)


@dataclass(slots=True)
class JobHandle:
    run_id: str
    artifact_dir: Path
    process: subprocess.Popen[str]
    started_at: float
    timeout_s: float


class ArtifactStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, config: SimulationConfig) -> Path:
        path = self.run_dir(config.run_id)
        path.mkdir(parents=True, exist_ok=False)
        _write_json(path / "config.json", config.to_dict())
        _write_json(
            path / "status.json",
            {
                "run_id": config.run_id,
                "status": "queued",
                "stage": "queued",
                "progress": 0.0,
                "updated_at": None,
            },
        )
        return path

    def read_status(self, run_id: str) -> dict[str, Any]:
        return _read_json(self.run_dir(run_id) / "status.json")

    def read_summary(self, run_id: str) -> dict[str, Any]:
        return _read_json(self.run_dir(run_id) / "summary.json")

    def read_meta(self, run_id: str) -> dict[str, Any]:
        return _read_json(self.run_dir(run_id) / "meta.json")

    def update_status(self, run_id: str, **values: Any) -> None:
        path = self.run_dir(run_id) / "status.json"
        payload = _read_json(path) if path.exists() else {"run_id": run_id}
        payload.update(values)
        _write_json(path, payload)

    def list_run_ids(self) -> list[str]:
        return sorted(item.name for item in self.root.iterdir() if item.is_dir())

    def run_dir(self, run_id: str) -> Path:
        validate_run_id(run_id)
        path = (self.root / run_id).resolve()
        if path.parent != self.root.resolve():
            raise ValueError("运行路径不在当前产物目录内")
        return path


class V2JobManager:
    def __init__(self, artifacts_root: Path):
        self.artifacts = ArtifactStore(artifacts_root)

    def start(self, config: SimulationConfig) -> JobHandle:
        validate_config(config)
        artifact_dir = self.artifacts.create(config)
        config_path = artifact_dir / "config.json"
        command = [
            sys.executable,
            "-m",
            "robot_mvp.v2_worker",
            "--config",
            str(config_path),
            "--artifact-dir",
            str(artifact_dir),
        ]
        process = subprocess.Popen(
            command,
            cwd=str(Path(__file__).resolve().parents[1]),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return JobHandle(config.run_id, artifact_dir, process, time.monotonic(), config.wall_timeout_s)

    def poll(self, handle: JobHandle) -> dict[str, Any]:
        return_code = handle.process.poll()
        status = self.artifacts.read_status(handle.run_id)
        if return_code is None and time.monotonic() - handle.started_at > handle.timeout_s:
            self._stop(handle)
            self._reap(handle)
            self.artifacts.update_status(
                handle.run_id,
                status="failed",
                stage="worker",
                progress=status.get("progress", 0.0),
                error_code="wall_timeout",
                error_message=f"worker exceeded wall_timeout_s={handle.timeout_s}",
            )
            return self.artifacts.read_status(handle.run_id)
        if return_code is None:
            if status.get("status") in {"succeeded", "failed", "cancelled"}:
                # worker 可能先写入终态、再从解释器退出；页面 poll 不能把前者当作资源已收敛。
                self._reap(handle)
            return status
        if return_code != 0 and status.get("status") in {"queued", "running"}:
            stderr = ""
            if handle.process.stderr is not None:
                stderr = handle.process.stderr.read()[-2000:]
            self.artifacts.update_status(
                handle.run_id,
                status="failed",
                stage="worker",
                progress=status.get("progress", 0.0),
                error_code="worker_crash",
                error_message=stderr or f"worker exited with code {return_code}",
            )
            self._reap(handle)
            return self.artifacts.read_status(handle.run_id)
        if status.get("status") not in {"succeeded", "failed", "cancelled"}:
            self._reap(handle)
            self.artifacts.update_status(
                handle.run_id,
                status="failed",
                stage="worker",
                progress=status.get("progress", 0.0),
                error_code="missing_terminal_state",
                error_message=f"worker exited with code {return_code} without a terminal status",
            )
            return self.artifacts.read_status(handle.run_id)
        self._reap(handle)
        return status

    @staticmethod
    def _stop(handle: JobHandle) -> None:
        if handle.process.poll() is None:
            handle.process.terminate()
            try:
                handle.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                handle.process.kill()
                handle.process.wait(timeout=2)

    @staticmethod
    def _reap(handle: JobHandle) -> None:
        if handle.process.poll() is None:
            # 终态文件可能先于解释器退出可见；给 worker 一个短窗口完成 error.log
            # 等尾部写入，只有自然退出未完成时才强制停止。
            try:
                handle.process.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                V2JobManager._stop(handle)
        for stream in (handle.process.stdout, handle.process.stderr):
            if stream is not None:
                stream.close()

    def wait(self, handle: JobHandle, timeout_s: float = 20.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            status = self.poll(handle)
            if status.get("status") in {"succeeded", "failed", "cancelled"}:
                self._reap(handle)
                return status
            time.sleep(0.05)
        if handle.process.poll() is None:
            self._stop(handle)
        self._reap(handle)
        self.artifacts.update_status(
            handle.run_id,
            status="failed",
            stage="worker",
            error_code="timeout",
            error_message=f"worker exceeded timeout_s={timeout_s}",
        )
        return self.artifacts.read_status(handle.run_id)


def new_config(**overrides: Any) -> SimulationConfig:
    values: dict[str, Any] = {"run_id": f"v2-{uuid4().hex[:10]}"}
    model_id = overrides.get("model_id", SimulationConfig.__dataclass_fields__["model_id"].default)
    if model_id == "panda-cube-v1":
        values.update({"model_id": model_id, "max_steps": 7000, "initial_object_x": .45, "target_x": .45})
    values.update(overrides)
    config = SimulationConfig(**values)
    validate_config(config)
    return config


def validate_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id 必须是非空字符串")
    if run_id in {".", ".."} or any(separator in run_id for separator in '<>:"/\\|?*') or run_id.endswith((' ', '.')):
        raise ValueError("run_id 必须是安全的单目录名")
    if Path(run_id).is_absolute() or os.path.isabs(run_id):
        raise ValueError("run_id 不得是绝对路径或包含盘符")


def validate_config(config: SimulationConfig) -> SimulationConfig:
    """在进程启动前冻结边界，避免未知模型或非法数值进入长任务。"""
    validate_run_id(config.run_id)
    if not isinstance(config.strategy_id, str) or not config.strategy_id.strip():
        raise ValueError("strategy_id必须是非空方案名称")
    if not isinstance(config.model_id,str) or config.model_id not in {"minimal_planar_pick_place", "panda-cube-v1"}:
        raise ValueError(f"未知模型：{config.model_id}")
    if not isinstance(config.max_steps, int) or isinstance(config.max_steps, bool) or config.max_steps <= 0:
        raise ValueError("max_steps 必须是正整数")
    for name in ("wall_timeout_s", "grasp_offset", "initial_object_x", "target_x"):
        value = getattr(config, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} 必须是有限 int/float 且不能是 bool")
    if config.wall_timeout_s <= 0:
        raise ValueError("wall_timeout_s 必须大于 0")
    if config.fault_mode is not None and (not isinstance(config.fault_mode,str) or config.fault_mode not in {"crash", "timeout"}):
        raise ValueError(f"未知故障模式：{config.fault_mode}")
    return config


def validate_summary(result: dict[str, Any]) -> dict[str, Any]:
    """页面、列表和比较共用报告语义，避免各自解释同一份结果。"""
    if not isinstance(result, dict) or not isinstance(result.get('success'), bool):
        raise ValueError('任务报告必须含布尔success')
    validate_run_id(result.get('run_id'))
    if result.get('final_status') != ('succeeded' if result['success'] else 'failed'):
        raise ValueError('任务结果与终态不一致')
    duration = result.get('duration_ms')
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0:
        raise ValueError('仿真时长无效')
    failure, criteria = result.get('failure'), result.get('success_criteria')
    if not isinstance(failure, dict) or not isinstance(criteria, dict) or not isinstance(failure.get('observation'), str):
        raise ValueError('报告结构或结果观察无效')
    for name in ('target_distance_m', 'target_distance_threshold_m'):
        value = criteria.get(name)
        if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or value < 0:
            raise ValueError('目标距离或阈值无效')
    if 'stable_duration_s' in criteria:
        for name in ('stable_duration_s','stable_window_s'):
            value = criteria.get(name)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value < 0:
                raise ValueError('稳定窗口无效')
        if not all(isinstance(criteria.get(name),bool) for name in ('lifted','released')):
            raise ValueError('抓放结果字段无效')
    return result


def load_trajectory(artifact_dir: Path) -> list[dict[str, Any]]:
    path = artifact_dir / "trajectory.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_comparison_report(artifact_dirs: list[Path]) -> dict[str, Any]:
    """完整性先于可比性；真实参数先于显示名称；重复次数不升级泛化证据。"""
    from hashlib import sha256
    if len(artifact_dirs) < 2:
        raise ValueError("comparison requires at least two run artifacts")
    paths = [Path(path).resolve() for path in artifact_dirs]
    run_ids = [path.name for path in paths]

    def reject(reasons, identity=None, differences=None, same=False):
        return {
            "schema_version": V2_SCHEMA_VERSION, "run_ids": run_ids, "strategy_ids": [],
            "same_initial_state": same, "controlled_differences": differences or {},
            "identity_differences": identity or {"invalid_artifacts": reasons},
            "comparison_status": "rejected", "comparison_kind": "rejected",
            "rejected_samples": reasons, "strategy_groups": {}, "parameter_groups": [],
            "generalization_supported": False, "sample_scope": "rejected_input",
            "sample_count": 0, "success_count": None, "success_rate": None,
            "evidence_status": "rejected_invalid_input",
            "conclusion": "拒绝产生优劣结论：输入损坏、重复或实验条件不一致；未计入统计。",
            "scope": "only complete distinct comparable physical runs",
        }

    if len(set(paths)) != len(paths) or len(set(run_ids)) != len(run_ids):
        return reject([{"reason": "重复运行不能充当独立样本"}], {"duplicate_run_id": run_ids})
    metas, summaries, configs, models, errors = [], [], [], [], []
    for path in paths:
        try:
            meta, summary = _read_json(path / "meta.json"), _read_json(path / "summary.json")
            if not isinstance(meta, dict) or not isinstance(summary, dict):
                raise ValueError("元数据与报告必须是JSON对象")
            validate_summary(summary)
            config = meta.get("config")
            if not isinstance(config, dict):
                raise ValueError("缺少运行配置")
            environment = meta.get("environment")
            if not isinstance(environment, dict):
                raise ValueError("缺少运行环境")
            model_id = config.get("model_id", environment.get("model_name"))
            if environment.get("model_name") != model_id:
                raise ValueError("配置与环境模型不一致")
            validate_config(SimulationConfig(**dict(config, model_id=model_id)))
            if not isinstance(summary.get("success"), bool):
                raise ValueError("success必须是布尔值")
            if summary.get("final_status") != ("succeeded" if summary["success"] else "failed"):
                raise ValueError("summary success与final_status冲突")
            if any(value != path.name for value in (meta.get("run_id"), config.get("run_id"), summary.get("run_id"))):
                raise ValueError("运行ID与目录不一致")
            if not isinstance(meta.get("initial_state"), dict) or not meta["initial_state"]:
                raise ValueError("缺少初始状态")
            if config.get("fault_mode") is not None:
                raise ValueError("诊断注入运行不属于任务效果比较")
            # 配置副本和终态属于同一运行，不能让手动篡改的摘要掩盖原始记录。
            disk_config, status = _read_json(path/"config.json"), _read_json(path/"status.json")
            if disk_config != config or status.get("run_id") != path.name or status.get("status") != summary["final_status"] or status.get("error_code"):
                raise ValueError("配置/状态与任务报告不一致")
            frames, events = _load_jsonl(path/"trajectory.jsonl"), _load_jsonl(path/"events.jsonl")
            if not frames or not events:
                raise ValueError("缺少轨迹或事件证据")
            if model_id == "panda-cube-v1":
                from robot_mvp.panda_artifacts import validate_panda
                validate_panda(path, meta, summary, frames, events)
                if not all(meta.get(key) for key in ("scene_sha256", "evaluation", "controller_version")):
                    raise ValueError("Panda模型、评估或控制器身份缺失")
                if not meta.get("model", {}).get("model_hash"):
                    raise ValueError("model_hash缺失")
            else:
                if meta.get("artifact_schema") != "v2.0":
                    raise ValueError("历史平面产物版本不匹配")
                if any(frame.get("run_id") != path.name for frame in frames + events):
                    raise ValueError("轨迹或事件来自其他运行")
            # 非有限数不能参与分组或身份比较，也不能被字符串化伪装为有效配置。
            json.dumps([meta, summary], sort_keys=True, allow_nan=False)
            metas.append(meta); summaries.append(summary); configs.append(config); models.append(model_id)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            errors.append({"artifact_dir": str(path), "reason": str(error)})
    if errors:
        return reject(errors)

    def canonical(value):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)

    initial_states = [canonical(meta["initial_state"]) for meta in metas]
    same_initial = len(set(initial_states)) == 1
    identity = {}
    if len(set(models)) != 1:
        identity["model_id"] = sorted(set(models))
    if not same_initial:
        identity["initial_state"] = ["mismatch"]
    for key in ("environment", "artifact_schema", "scene_sha256", "evaluation", "controller_version"):
        values = {canonical(meta.get(key)) for meta in metas}
        if len(values) > 1:
            identity[key] = sorted(values)
    model_hashes = {meta.get("model", {}).get("model_hash") for meta in metas}
    if len(model_hashes) > 1:
        identity["model_hash"] = sorted(model_hashes, key=str)
    all_keys = set().union(*(config.keys() for config in configs)) - {"run_id", "strategy_id"}
    differences = {}
    for key in sorted(all_keys):
        unique = {canonical(config.get(key)): config.get(key) for config in configs}
        if len(unique) > 1:
            differences[key] = [unique[value] for value in sorted(unique)]
    if identity or set(differences) - {"grasp_offset"}:
        return reject([], identity or {"uncontrolled_parameters": sorted(set(differences)-{"grasp_offset"})}, differences, same_initial)

    # 同名可含不同参数；异名也可能是同一参数方案。分组不依赖展示标签。
    grouped = {}
    for config, summary in zip(configs, summaries):
        configuration = {key: config.get(key) for key in sorted(all_keys)}
        signature = canonical(configuration)
        group = grouped.setdefault(signature, {
            "parameter_set_id": sha256(signature.encode()).hexdigest()[:12],
            "configuration": configuration, "strategy_ids": [], "run_ids": [],
            "sample_count": 0, "success_count": 0,
        })
        if config["strategy_id"] not in group["strategy_ids"]:
            group["strategy_ids"].append(config["strategy_id"])
        group["run_ids"].append(config["run_id"])
        group["sample_count"] += 1
        group["success_count"] += int(summary["success"])
    parameter_groups = list(grouped.values())
    strategy_groups = {}
    for group in parameter_groups:
        group["success_rate"] = group["success_count"] / group["sample_count"]
        label = " / ".join(map(str, group["strategy_ids"]))
        collision = sum(label == " / ".join(map(str, item["strategy_ids"])) for item in parameter_groups) > 1
        key = label + ("@" + group["parameter_set_id"] if collision else "")
        strategy_groups[key] = dict(group)
    repeatability = len(parameter_groups) == 1
    success_count = sum(summary["success"] for summary in summaries)
    return {
        "schema_version": V2_SCHEMA_VERSION, "run_ids": run_ids,
        "strategy_ids": [config["strategy_id"] for config in configs],
        "same_initial_state": same_initial, "controlled_differences": differences,
        "identity_differences": {}, "comparison_status": "comparable",
        "comparison_kind": "repeatability_check" if repeatability else "controlled_parameter_comparison",
        "rejected_samples": [], "strategy_groups": strategy_groups, "parameter_groups": parameter_groups,
        "generalization_supported": False, "sample_scope": "fixed_initial_state_repetition",
        "sample_count": len(paths), "success_count": success_count,
        "success_rate": success_count / len(paths), "evidence_status": "evidence_insufficient",
        "conclusion": (
            "相同参数与初始条件，本次仅检查重复性，不是两版策略比较；泛化证据不足，需要补测。"
            if repeatability else
            "可核对当前固定条件下的参数与结果差异；样本不足以判断策略全面改善，需要补测。"
        ),
        "scope": "one model and initial state; descriptive observations, not generalization",
    }
