from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

RunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


@dataclass(slots=True)
class TaskTemplate:
    id: str
    name: str
    description: str
    steps: list[str]
    success_criteria: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TaskTemplate":
        return cls(
            id=payload["id"],
            name=payload["name"],
            description=payload["description"],
            steps=list(payload.get("steps", [])),
            success_criteria=list(payload.get("success_criteria", [])),
        )


@dataclass(slots=True)
class StrategyVersion:
    id: str
    name: str
    version: str
    notes: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StrategyVersion":
        return cls(
            id=payload["id"],
            name=payload["name"],
            version=payload["version"],
            notes=payload["notes"],
            created_at=payload["created_at"],
        )


@dataclass(slots=True)
class BenchmarkSuite:
    id: str
    name: str
    description: str
    case_ids: list[str]
    focus_metrics: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BenchmarkSuite":
        return cls(
            id=payload["id"],
            name=payload["name"],
            description=payload["description"],
            case_ids=list(payload.get("case_ids", [])),
            focus_metrics=list(payload.get("focus_metrics", [])),
        )


@dataclass(slots=True)
class BenchmarkBatch:
    id: str
    suite_id: str
    task_template_id: str
    strategy_version_id: str
    created_at: str
    run_ids: list[str]
    operator_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BenchmarkBatch":
        return cls(
            id=payload["id"],
            suite_id=payload["suite_id"],
            task_template_id=payload["task_template_id"],
            strategy_version_id=payload["strategy_version_id"],
            created_at=payload["created_at"],
            run_ids=list(payload.get("run_ids", [])),
            operator_note=payload.get("operator_note"),
        )


@dataclass(slots=True)
class RunResult:
    success: bool
    final_status: RunStatus
    failure_reason: str | None
    key_observation: str
    quality_score: float
    notes: str
    scenario_label: str
    operator_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunResult":
        return cls(
            success=bool(payload["success"]),
            final_status=payload["final_status"],
            failure_reason=payload.get("failure_reason"),
            key_observation=payload["key_observation"],
            quality_score=float(payload["quality_score"]),
            notes=payload["notes"],
            scenario_label=payload["scenario_label"],
            operator_note=payload.get("operator_note"),
        )


@dataclass(slots=True)
class RunRecord:
    id: str
    task_template_id: str
    strategy_version_id: str
    status: RunStatus
    started_at: str
    ended_at: str
    duration_ms: int
    result: RunResult
    input_params: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["result"] = self.result.to_dict()
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunRecord":
        return cls(
            id=payload["id"],
            task_template_id=payload["task_template_id"],
            strategy_version_id=payload["strategy_version_id"],
            status=payload["status"],
            started_at=payload["started_at"],
            ended_at=payload["ended_at"],
            duration_ms=int(payload["duration_ms"]),
            result=RunResult.from_dict(payload["result"]),
            input_params=dict(payload.get("input_params", {})),
            tags=list(payload.get("tags", [])),
        )


@dataclass(slots=True)
class RunEvent:
    run_id: str
    timestamp: str
    stage: str
    level: str
    message: str
    offset_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunEvent":
        return cls(
            run_id=payload["run_id"],
            timestamp=payload["timestamp"],
            stage=payload["stage"],
            level=payload["level"],
            message=payload["message"],
            offset_ms=int(payload["offset_ms"]),
        )


@dataclass(slots=True)
class ReplayFrame:
    run_id: str
    timestamp: str
    arm_pose: dict[str, Any]
    gripper_state: str
    target_state: dict[str, Any]
    offset_ms: int
    stage: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReplayFrame":
        return cls(
            run_id=payload["run_id"],
            timestamp=payload["timestamp"],
            arm_pose=dict(payload["arm_pose"]),
            gripper_state=payload["gripper_state"],
            target_state=dict(payload["target_state"]),
            offset_ms=int(payload["offset_ms"]),
            stage=payload["stage"],
        )


@dataclass(slots=True)
class ComparisonSummary:
    left_run_id: str
    right_run_id: str
    success_diff: str
    duration_diff_ms: int
    failure_reason_diff: str
    log_summary_diff: str
    recommended_run_id: str
    recommended_reason: str


@dataclass(slots=True)
class ProjectedRunView:
    run_record: RunRecord
    visible_events: list[RunEvent]
    visible_frames: list[ReplayFrame]
    progress: float
    current_stage: str
    completed: bool
    elapsed_ms: int

    @property
    def latest_frame(self) -> ReplayFrame | None:
        if not self.visible_frames:
            return None
        return self.visible_frames[-1]


@dataclass(slots=True)
class StoreData:
    task_templates: list[TaskTemplate]
    strategy_versions: list[StrategyVersion]
    benchmark_suites: list[BenchmarkSuite]
    benchmark_batches: list[BenchmarkBatch]
    run_records: list[RunRecord]
    run_events: list[RunEvent]
    replay_frames: list[ReplayFrame]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_templates": [template.to_dict() for template in self.task_templates],
            "strategy_versions": [strategy.to_dict() for strategy in self.strategy_versions],
            "benchmark_suites": [suite.to_dict() for suite in self.benchmark_suites],
            "benchmark_batches": [batch.to_dict() for batch in self.benchmark_batches],
            "run_records": [run.to_dict() for run in self.run_records],
            "run_events": [event.to_dict() for event in self.run_events],
            "replay_frames": [frame.to_dict() for frame in self.replay_frames],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StoreData":
        return cls(
            task_templates=[
                TaskTemplate.from_dict(item) for item in payload.get("task_templates", [])
            ],
            strategy_versions=[
                StrategyVersion.from_dict(item)
                for item in payload.get("strategy_versions", [])
            ],
            benchmark_suites=[
                BenchmarkSuite.from_dict(item)
                for item in payload.get("benchmark_suites", [])
            ],
            benchmark_batches=[
                BenchmarkBatch.from_dict(item)
                for item in payload.get("benchmark_batches", [])
            ],
            run_records=[RunRecord.from_dict(item) for item in payload.get("run_records", [])],
            run_events=[RunEvent.from_dict(item) for item in payload.get("run_events", [])],
            replay_frames=[
                ReplayFrame.from_dict(item) for item in payload.get("replay_frames", [])
            ],
        )
