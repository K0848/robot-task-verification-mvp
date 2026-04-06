from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from robot_mvp.models import (
    BenchmarkBatch,
    BenchmarkSuite,
    ComparisonSummary,
    ProjectedRunView,
    ReplayFrame,
    RunEvent,
    RunRecord,
    RunResult,
    StoreData,
    StrategyVersion,
    TaskTemplate,
)

PRESET_LABELS = {
    "auto": "自动判断",
    "success": "标准成功",
    "grasp_slip": "抓取失败",
    "placement_offset": "放置偏移",
}
PACE_DISPLAY_LABELS = {
    "default": "默认节奏",
    "fast": "快节奏",
    "slow": "慢速讲解",
}
FOCUS_DISPLAY_LABELS = {
    "overview": "全链路",
    "grasp": "强调抓取",
    "place": "强调放置",
    "failure": "强调失败",
}
_PACE_KEYWORD_RULES = (
    ("fast", 1.35, ("快节奏", "高速", "加速", "快一点")),
    ("slow", 0.70, ("慢速", "慢一点", "讲解", "演示讲解")),
)
_FOCUS_KEYWORD_RULES = (
    ("grasp", ("强调抓取", "抓取细节", "看抓取")),
    ("place", ("强调放置", "放置细节", "看放置")),
    ("failure", ("强调失败", "失败复盘", "看失败")),
)
_DEFAULT_DYNAMIC_PROFILE = {
    "pace": "default",
    "pace_multiplier": 1.0,
    "focus": "overview",
    "matched_keywords": [],
}
_STRATEGY_DISPLAY_NAMES = {
    "heuristic-baseline": "规则阈值基线策略",
    "stable-policy": "稳定抓取补偿策略",
    "fast-motion": "高速节拍转运策略",
}
_STRATEGY_DEFAULT_PACE = {
    "heuristic-baseline": ("default", 1.0),
    "stable-policy": ("slow", 0.70),
    "fast-motion": ("fast", 1.35),
}

_SCENARIO_SPECS: dict[str, dict[str, Any]] = {
    "success": {
        "label": "标准成功",
        "final_status": "succeeded",
        "success": True,
        "failure_reason": None,
        "key_observation": "夹爪闭环控制稳定，目标物成功落入托盘中心区域。",
        "notes": "整条轨迹平滑，没有出现停顿和抖动。",
        "score_bonus": 0.08,
        "events": [
            (0.00, "准备环境", "info", "加载工位配置、目标物和托盘坐标"),
            (0.10, "机械臂归位", "info", "完成标定，末端执行器回到安全位"),
            (0.24, "接近目标", "info", "按照规划轨迹接近目标物"),
            (0.44, "执行抓取", "success", "夹爪闭合，目标物抓取稳定"),
            (0.66, "转运中", "info", "沿避障轨迹移动到托盘上方"),
            (0.84, "放置校验", "success", "目标物已落入托盘中心，偏差低于 5 mm"),
            (1.00, "任务完成", "success", "任务完成，生成结构化运行报告"),
        ],
        "frames": [
            (0.00, 16, 86, 8, "open", 34, 58, False, False, "准备环境"),
            (0.10, 20, 80, 12, "open", 34, 58, False, False, "机械臂归位"),
            (0.24, 28, 64, 18, "open", 34, 58, False, False, "接近目标"),
            (0.38, 32, 58, 8, "open", 34, 58, False, False, "对准目标"),
            (0.44, 34, 58, 8, "closed", 34, 58, True, False, "执行抓取"),
            (0.56, 42, 46, 18, "closed", 42, 46, True, False, "抬升目标"),
            (0.66, 56, 42, 24, "closed", 56, 42, True, False, "转运中"),
            (0.76, 68, 46, 24, "closed", 68, 46, True, False, "接近托盘"),
            (0.84, 76, 58, 12, "open", 76, 58, False, True, "放置校验"),
            (0.92, 72, 52, 18, "open", 76, 58, False, True, "回撤"),
            (1.00, 24, 78, 10, "open", 76, 58, False, True, "任务完成"),
        ],
    },
    "grasp_slip": {
        "label": "抓取失败",
        "final_status": "failed",
        "success": False,
        "failure_reason": "抓取阶段夹爪力反馈异常，目标物滑落。",
        "key_observation": "目标物在夹爪闭合后 1 秒内滑落，未进入转运阶段。",
        "notes": "建议优先检查夹爪阈值和接近速度参数。",
        "score_bonus": -0.25,
        "events": [
            (0.00, "准备环境", "info", "载入目标物位置和抓取策略"),
            (0.18, "机械臂归位", "info", "完成标定，准备接近目标物"),
            (0.40, "接近目标", "info", "末端执行器到达抓取窗口"),
            (0.66, "执行抓取", "warning", "夹爪闭合后出现力反馈波动"),
            (1.00, "任务失败", "error", "目标物滑落，运行终止并生成失败报告"),
        ],
        "frames": [
            (0.00, 16, 86, 8, "open", 34, 58, False, False, "准备环境"),
            (0.18, 22, 76, 12, "open", 34, 58, False, False, "机械臂归位"),
            (0.40, 28, 64, 16, "open", 34, 58, False, False, "接近目标"),
            (0.56, 32, 58, 10, "open", 34, 58, False, False, "对准目标"),
            (0.66, 34, 58, 8, "closed", 34, 58, True, False, "执行抓取"),
            (0.82, 34, 64, 6, "closed", 32, 62, False, False, "目标物滑落"),
            (1.00, 20, 80, 10, "open", 32, 62, False, False, "任务失败"),
        ],
    },
    "placement_offset": {
        "label": "放置偏移",
        "final_status": "failed",
        "success": False,
        "failure_reason": "放置阶段偏移超阈值，目标物落点偏离托盘。",
        "key_observation": "目标物成功抓取并转运，但最终落点偏离目标区域。",
        "notes": "建议检查末端校准参数和放置高度补偿。",
        "score_bonus": -0.1,
        "events": [
            (0.00, "准备环境", "info", "读取任务模板、目标物和托盘配置"),
            (0.12, "机械臂归位", "info", "完成机械臂标定"),
            (0.24, "接近目标", "info", "进入抓取准备姿态"),
            (0.40, "执行抓取", "success", "目标物抓取稳定"),
            (0.64, "转运中", "info", "沿最短轨迹移动到放置区"),
            (0.84, "放置校验", "warning", "检测到放置落点偏差正在增大"),
            (1.00, "任务失败", "error", "偏移超过阈值，结果标记为失败"),
        ],
        "frames": [
            (0.00, 16, 86, 8, "open", 34, 58, False, False, "准备环境"),
            (0.12, 22, 78, 12, "open", 34, 58, False, False, "机械臂归位"),
            (0.24, 28, 64, 18, "open", 34, 58, False, False, "接近目标"),
            (0.40, 34, 58, 8, "closed", 34, 58, True, False, "执行抓取"),
            (0.54, 48, 46, 20, "closed", 48, 46, True, False, "抬升目标"),
            (0.64, 62, 42, 24, "closed", 62, 42, True, False, "转运中"),
            (0.78, 74, 48, 22, "closed", 74, 48, True, False, "准备放置"),
            (0.84, 82, 60, 10, "open", 84, 62, False, False, "放置校验"),
            (1.00, 24, 78, 10, "open", 84, 62, False, False, "任务失败"),
        ],
    },
}

_OBJECT_LABELS = ["轴承套环", "传感器外壳", "阀门盖", "立方体工件", "连接法兰"]
_SOURCE_BINS = ["A1", "A2", "B1", "B2", "C1"]
_TARGET_SLOTS = ["Tray-01", "Tray-02", "Tray-03"]
_BENCHMARK_CASE_SPECS: dict[str, dict[str, Any]] = {
    "standard-pick": {
        "name": "标准抓取",
        "description": "标准工位、无遮挡、常规节拍。",
        "scenario_by_strategy": {
            "heuristic-baseline": "success",
            "stable-policy": "success",
            "fast-motion": "success",
        },
    },
    "low-grip-margin": {
        "name": "低抓取裕量",
        "description": "目标工件边缘抓取窗口更窄，考验夹爪力控稳定性。",
        "scenario_by_strategy": {
            "heuristic-baseline": "grasp_slip",
            "stable-policy": "success",
            "fast-motion": "grasp_slip",
        },
    },
    "tight-placement-window": {
        "name": "严格放置容差",
        "description": "放置托盘容差收紧，要求末端校准更稳定。",
        "scenario_by_strategy": {
            "heuristic-baseline": "placement_offset",
            "stable-policy": "success",
            "fast-motion": "placement_offset",
        },
    },
    "occluded-approach": {
        "name": "遮挡接近",
        "description": "接近路径受轻微遮挡，考验策略恢复能力。",
        "scenario_by_strategy": {
            "heuristic-baseline": "grasp_slip",
            "stable-policy": "success",
            "fast-motion": "placement_offset",
        },
    },
    "fast-cycle": {
        "name": "快速节拍",
        "description": "要求在更短节拍内完成抓取与放置。",
        "scenario_by_strategy": {
            "heuristic-baseline": "success",
            "stable-policy": "success",
            "fast-motion": "success",
        },
    },
}


def seed_benchmark_suites() -> list[BenchmarkSuite]:
    return [
        BenchmarkSuite(
            id="embodied-core-v1",
            name="具身基础作业集",
            description="覆盖抓取稳定性、放置精度和恢复能力的最小验证集。",
            case_ids=[
                "standard-pick",
                "low-grip-margin",
                "tight-placement-window",
                "occluded-approach",
                "fast-cycle",
            ],
            focus_metrics=["成功率", "平均耗时", "失败类型分布"],
        ),
        BenchmarkSuite(
            id="demo-readiness-v1",
            name="演示优先评测集",
            description="偏向现场演示场景，关注稳定成功和节拍表现。",
            case_ids=[
                "standard-pick",
                "fast-cycle",
                "tight-placement-window",
                "standard-pick",
            ],
            focus_metrics=["成功率", "质量分", "演示稳定性"],
        ),
    ]


def now_local() -> datetime:
    return datetime.now().astimezone()


def to_iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def format_duration(duration_ms: int) -> str:
    total_seconds = max(duration_ms // 1000, 0)
    minutes, seconds = divmod(total_seconds, 60)
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def seed_store_data(reference_time: datetime | None = None) -> StoreData:
    current = reference_time or now_local()
    task_templates = [
        TaskTemplate(
            id="pick-and-place",
            name="抓取并放置验证",
            description="验证机械臂是否能完成单个工件的抓取、转运和放置闭环。",
            steps=[
                "加载工位配置",
                "机械臂归位",
                "接近目标物",
                "执行抓取",
                "转运至托盘",
                "放置并校验",
            ],
            success_criteria=[
                "目标物被稳定抓取",
                "运行过程中无中断",
                "落点偏差小于 5 mm",
            ],
        )
    ]
    strategy_versions = [
        StrategyVersion(
            id="heuristic-baseline",
            name=_STRATEGY_DISPLAY_NAMES["heuristic-baseline"],
            version="v0.9",
            notes="规则驱动，参数稳定但对夹爪阈值较敏感。",
            created_at=to_iso(current - timedelta(days=30)),
        ),
        StrategyVersion(
            id="stable-policy",
            name=_STRATEGY_DISPLAY_NAMES["stable-policy"],
            version="v1.1",
            notes="强调稳定抓取和校准补偿，成功率最高。",
            created_at=to_iso(current - timedelta(days=18)),
        ),
        StrategyVersion(
            id="fast-motion",
            name=_STRATEGY_DISPLAY_NAMES["fast-motion"],
            version="v1.3",
            notes="缩短整体时长，但放置阶段容错更低。",
            created_at=to_iso(current - timedelta(days=8)),
        ),
    ]

    schedule = [
        ("stable-policy", "success", 46, 0),
        ("heuristic-baseline", "grasp_slip", 40, 1),
        ("fast-motion", "placement_offset", 35, 2),
        ("stable-policy", "success", 30, 3),
        ("heuristic-baseline", "success", 26, 4),
        ("fast-motion", "success", 22, 0),
        ("stable-policy", "success", 18, 1),
        ("fast-motion", "grasp_slip", 14, 2),
        ("heuristic-baseline", "placement_offset", 9, 3),
        ("stable-policy", "success", 4, 4),
    ]

    strategy_map = {strategy.id: strategy for strategy in strategy_versions}
    task = task_templates[0]
    run_records: list[RunRecord] = []
    run_events: list[RunEvent] = []
    replay_frames: list[ReplayFrame] = []

    for index, (strategy_id, scenario_key, minutes_ago, object_index) in enumerate(
        schedule, start=1
    ):
        started_at = current - timedelta(minutes=minutes_ago)
        run_id = f"run-seed-{index:03d}"
        run, events, frames = create_run_bundle(
            task_template=task,
            strategy=strategy_map[strategy_id],
            started_at=started_at,
            scenario_key=scenario_key,
            run_id=run_id,
            object_index=object_index,
            live=False,
        )
        run_records.append(run)
        run_events.extend(events)
        replay_frames.extend(frames)

    run_records.sort(key=lambda item: item.started_at, reverse=True)
    return StoreData(
        task_templates=task_templates,
        strategy_versions=strategy_versions,
        benchmark_suites=seed_benchmark_suites(),
        benchmark_batches=[],
        run_records=run_records,
        run_events=run_events,
        replay_frames=replay_frames,
    )


def create_live_run_bundle(
    task_template: TaskTemplate,
    strategy: StrategyVersion,
    preset_key: str = "auto",
    operator_note: str | None = None,
    resolved_scenario: str | None = None,
    dynamic_profile: dict[str, Any] | None = None,
) -> tuple[RunRecord, list[RunEvent], list[ReplayFrame]]:
    started_at = now_local()
    chosen_scenario = resolved_scenario or resolve_preset(strategy.id, preset_key, started_at)
    effective_profile = (
        normalize_dynamic_profile(dynamic_profile)
        if dynamic_profile is not None
        else resolve_dynamic_profile(strategy.id, operator_note)
    )
    run_id = f"run-live-{started_at.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
    return create_run_bundle(
        task_template=task_template,
        strategy=strategy,
        started_at=started_at,
        scenario_key=chosen_scenario,
        run_id=run_id,
        object_index=started_at.second % len(_OBJECT_LABELS),
        operator_note=operator_note,
        extra_input_params={
            "requested_preset": preset_key,
            "resolved_scenario": chosen_scenario,
            "dynamic_profile": effective_profile,
        },
        live=True,
    )


def create_preview_bundle(
    task_template: TaskTemplate,
    strategy: StrategyVersion,
    preset_key: str = "auto",
    operator_note: str | None = None,
    reference_time: datetime | None = None,
    resolved_scenario: str | None = None,
) -> tuple[RunRecord, list[RunEvent], list[ReplayFrame]]:
    preview_time = reference_time or now_local()
    chosen_scenario = resolved_scenario or resolve_preset(strategy.id, preset_key, preview_time)
    dynamic_profile = resolve_dynamic_profile(strategy.id, operator_note)
    run_id = f"preview-{strategy.id}-{chosen_scenario}"
    return create_run_bundle(
        task_template=task_template,
        strategy=strategy,
        started_at=preview_time,
        scenario_key=chosen_scenario,
        run_id=run_id,
        object_index=preview_time.second % len(_OBJECT_LABELS),
        operator_note=operator_note,
        extra_input_params={
            "requested_preset": preset_key,
            "resolved_scenario": chosen_scenario,
            "dynamic_profile": dynamic_profile,
        },
        live=False,
    )


def create_benchmark_batch_bundle(
    task_template: TaskTemplate,
    strategy: StrategyVersion,
    suite: BenchmarkSuite,
    operator_note: str | None = None,
    created_at: datetime | None = None,
) -> tuple[BenchmarkBatch, list[RunRecord], list[RunEvent], list[ReplayFrame]]:
    created = created_at or now_local()
    batch_id = f"bench-{created.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
    base_start = created - timedelta(seconds=len(suite.case_ids) * 70)
    runs: list[RunRecord] = []
    events: list[RunEvent] = []
    frames: list[ReplayFrame] = []

    for index, case_id in enumerate(suite.case_ids, start=1):
        case_spec = _BENCHMARK_CASE_SPECS[case_id]
        scenario_key = resolve_benchmark_case_scenario(case_id, strategy.id)
        started_at = base_start + timedelta(seconds=(index - 1) * 70)
        case_note = case_spec["name"]
        if operator_note and operator_note.strip():
            case_note = f"{operator_note.strip()} / {case_spec['name']}"
        run, run_events, run_frames = create_run_bundle(
            task_template=task_template,
            strategy=strategy,
            started_at=started_at,
            scenario_key=scenario_key,
            run_id=f"{batch_id}-run-{index:02d}",
            object_index=index - 1,
            operator_note=case_note,
            extra_input_params={
                "benchmark_suite_id": suite.id,
                "benchmark_case_id": case_id,
                "benchmark_case_name": case_spec["name"],
                "benchmark_case_description": case_spec["description"],
            },
            extra_tags=[
                "benchmark-generated",
                f"benchmark-batch:{batch_id}",
                f"benchmark-suite:{suite.id}",
                f"benchmark-case:{case_id}",
            ],
            live=False,
        )
        runs.append(run)
        events.extend(run_events)
        frames.extend(run_frames)

    batch = BenchmarkBatch(
        id=batch_id,
        suite_id=suite.id,
        task_template_id=task_template.id,
        strategy_version_id=strategy.id,
        created_at=to_iso(created),
        run_ids=[run.id for run in runs],
        operator_note=operator_note.strip() if operator_note and operator_note.strip() else None,
    )
    return batch, runs, events, frames


def resolve_preset(strategy_id: str, preset_key: str, now: datetime) -> str:
    if preset_key != "auto":
        return preset_key
    if strategy_id == "stable-policy":
        return "success"
    if strategy_id == "fast-motion":
        return "placement_offset" if now.second % 2 else "success"
    return "grasp_slip" if now.second % 3 == 0 else "success"


def resolve_benchmark_case_scenario(case_id: str, strategy_id: str) -> str:
    case_spec = _BENCHMARK_CASE_SPECS[case_id]
    return case_spec["scenario_by_strategy"][strategy_id]


def create_run_bundle(
    task_template: TaskTemplate,
    strategy: StrategyVersion,
    started_at: datetime,
    scenario_key: str,
    run_id: str,
    object_index: int = 0,
    operator_note: str | None = None,
    extra_input_params: dict[str, Any] | None = None,
    extra_tags: list[str] | None = None,
    live: bool = False,
) -> tuple[RunRecord, list[RunEvent], list[ReplayFrame]]:
    scenario = _SCENARIO_SPECS[scenario_key]
    duration_ms = estimate_duration_ms(strategy.id, scenario_key)
    ended_at = started_at + timedelta(milliseconds=duration_ms)
    object_label = _OBJECT_LABELS[object_index % len(_OBJECT_LABELS)]
    target_slot = _TARGET_SLOTS[object_index % len(_TARGET_SLOTS)]
    source_bin = _SOURCE_BINS[object_index % len(_SOURCE_BINS)]
    base_score = {
        "heuristic-baseline": 0.72,
        "stable-policy": 0.88,
        "fast-motion": 0.81,
    }[strategy.id]
    quality_score = min(max(base_score + scenario["score_bonus"], 0.15), 0.98)

    result = RunResult(
        success=scenario["success"],
        final_status=scenario["final_status"],
        failure_reason=scenario["failure_reason"],
        key_observation=scenario["key_observation"],
        quality_score=round(quality_score, 2),
        notes=scenario["notes"],
        scenario_label=scenario["label"],
        operator_note=operator_note.strip() if operator_note and operator_note.strip() else None,
    )
    run = RunRecord(
        id=run_id,
        task_template_id=task_template.id,
        strategy_version_id=strategy.id,
        status="running" if live else scenario["final_status"],
        started_at=to_iso(started_at),
        ended_at=to_iso(ended_at),
        duration_ms=duration_ms,
        result=result,
        input_params={
            "object_label": object_label,
            "source_bin": source_bin,
            "target_slot": target_slot,
            "surface": "铝托盘",
        },
        tags=[task_template.id, scenario_key, strategy.id],
    )
    if extra_input_params:
        run.input_params.update(extra_input_params)
    if extra_tags:
        run.tags.extend(extra_tags)

    events = build_events(run_id, started_at, duration_ms, scenario["events"])
    frames = build_frames(
        run_id=run_id,
        started_at=started_at,
        duration_ms=duration_ms,
        frame_specs=scenario["frames"],
        target_slot=target_slot,
        object_label=object_label,
    )
    return run, events, frames


def parse_operator_note_dynamic_profile(operator_note: str | None) -> dict[str, Any]:
    note = (operator_note or "").strip()
    profile = dict(_DEFAULT_DYNAMIC_PROFILE)
    matched_keywords: list[str] = []

    for pace, multiplier, keywords in _PACE_KEYWORD_RULES:
        matched = next((keyword for keyword in keywords if keyword in note), None)
        if matched:
            profile["pace"] = pace
            profile["pace_multiplier"] = multiplier
            matched_keywords.append(matched)
            break

    for focus, keywords in _FOCUS_KEYWORD_RULES:
        matched = next((keyword for keyword in keywords if keyword in note), None)
        if matched:
            profile["focus"] = focus
            matched_keywords.append(matched)
            break

    profile["matched_keywords"] = matched_keywords
    return profile


def default_dynamic_profile_for_strategy(strategy_id: str) -> dict[str, Any]:
    pace, multiplier = _STRATEGY_DEFAULT_PACE.get(
        strategy_id,
        (_DEFAULT_DYNAMIC_PROFILE["pace"], _DEFAULT_DYNAMIC_PROFILE["pace_multiplier"]),
    )
    return {
        "pace": pace,
        "pace_multiplier": multiplier,
        "focus": _DEFAULT_DYNAMIC_PROFILE["focus"],
        "matched_keywords": [],
    }


def resolve_dynamic_profile(strategy_id: str, operator_note: str | None) -> dict[str, Any]:
    profile = default_dynamic_profile_for_strategy(strategy_id)
    note_profile = parse_operator_note_dynamic_profile(operator_note)

    if note_profile["pace"] != _DEFAULT_DYNAMIC_PROFILE["pace"]:
        profile["pace"] = note_profile["pace"]
        profile["pace_multiplier"] = note_profile["pace_multiplier"]

    if note_profile["focus"] != _DEFAULT_DYNAMIC_PROFILE["focus"]:
        profile["focus"] = note_profile["focus"]

    profile["matched_keywords"] = note_profile["matched_keywords"]
    return profile


def normalize_dynamic_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(_DEFAULT_DYNAMIC_PROFILE)
    if not isinstance(profile, dict):
        return normalized

    pace = profile.get("pace")
    if pace in PACE_DISPLAY_LABELS:
        normalized["pace"] = pace

    pace_multiplier = profile.get("pace_multiplier")
    if isinstance(pace_multiplier, (int, float)) and pace_multiplier > 0:
        normalized["pace_multiplier"] = float(pace_multiplier)

    focus = profile.get("focus")
    if focus in FOCUS_DISPLAY_LABELS:
        normalized["focus"] = focus

    matched_keywords = profile.get("matched_keywords")
    if isinstance(matched_keywords, list):
        normalized["matched_keywords"] = [str(item) for item in matched_keywords]

    return normalized


def extract_dynamic_profile(run: RunRecord) -> dict[str, Any]:
    return normalize_dynamic_profile(run.input_params.get("dynamic_profile"))


def compute_display_elapsed_ms(
    elapsed_ms: int,
    duration_ms: int,
    dynamic_profile: dict[str, Any] | None = None,
    *,
    loop: bool = False,
) -> int:
    safe_duration = max(duration_ms, 0)
    if safe_duration == 0:
        return 0
    profile = normalize_dynamic_profile(dynamic_profile)
    scaled = max(0, int(elapsed_ms * profile["pace_multiplier"]))
    if loop:
        return scaled % safe_duration
    return min(scaled, safe_duration)


def build_renderer_payload(
    run: RunRecord,
    events: list[RunEvent],
    frames: list[ReplayFrame],
    view_mode: str,
    *,
    dynamic_profile: dict[str, Any] | None = None,
    animation_mode: str | None = None,
    initial_elapsed_ms: int = 0,
    progress: float | None = None,
    current_stage: str | None = None,
    camera_preset: str = "sim-isometric",
    title: str | None = None,
    compare_label: str | None = None,
) -> dict[str, Any]:
    safe_duration = max(run.duration_ms, 0)
    profile = normalize_dynamic_profile(dynamic_profile or run.input_params.get("dynamic_profile"))
    effective_animation = animation_mode or {
        "preview": "loop",
        "detail": "live",
        "replay": "static",
        "compare": "static",
    }.get(view_mode, "static")
    clamped_elapsed = max(0, initial_elapsed_ms)
    if safe_duration:
        if effective_animation == "loop":
            clamped_elapsed %= safe_duration
        else:
            clamped_elapsed = min(clamped_elapsed, safe_duration)

    effective_progress = progress
    if effective_progress is None:
        effective_progress = (clamped_elapsed / safe_duration) if safe_duration else 0.0

    effective_stage = current_stage
    if effective_stage is None:
        visible_events = [event for event in events if event.offset_ms <= clamped_elapsed]
        effective_stage = visible_events[-1].stage if visible_events else (frames[0].stage if frames else "等待启动")

    return {
        "view_mode": view_mode,
        "title": title or "动作视图",
        "compare_label": compare_label,
        "status": run.status,
        "success": run.result.success,
        "scenario_label": run.result.scenario_label,
        "resolved_scenario": run.input_params.get("resolved_scenario", ""),
        "progress": round(effective_progress, 4),
        "current_stage": effective_stage,
        "highlight_mode": profile["focus"],
        "camera_preset": camera_preset,
        "dynamic_profile": profile,
        "scene": {
            "object_label": run.input_params.get("object_label", "未知工件"),
            "source_bin": run.input_params.get("source_bin", "A1"),
            "target_slot": run.input_params.get("target_slot", "Tray-01"),
            "surface": run.input_params.get("surface", ""),
        },
        "animation": {
            "mode": effective_animation,
            "duration_ms": safe_duration,
            "initial_elapsed_ms": clamped_elapsed,
        },
        "frames": [frame.to_dict() for frame in frames],
        "events": [event.to_dict() for event in events],
    }


def build_events(
    run_id: str,
    started_at: datetime,
    duration_ms: int,
    event_specs: list[tuple[float, str, str, str]],
) -> list[RunEvent]:
    events: list[RunEvent] = []
    for ratio, stage, level, message in event_specs:
        offset_ms = min(int(duration_ms * ratio), duration_ms)
        timestamp = started_at + timedelta(milliseconds=offset_ms)
        events.append(
            RunEvent(
                run_id=run_id,
                timestamp=to_iso(timestamp),
                stage=stage,
                level=level,
                message=message,
                offset_ms=offset_ms,
            )
        )
    return events


def build_frames(
    run_id: str,
    started_at: datetime,
    duration_ms: int,
    frame_specs: list[tuple[float, int, int, int, str, int, int, bool, bool, str]],
    target_slot: str,
    object_label: str,
) -> list[ReplayFrame]:
    frames: list[ReplayFrame] = []
    for ratio, arm_x, arm_y, arm_z, gripper, obj_x, obj_y, held, placed, stage in frame_specs:
        offset_ms = min(int(duration_ms * ratio), duration_ms)
        timestamp = started_at + timedelta(milliseconds=offset_ms)
        frames.append(
            ReplayFrame(
                run_id=run_id,
                timestamp=to_iso(timestamp),
                arm_pose={"x": arm_x, "y": arm_y, "z": arm_z},
                gripper_state=gripper,
                target_state={
                    "object_label": object_label,
                    "target_slot": target_slot,
                    "object_x": obj_x,
                    "object_y": obj_y,
                    "pickup_x": 34,
                    "pickup_y": 58,
                    "dropoff_x": 76,
                    "dropoff_y": 58,
                    "held": held,
                    "placed": placed,
                },
                offset_ms=offset_ms,
                stage=stage,
            )
        )
    return frames


def interpolate_replay_frame(
    frames: list[ReplayFrame], elapsed_ms: int | float
) -> ReplayFrame | None:
    if not frames:
        return None

    clamped = max(frames[0].offset_ms, min(float(elapsed_ms), float(frames[-1].offset_ms)))
    if clamped <= frames[0].offset_ms:
        return ReplayFrame(
            run_id=frames[0].run_id,
            timestamp=frames[0].timestamp,
            arm_pose=dict(frames[0].arm_pose),
            gripper_state=frames[0].gripper_state,
            target_state=dict(frames[0].target_state),
            offset_ms=int(clamped),
            stage=frames[0].stage,
        )
    if clamped >= frames[-1].offset_ms:
        return ReplayFrame(
            run_id=frames[-1].run_id,
            timestamp=frames[-1].timestamp,
            arm_pose=dict(frames[-1].arm_pose),
            gripper_state=frames[-1].gripper_state,
            target_state=dict(frames[-1].target_state),
            offset_ms=int(clamped),
            stage=frames[-1].stage,
        )

    right_index = next(
        index for index, frame in enumerate(frames) if frame.offset_ms >= clamped
    )
    left = frames[right_index - 1]
    right = frames[right_index]
    span = max(right.offset_ms - left.offset_ms, 1)
    ratio = (clamped - left.offset_ms) / span

    def blend(left_value: float, right_value: float) -> float:
        return round(left_value + (right_value - left_value) * ratio, 2)

    def blend_object_position(left_value: float, right_value: float) -> float:
        left_held = bool(left.target_state.get("held"))
        right_held = bool(right.target_state.get("held"))
        if left_held and right_held:
            return blend(float(left_value), float(right_value))
        if not left_held and not right_held:
            return float(left_value)
        # 抓取/释放过渡：物体原地不动，直到 held 状态翻转瞬间再跳到新位置
        return float(right_value) if ratio >= 0.5 else float(left_value)

    numeric_target_keys = {
        "object_x",
        "object_y",
        "pickup_x",
        "pickup_y",
        "dropoff_x",
        "dropoff_y",
    }
    target_state: dict[str, Any] = {}
    for key, left_value in left.target_state.items():
        right_value = right.target_state.get(key, left_value)
        if key in numeric_target_keys and isinstance(left_value, (int, float)) and isinstance(
            right_value, (int, float)
        ):
            if key in {"object_x", "object_y"}:
                target_state[key] = blend_object_position(float(left_value), float(right_value))
            else:
                target_state[key] = blend(float(left_value), float(right_value))
        elif isinstance(left_value, bool) and isinstance(right_value, bool):
            target_state[key] = right_value if ratio >= 0.5 else left_value
        else:
            target_state[key] = right_value if ratio >= 0.5 else left_value

    started_at = parse_dt(frames[0].timestamp) - timedelta(milliseconds=frames[0].offset_ms)
    current_timestamp = started_at + timedelta(milliseconds=clamped)
    return ReplayFrame(
        run_id=left.run_id,
        timestamp=to_iso(current_timestamp),
        arm_pose={
            axis: blend(float(left.arm_pose[axis]), float(right.arm_pose[axis]))
            for axis in left.arm_pose
        },
        gripper_state=right.gripper_state if ratio >= 0.5 else left.gripper_state,
        target_state=target_state,
        offset_ms=int(clamped),
        stage=right.stage if ratio >= 0.5 else left.stage,
    )


def resolve_focus_anchor_frame(
    frames: list[ReplayFrame],
    focus: str,
    *,
    success: bool,
) -> ReplayFrame | None:
    if not frames:
        return None

    def first_matching(*tokens: str) -> ReplayFrame | None:
        for frame in frames:
            if any(token in frame.stage for token in tokens):
                return frame
        return None

    if focus == "failure":
        if success:
            focus = "grasp"
        else:
            return first_matching("失败", "滑落") or frames[-1]

    if focus == "place":
        return first_matching("放置", "托盘") or frames[-1]

    if focus == "grasp":
        return first_matching("抓取") or first_matching("对准") or frames[len(frames) // 2]

    return frames[min(len(frames) - 1, len(frames) // 2)]


def estimate_duration_ms(strategy_id: str, scenario_key: str) -> int:
    base_by_strategy = {
        "heuristic-baseline": 42000,
        "stable-policy": 45000,
        "fast-motion": 34000,
    }
    scenario_adjustment = {
        "success": 0,
        "grasp_slip": -9000,
        "placement_offset": -3000,
    }
    return base_by_strategy[strategy_id] + scenario_adjustment[scenario_key]


def project_run_view(
    run: RunRecord,
    events: list[RunEvent],
    frames: list[ReplayFrame],
    now: datetime | None = None,
) -> ProjectedRunView:
    current = now or now_local()
    started_at = parse_dt(run.started_at)
    ended_at = parse_dt(run.ended_at)
    completed = run.status in {"succeeded", "failed", "cancelled"} or current >= ended_at
    elapsed_ms = run.duration_ms if completed else max(
        0, int((current - started_at).total_seconds() * 1000)
    )
    elapsed_ms = min(elapsed_ms, run.duration_ms)
    visible_events = [event for event in events if completed or event.offset_ms <= elapsed_ms]
    visible_frames = [frame for frame in frames if completed or frame.offset_ms <= elapsed_ms]
    if not visible_frames and frames:
        visible_frames = [frames[0]]
    if not visible_events and events:
        visible_events = [events[0]]

    current_stage = visible_events[-1].stage if visible_events else "等待启动"
    effective_status = run.result.final_status if completed else "running"
    projected_run = replace(run, status=effective_status)
    return ProjectedRunView(
        run_record=projected_run,
        visible_events=visible_events,
        visible_frames=visible_frames,
        progress=(elapsed_ms / run.duration_ms) if run.duration_ms else 0.0,
        current_stage=current_stage,
        completed=completed,
        elapsed_ms=elapsed_ms,
    )


def build_comparison_summary(
    left_run: RunRecord,
    right_run: RunRecord,
    left_events: list[RunEvent],
    right_events: list[RunEvent],
) -> ComparisonSummary:
    duration_diff_ms = right_run.duration_ms - left_run.duration_ms
    if left_run.result.success == right_run.result.success:
        success_diff = "两侧结果一致"
    elif left_run.result.success:
        success_diff = "左侧成功，右侧失败"
    else:
        success_diff = "右侧成功，左侧失败"

    left_failure = left_run.result.failure_reason or "无失败"
    right_failure = right_run.result.failure_reason or "无失败"
    failure_reason_diff = f"左侧：{left_failure}；右侧：{right_failure}"

    left_final_log = left_events[-1].message if left_events else "左侧无日志"
    right_final_log = right_events[-1].message if right_events else "右侧无日志"
    log_summary_diff = f"左侧结束日志：{left_final_log}；右侧结束日志：{right_final_log}"

    recommended_run_id, recommended_reason = choose_recommended_run(left_run, right_run)
    return ComparisonSummary(
        left_run_id=left_run.id,
        right_run_id=right_run.id,
        success_diff=success_diff,
        duration_diff_ms=duration_diff_ms,
        failure_reason_diff=failure_reason_diff,
        log_summary_diff=log_summary_diff,
        recommended_run_id=recommended_run_id,
        recommended_reason=recommended_reason,
    )


def is_benchmark_run(run: RunRecord) -> bool:
    return "benchmark-generated" in run.tags


def ad_hoc_run_records(data: StoreData) -> list[RunRecord]:
    return [run for run in data.run_records if not is_benchmark_run(run)]


def benchmark_batches_sorted(data: StoreData) -> list[BenchmarkBatch]:
    return sorted(data.benchmark_batches, key=lambda item: item.created_at, reverse=True)


def benchmark_runs_for_batch(data: StoreData, batch: BenchmarkBatch) -> list[RunRecord]:
    run_map = {run.id: run for run in data.run_records}
    return [run_map[run_id] for run_id in batch.run_ids if run_id in run_map]


def summarize_benchmark_batch(
    batch: BenchmarkBatch,
    suite: BenchmarkSuite,
    runs: list[RunRecord],
) -> dict[str, Any]:
    total_cases = len(runs)
    success_count = sum(1 for run in runs if run.result.success)
    success_rate = (success_count / total_cases) if total_cases else 0.0
    avg_duration_ms = (
        sum(run.duration_ms for run in runs) // total_cases if total_cases else 0
    )
    failure_counter = Counter(
        run.result.failure_reason for run in runs if run.result.failure_reason
    )
    weakest_run = min(
        runs,
        key=lambda item: (1 if item.result.success else 0, item.result.quality_score),
    ) if runs else None
    case_results = [
        {
            "run_id": run.id,
            "case_id": run.input_params.get("benchmark_case_id", ""),
            "case_name": run.input_params.get("benchmark_case_name", run.id),
            "status": "成功" if run.result.success else "失败",
            "duration_ms": run.duration_ms,
            "quality_score": run.result.quality_score,
            "summary": human_stage_summary(run),
        }
        for run in runs
    ]
    if success_rate >= 0.8:
        recommendation = "通过最小验证门槛，可作为默认演示和验证策略。"
    elif success_rate >= 0.6:
        recommendation = "部分通过，适合作为候选策略，但需要针对失败场景补强。"
    else:
        recommendation = "未通过最小验证门槛，不建议作为默认策略。"
    if weakest_run and not weakest_run.result.success:
        recommendation = (
            f"{recommendation} 当前最薄弱场景是"
            f"{weakest_run.input_params.get('benchmark_case_name', weakest_run.id)}。"
        )
    return {
        "batch_id": batch.id,
        "suite_id": suite.id,
        "suite_name": suite.name,
        "total_cases": total_cases,
        "success_count": success_count,
        "success_rate": success_rate,
        "avg_duration_ms": avg_duration_ms,
        "failure_breakdown": dict(failure_counter),
        "failure_breakdown_text": "；".join(
            f"{reason} x{count}" for reason, count in failure_counter.items()
        ) if failure_counter else "无失败案例",
        "case_results": case_results,
        "recommendation": recommendation,
        "focus_metrics": suite.focus_metrics,
    }


def choose_recommended_run(left_run: RunRecord, right_run: RunRecord) -> tuple[str, str]:
    if left_run.result.success and not right_run.result.success:
        return left_run.id, "左侧成功率更高，适合优先用于演示。"
    if right_run.result.success and not left_run.result.success:
        return right_run.id, "右侧成功率更高，适合优先用于演示。"
    if left_run.result.quality_score > right_run.result.quality_score:
        return left_run.id, "左侧质量分更高，轨迹稳定性更好。"
    if right_run.result.quality_score > left_run.result.quality_score:
        return right_run.id, "右侧质量分更高，轨迹稳定性更好。"
    if left_run.duration_ms <= right_run.duration_ms:
        return left_run.id, "两者表现接近，左侧耗时更短。"
    return right_run.id, "两者表现接近，右侧耗时更短。"


def sync_run_statuses(
    data: StoreData,
    current: datetime | None = None,
    runtime_overrides: dict[str, datetime] | None = None,
) -> bool:
    now_value = current or now_local()
    overrides = runtime_overrides or {}
    changed = False
    for index, run in enumerate(data.run_records):
        effective_now = overrides.get(run.id, now_value)
        if run.status == "running" and parse_dt(run.ended_at) <= effective_now:
            data.run_records[index] = replace(run, status=run.result.final_status)
            changed = True
    return changed


def sync_store_defaults(data: StoreData) -> bool:
    changed = False
    if not data.benchmark_suites:
        data.benchmark_suites = seed_benchmark_suites()
        changed = True
    migrated_strategies: list[StrategyVersion] = []
    for strategy in data.strategy_versions:
        desired_name = _STRATEGY_DISPLAY_NAMES.get(strategy.id)
        if desired_name and strategy.name != desired_name:
            migrated_strategies.append(replace(strategy, name=desired_name))
            changed = True
        else:
            migrated_strategies.append(strategy)
    if migrated_strategies != data.strategy_versions:
        data.strategy_versions = migrated_strategies
    if data.benchmark_batches:
        ordered = sorted(data.benchmark_batches, key=lambda item: item.created_at, reverse=True)
        if ordered != data.benchmark_batches:
            data.benchmark_batches = ordered
            changed = True
    return changed


def runs_by_strategy(
    data: StoreData, include_benchmark: bool = False
) -> dict[str, list[RunRecord]]:
    grouped: dict[str, list[RunRecord]] = {strategy.id: [] for strategy in data.strategy_versions}
    for run in data.run_records:
        if not include_benchmark and is_benchmark_run(run):
            continue
        grouped.setdefault(run.strategy_version_id, []).append(run)
    return grouped


def generate_strategy_metrics(
    data: StoreData, include_benchmark: bool = False
) -> list[dict[str, Any]]:
    grouped = runs_by_strategy(data, include_benchmark=include_benchmark)
    metrics: list[dict[str, Any]] = []
    strategy_map = {strategy.id: strategy for strategy in data.strategy_versions}
    for strategy_id, runs in grouped.items():
        if not runs:
            continue
        success_count = sum(1 for run in runs if run.result.success)
        avg_duration = sum(run.duration_ms for run in runs) // len(runs)
        metrics.append(
            {
                "id": strategy_id,
                "name": strategy_map[strategy_id].name,
                "version": strategy_map[strategy_id].version,
                "success_rate": success_count / len(runs),
                "avg_duration_ms": avg_duration,
                "notes": strategy_map[strategy_id].notes,
            }
        )
    return metrics


def latest_failure_reasons(
    data: StoreData, limit: int = 3, include_benchmark: bool = False
) -> list[str]:
    reasons: list[str] = []
    for run in data.run_records:
        if not include_benchmark and is_benchmark_run(run):
            continue
        if run.result.failure_reason:
            reasons.append(run.result.failure_reason)
        if len(reasons) >= limit:
            break
    return reasons


def iter_run_assets(
    data: StoreData, run_id: str
) -> tuple[RunRecord | None, list[RunEvent], list[ReplayFrame]]:
    run = next((item for item in data.run_records if item.id == run_id), None)
    events = sorted(
        [event for event in data.run_events if event.run_id == run_id],
        key=lambda item: item.offset_ms,
    )
    frames = sorted(
        [frame for frame in data.replay_frames if frame.run_id == run_id],
        key=lambda item: item.offset_ms,
    )
    return run, events, frames


def duration_delta_text(duration_diff_ms: int) -> str:
    if duration_diff_ms == 0:
        return "两侧耗时一致"
    direction = "右侧更慢" if duration_diff_ms > 0 else "右侧更快"
    return f"{direction} {format_duration(abs(duration_diff_ms))}"


def human_stage_summary(run: RunRecord) -> str:
    if run.result.success:
        return "成功完成抓取、转运和放置"
    return run.result.failure_reason or "运行失败"


def make_seed_reference() -> datetime:
    return datetime(2026, 4, 2, 9, 0, 0).astimezone()
