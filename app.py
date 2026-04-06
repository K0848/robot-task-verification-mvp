from __future__ import annotations

from datetime import timedelta
import html
import time
from pathlib import Path
from typing import Any

import streamlit as st

from robot_mvp.models import ReplayFrame, RunEvent
from robot_mvp.renderer import bundle_available, render_threejs_scene
from robot_mvp.simulator import (
    FOCUS_DISPLAY_LABELS,
    PACE_DISPLAY_LABELS,
    PRESET_LABELS,
    ad_hoc_run_records,
    benchmark_batches_sorted,
    benchmark_runs_for_batch,
    build_comparison_summary,
    build_renderer_payload,
    compute_display_elapsed_ms,
    create_preview_bundle,
    duration_delta_text,
    extract_dynamic_profile,
    format_duration,
    generate_strategy_metrics,
    human_stage_summary,
    interpolate_replay_frame,
    iter_run_assets,
    latest_failure_reasons,
    now_local,
    parse_dt,
    resolve_focus_anchor_frame,
    resolve_preset,
    project_run_view,
    summarize_benchmark_batch,
    sync_run_statuses,
    to_iso,
)
from robot_mvp.storage import JsonStore

ROOT = Path(__file__).resolve().parent
STORE = JsonStore(ROOT / "data" / "store.json")
PAGES = ["总览", "任务工作台", "版本对比", "基准评测"]
ROLE_HINTS = {
    "算法工程师": [
        "关注策略版本的成功率、关键日志和失败原因。",
        "重点看任务详情页和版本对比页，快速判断哪版策略更稳。",
    ],
    "测试/实施": [
        "关注运行状态、回放和失败复现路径。",
        "重点看任务详情页的时间线和回放页的帧级回放。",
    ],
    "产品经理": [
        "关注任务链路是否清晰、结果是否可解释、演示是否顺畅。",
        "重点看总览页和任务详情页的结构化报告。",
    ],
}
STATUS_STYLE = {
    "running": ("进行中", "#ffb84d", "#3b2a08"),
    "succeeded": ("成功", "#42d392", "#10291f"),
    "failed": ("失败", "#ff7a90", "#321118"),
    "cancelled": ("取消", "#9aa6c1", "#1f2636"),
    "queued": ("排队中", "#7bc7ff", "#0c2335"),
}


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp { background: #0a0f1a; color: #e0e7ff; }
        .main, .block-container { background: transparent; }
        .block-container { padding-top: 2.4rem; padding-bottom: 2rem; }
        [data-testid="stSidebar"] { background: rgba(8, 13, 24, 0.96); }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span {
            color: #d9e3f0;
        }

        .hero-card,.panel-card,.run-card,.scene-card,.metric-box,.compare-banner,.event-row {
            border: 1px solid rgba(148, 163, 184, 0.15);
        }
        .hero-card,.panel-card,.run-card,.scene-card,.metric-box {
            background: rgba(15, 23, 42, 0.92);
            border-radius: 20px;
            padding: 1.1rem 1.2rem;
            margin-bottom: 0.9rem;
            box-shadow: 0 18px 48px rgba(2, 6, 23, 0.28);
        }
        .hero-card {
            padding: 1.55rem 1.6rem 1.35rem 1.6rem;
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.94), rgba(8, 18, 34, 0.96));
            overflow: visible;
        }
        .hero-kicker,.mini-label {
            color: #94a3b8;
            font-size: 0.82rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            line-height: 1.45;
            display: block;
        }
        .hero-title {
            font-size: 2rem;
            font-weight: 700;
            color: #f8fafc;
            margin: 0.35rem 0;
            line-height: 1.28;
            overflow: visible;
            word-break: break-word;
        }
        .hero-body,.run-copy,.event-copy {
            color: #94a3b8;
            line-height: 1.6;
            overflow: visible;
        }
        .run-title,.event-stage {
            color: #e2e8f0;
            font-weight: 700;
        }
        .status-pill {
            display: inline-block;
            padding: 0.24rem 0.65rem;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 700;
            margin-bottom: 0.7rem;
        }
        .event-row {
            padding: 0.72rem 0.85rem;
            border-left: 3px solid rgba(255,255,255,0.16);
            background: rgba(255,255,255,0.03);
            border-radius: 14px;
            margin-bottom: 0.55rem;
        }
        .metric-strip {
            display: grid;
            grid-template-columns: repeat(4, minmax(0,1fr));
            gap: 0.8rem;
            margin-bottom: 1rem;
        }
        .metric-value {
            color: #f8fafc;
            font-size: 1.45rem;
            font-weight: 700;
            margin-top: 0.25rem;
        }
        .compare-banner {
            padding: 0.95rem 1rem;
            border-radius: 18px;
            background: rgba(0, 229, 195, 0.08);
            color: #e0e7ff;
            margin-bottom: 1rem;
        }

        .overview-title {
            font-size: 2.15rem;
            line-height: 1.24;
            font-weight: 800;
            color: #f8fafc;
            margin: 0 0 0.3rem 0;
        }
        .overview-subtitle {
            color: #94a3b8;
            margin-bottom: 0.25rem;
        }
        .panel-heading {
            font-size: 1.08rem;
            font-weight: 700;
            color: #00e5c3;
            margin-bottom: 0.25rem;
        }
        .panel-helper {
            color: #94a3b8;
            font-size: 0.92rem;
            margin-bottom: 0.95rem;
        }

        .kpi-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(175px, 1fr));
            gap: 1rem;
            margin: 1rem 0 1.7rem 0;
        }
        .kpi-card {
            background: rgba(15, 23, 42, 0.92);
            border: 1px solid rgba(0, 229, 195, 0.25);
            border-radius: 18px;
            padding: 1.2rem 1.35rem;
            min-height: 118px;
            box-shadow: 0 18px 48px rgba(2, 6, 23, 0.28);
        }
        .kpi-value {
            font-size: 2.25rem;
            font-weight: 700;
            color: #00e5c3;
            line-height: 1;
        }
        .kpi-label {
            font-size: 0.82rem;
            color: #94a3b8;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.7rem;
        }
        .kpi-delta {
            font-size: 0.9rem;
            font-weight: 600;
            margin-top: 0.55rem;
        }
        .trend-up { color: #22c55e; }
        .trend-down { color: #f87171; }
        .trend-flat { color: #94a3b8; }

        .health-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0,1fr));
            gap: 0.85rem;
        }
        .health-card {
            background: rgba(8, 15, 26, 0.72);
            border: 1px solid rgba(0, 229, 195, 0.12);
            border-radius: 16px;
            padding: 1rem;
            min-height: 150px;
        }
        .health-title {
            color: #e2e8f0;
            font-size: 1rem;
            font-weight: 700;
            margin-bottom: 0.35rem;
        }
        .health-value {
            color: #00e5c3;
            font-size: 1.8rem;
            font-weight: 700;
            line-height: 1;
            margin: 0.35rem 0 0.45rem 0;
        }
        .health-meta {
            color: #94a3b8;
            font-size: 0.88rem;
            line-height: 1.5;
        }

        .stDataFrame {
            border-radius: 16px;
            border: 1px solid rgba(148, 163, 184, 0.15);
            overflow: hidden;
        }

        @media (max-width: 1100px) {
            .health-grid { grid-template-columns: 1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_badge(status: str) -> str:
    label, bg_color, fg_color = STATUS_STYLE.get(status, (status, "#9aa6c1", "#1f2636"))
    return f"<span class='status-pill' style='background:{bg_color};color:{fg_color};'>{label}</span>"


def format_timestamp(value: str) -> str:
    return parse_dt(value).strftime("%m-%d %H:%M:%S")


def ensure_state(run_ids: list[str], batch_ids: list[str]) -> None:
    if "page" not in st.session_state:
        st.session_state.page = PAGES[0]
    if "role" not in st.session_state:
        st.session_state.role = "产品经理"
    if "selected_run_id" not in st.session_state:
        st.session_state.selected_run_id = run_ids[0] if run_ids else None
    elif st.session_state.selected_run_id not in run_ids:
        st.session_state.selected_run_id = run_ids[0] if run_ids else None
    if "compare_left_id" not in st.session_state:
        st.session_state.compare_left_id = run_ids[0] if run_ids else None
    elif st.session_state.compare_left_id not in run_ids:
        st.session_state.compare_left_id = run_ids[0] if run_ids else None
    if "compare_right_id" not in st.session_state:
        st.session_state.compare_right_id = run_ids[1] if len(run_ids) > 1 else (run_ids[0] if run_ids else None)
    elif st.session_state.compare_right_id not in run_ids:
        st.session_state.compare_right_id = run_ids[1] if len(run_ids) > 1 else (run_ids[0] if run_ids else None)
    if "selected_benchmark_batch_id" not in st.session_state:
        st.session_state.selected_benchmark_batch_id = batch_ids[0] if batch_ids else None
    if "renderer_mode" not in st.session_state:
        st.session_state.renderer_mode = "threejs"
    if "latest_overview_run_id" not in st.session_state:
        st.session_state.latest_overview_run_id = run_ids[0] if run_ids else None
    elif st.session_state.latest_overview_run_id not in run_ids:
        st.session_state.latest_overview_run_id = run_ids[0] if run_ids else None
    if "launch_preview_signature" not in st.session_state:
        st.session_state.launch_preview_signature = None
    if "launch_preview_anchor" not in st.session_state:
        st.session_state.launch_preview_anchor = time.perf_counter()
    if "launch_preview_reference" not in st.session_state:
        st.session_state.launch_preview_reference = to_iso(now_local())
    if "launch_preview_resolved_scenario" not in st.session_state:
        st.session_state.launch_preview_resolved_scenario = "success"
    if "detail_paused_run_id" not in st.session_state:
        st.session_state.detail_paused_run_id = None
    elif st.session_state.detail_paused_run_id not in run_ids:
        st.session_state.detail_paused_run_id = None
    if "detail_paused_elapsed_ms" not in st.session_state:
        st.session_state.detail_paused_elapsed_ms = 0
    if "runtime_control_run_id" not in st.session_state:
        st.session_state.runtime_control_run_id = st.session_state.detail_paused_run_id
    elif st.session_state.runtime_control_run_id not in run_ids:
        st.session_state.runtime_control_run_id = None
    if "runtime_control_paused" not in st.session_state:
        st.session_state.runtime_control_paused = bool(st.session_state.runtime_control_run_id)
    if "runtime_control_elapsed_ms" not in st.session_state:
        st.session_state.runtime_control_elapsed_ms = int(
            st.session_state.get("detail_paused_elapsed_ms", 0)
        )
    if "runtime_control_anchor_time" not in st.session_state:
        st.session_state.runtime_control_anchor_time = (
            to_iso(now_local()) if st.session_state.runtime_control_run_id else None
        )
    elif not st.session_state.runtime_control_run_id:
        st.session_state.runtime_control_anchor_time = None


def clear_runtime_control() -> None:
    st.session_state.runtime_control_run_id = None
    st.session_state.runtime_control_paused = False
    st.session_state.runtime_control_elapsed_ms = 0
    st.session_state.runtime_control_anchor_time = None
    st.session_state.detail_paused_run_id = None
    st.session_state.detail_paused_elapsed_ms = 0


def get_runtime_control_state(run_id: str | None = None) -> dict[str, Any] | None:
    current_run_id = st.session_state.get("runtime_control_run_id")
    if not current_run_id:
        return None
    if run_id is not None and current_run_id != run_id:
        return None
    return {
        "run_id": current_run_id,
        "paused": bool(st.session_state.get("runtime_control_paused", False)),
        "elapsed_ms": int(st.session_state.get("runtime_control_elapsed_ms", 0)),
        "anchor_time": st.session_state.get("runtime_control_anchor_time"),
    }


def is_runtime_paused(run_id: str) -> bool:
    control = get_runtime_control_state(run_id)
    return bool(control and control["paused"])


def compute_runtime_elapsed_ms(run, current: Any | None = None) -> int:
    now_value = current or now_local()
    control = get_runtime_control_state(run.id)
    if control is None:
        if run.status in {"succeeded", "failed", "cancelled"}:
            return run.duration_ms
        started_at = parse_dt(run.started_at)
        return min(
            max(int((now_value - started_at).total_seconds() * 1000), 0),
            run.duration_ms,
        )

    anchor_raw = control["anchor_time"]
    anchor_time = parse_dt(anchor_raw) if anchor_raw else now_value
    base_elapsed = min(max(int(control["elapsed_ms"]), 0), run.duration_ms)
    if control["paused"]:
        return base_elapsed
    resumed_delta = max(int((now_value - anchor_time).total_seconds() * 1000), 0)
    return min(base_elapsed + resumed_delta, run.duration_ms)


def build_runtime_sync_overrides(data, current: Any | None = None) -> dict[str, Any]:
    now_value = current or now_local()
    control = get_runtime_control_state()
    if control is None:
        return {}
    run = next((item for item in data.run_records if item.id == control["run_id"]), None)
    if run is None:
        clear_runtime_control()
        return {}
    effective_elapsed_ms = compute_runtime_elapsed_ms(run, now_value)
    return {
        run.id: parse_dt(run.started_at) + timedelta(milliseconds=effective_elapsed_ms)
    }


def resolve_runtime_projection(run, events: list[RunEvent], frames: list[ReplayFrame]) -> dict[str, Any]:
    effective_now = now_local()
    effective_elapsed_ms = compute_runtime_elapsed_ms(run, effective_now)
    projection_now = parse_dt(run.started_at) + timedelta(milliseconds=effective_elapsed_ms)
    projected = project_run_view(run, events, frames, now=projection_now)
    dynamic_profile = extract_dynamic_profile(run)
    display_elapsed_ms = compute_display_elapsed_ms(
        projected.elapsed_ms,
        run.duration_ms,
        dynamic_profile,
    )
    display_frame = interpolate_replay_frame(frames, display_elapsed_ms)
    scene_meta = scene_meta_for_run(run, frames, display_frame, dynamic_profile)
    paused = is_runtime_paused(run.id) and not projected.completed
    animation_mode = "static" if paused or projected.completed else "live"
    if projected.completed and get_runtime_control_state(run.id) is not None:
        clear_runtime_control()
        paused = False
    return {
        "projected": projected,
        "dynamic_profile": dynamic_profile,
        "display_elapsed_ms": display_elapsed_ms,
        "display_frame": display_frame,
        "scene_meta": scene_meta,
        "paused": paused,
        "animation_mode": animation_mode,
    }


def toggle_runtime_pause(run) -> None:
    current = now_local()
    effective_elapsed_ms = compute_runtime_elapsed_ms(run, current)
    if is_runtime_paused(run.id):
        st.session_state.runtime_control_run_id = run.id
        st.session_state.runtime_control_paused = False
        st.session_state.runtime_control_elapsed_ms = effective_elapsed_ms
        st.session_state.runtime_control_anchor_time = to_iso(current)
    else:
        st.session_state.runtime_control_run_id = run.id
        st.session_state.runtime_control_paused = True
        st.session_state.runtime_control_elapsed_ms = effective_elapsed_ms
        st.session_state.runtime_control_anchor_time = to_iso(current)
    st.session_state.detail_paused_run_id = st.session_state.runtime_control_run_id
    st.session_state.detail_paused_elapsed_ms = st.session_state.runtime_control_elapsed_ms


def effective_renderer_mode() -> str:
    if st.session_state.renderer_mode == "threejs" and bundle_available():
        return "threejs"
    return "svg"


def sync_launch_preview_state(
    template_id: str, strategy_id: str, preset_key: str, operator_note: str
) -> None:
    signature = (template_id, strategy_id, preset_key, operator_note.strip())
    if st.session_state.launch_preview_signature == signature:
        return
    reference = now_local()
    st.session_state.launch_preview_signature = signature
    st.session_state.launch_preview_anchor = time.perf_counter()
    st.session_state.launch_preview_reference = to_iso(reference)
    st.session_state.launch_preview_resolved_scenario = resolve_preset(
        strategy_id, preset_key, reference
    )


def scene_meta_for_run(
    run,
    frames: list[ReplayFrame],
    display_frame: ReplayFrame | None,
    dynamic_profile: dict[str, Any],
) -> dict[str, Any]:
    focus = dynamic_profile["focus"]
    anchor = resolve_focus_anchor_frame(frames, focus, success=run.result.success)
    highlight_target = {
        "grasp": "gripper",
        "place": "object",
        "failure": "object",
    }.get(focus, None)
    subtitle_parts = [
        PACE_DISPLAY_LABELS[dynamic_profile["pace"]],
        FOCUS_DISPLAY_LABELS[focus],
        f"场景：{run.result.scenario_label}",
    ]
    if anchor is not None and focus != "overview":
        subtitle_parts.append(f"聚焦阶段：{anchor.stage}")
    if dynamic_profile["matched_keywords"]:
        subtitle_parts.append(f"备注指令：{' / '.join(dynamic_profile['matched_keywords'])}")
    failure_style = focus == "failure" and not run.result.success
    return {
        "subtitle": " · ".join(subtitle_parts),
        "focus_stage": anchor.stage if anchor is not None else (display_frame.stage if display_frame else ""),
        "highlight_target": highlight_target,
        "failure_style": failure_style,
    }


def render_launch_preview_fragment(
    data,
    *,
    heading: str = "动作预览",
    height: int = 420,
    event_limit: int = 4,
) -> None:
    template_id = st.session_state.get("launch-task-template")
    strategy_id = st.session_state.get("launch-strategy")
    preset_key = st.session_state.get("launch-preset", "auto")
    operator_note = st.session_state.get("launch-operator-note", "")
    if not template_id or not strategy_id:
        st.info("选择任务模板和策略版本后显示动态预览。")
        return

    task = next(item for item in data.task_templates if item.id == template_id)
    strategy = next(item for item in data.strategy_versions if item.id == strategy_id)
    reference = parse_dt(st.session_state.launch_preview_reference)
    resolved_scenario = st.session_state.launch_preview_resolved_scenario
    run, events, frames = create_preview_bundle(
        task_template=task,
        strategy=strategy,
        preset_key=preset_key,
        operator_note=operator_note,
        reference_time=reference,
        resolved_scenario=resolved_scenario,
    )
    dynamic_profile = extract_dynamic_profile(run)
    raw_elapsed_ms = 0
    display_elapsed_ms = 0
    display_frame = frames[0] if frames else None
    visible_events = events[:1]
    if not visible_events and events:
        visible_events = [events[0]]
    scene_meta = scene_meta_for_run(run, frames, display_frame, dynamic_profile)
    payload = build_renderer_payload(
        run,
        events,
        frames,
        "preview",
        dynamic_profile=dynamic_profile,
        animation_mode="loop",
        initial_elapsed_ms=raw_elapsed_ms,
        progress=0.0,
        current_stage=display_frame.stage if display_frame is not None else run.result.scenario_label,
        title="实时动态预览",
    )

    st.markdown(f"#### {heading}")
    render_motion_scene(
        payload,
        display_frame,
        heading,
        scene_meta=scene_meta,
        height=height,
    )
    progress_text = display_frame.stage if display_frame is not None else run.result.scenario_label
    st.progress(0.0, text=f"{progress_text} | {run.result.scenario_label}")
    st.caption(f"策略：{strategy.name} {strategy.version}")
    render_event_timeline(visible_events, limit=event_limit)


def render_command_center_header(
    *,
    kicker: str,
    title: str = "RoboForge 指挥中心",
    body: str,
) -> None:
    st.markdown(
        f"""
        <div class="hero-card">
            <div class="hero-kicker">{html.escape(kicker)}</div>
            <div class="hero-title">{html.escape(title)}</div>
            <div class="hero-body">{html.escape(body)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def format_run_selector_label(data, run) -> str:
    task_map = {item.id: item for item in data.task_templates}
    strategy_map = {item.id: item for item in data.strategy_versions}
    task = task_map.get(run.task_template_id)
    strategy = strategy_map.get(run.strategy_version_id)
    scenario_label = getattr(run.result, "scenario_label", "")
    if task is None or strategy is None or not scenario_label:
        return f"{format_timestamp(run.started_at)} | {run.id}"
    return (
        f"{format_timestamp(run.started_at)} | "
        f"{task.name} | {strategy.name} {strategy.version} | {scenario_label}"
    )


def build_run_selector_options(data) -> dict[str, str]:
    options: dict[str, str] = {}
    for run in data.run_records:
        base_label = format_run_selector_label(data, run)
        label = base_label
        suffix = 2
        while label in options:
            label = f"{base_label} ({suffix})"
            suffix += 1
        options[label] = run.id
    return options


def render_hero() -> None:
    st.markdown(
        """
        <div class="hero-card">
            <div class="hero-kicker">Robotics Product MVP</div>
            <div class="hero-title">仿真机械臂任务验证平台</div>
            <div class="hero-body">
                用一个轻量 Web 仪表盘，把抓取任务的启动、实时监控、结果沉淀、回放和版本对比放进同一条验证链路。
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_strip(data) -> None:
    visible_runs = ad_hoc_run_records(data)
    total_runs = len(visible_runs)
    success_count = sum(1 for run in visible_runs if run.result.success)
    success_rate = f"{(success_count / total_runs * 100):.0f}%" if total_runs else "0%"
    active_runs = sum(1 for run in visible_runs if run.status == "running")
    failure_coverage = len({run.result.failure_reason for run in visible_runs if run.result.failure_reason})
    st.markdown(
        f"""
        <div class="metric-strip">
            <div class="metric-box"><div class="mini-label">总运行记录</div><div class="metric-value">{total_runs}</div></div>
            <div class="metric-box"><div class="mini-label">整体成功率</div><div class="metric-value">{success_rate}</div></div>
            <div class="metric-box"><div class="mini-label">进行中任务</div><div class="metric-value">{active_runs}</div></div>
            <div class="metric-box"><div class="mini-label">失败类型覆盖</div><div class="metric-value">{failure_coverage}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_role_brief(role: str) -> None:
    bullets = "".join(f"<li>{html.escape(item)}</li>" for item in ROLE_HINTS[role])
    st.markdown(
        f"""
        <div class="mini-label" style="margin-top:0.85rem;">当前角色关注点</div>
        <div style="color:#eef2ff;font-weight:700;margin:0.25rem 0 0.45rem 0;">{html.escape(role)}</div>
        <ul style="color:#94a3b8;line-height:1.7;margin:0 0 0 1.05rem;padding-left:0.1rem;">{bullets}</ul>
        """,
        unsafe_allow_html=True,
    )


def render_event_timeline(events: list[RunEvent], limit: int | None = None) -> None:
    subset = events if limit is None else events[-limit:]
    for event in subset:
        color = {"success": "#42d392", "warning": "#ffb84d", "error": "#ff7a90"}.get(event.level, "#7bc7ff")
        st.markdown(
            f"""
            <div class="event-row" style="border-left-color:{color};">
                <div class="event-stage">{html.escape(event.stage)} <span style="color:#93a1bd;font-weight:400;">{format_timestamp(event.timestamp)}</span></div>
                <div class="event-copy">{html.escape(event.message)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def build_svg_scene_html(
    frame: ReplayFrame | None,
    title: str = "简化动作视图",
    scene_meta: dict[str, Any] | None = None,
) -> str:
    if frame is None:
        return '<div class="scene-card"><div class="run-copy">暂无回放帧。</div></div>'
    scene_meta = scene_meta or {}
    arm_x = frame.arm_pose["x"] * 3
    arm_y = frame.arm_pose["y"] * 2
    elbow_x = int((arm_x + 45) / 2)
    elbow_y = max(int((arm_y + 188) / 2) - 34, 36)
    obj_x = frame.target_state["object_x"] * 3
    obj_y = frame.target_state["object_y"] * 2
    pickup_x = frame.target_state["pickup_x"] * 3
    pickup_y = frame.target_state["pickup_y"] * 2
    dropoff_x = frame.target_state["dropoff_x"] * 3
    dropoff_y = frame.target_state["dropoff_y"] * 2
    focus_stage = scene_meta.get("focus_stage", "")
    highlight_target = scene_meta.get("highlight_target")
    failure_style = bool(scene_meta.get("failure_style"))
    subtitle = scene_meta.get("subtitle")
    object_fill = "#42d392" if frame.target_state["placed"] else "#ffb84d"
    gripper_fill = "#7bc7ff" if frame.gripper_state == "open" else "#ff9f43"
    object_halo = (
        f'<circle cx="{obj_x}" cy="{obj_y}" r="13" fill="rgba(255, 207, 153, 0.12)" stroke="#ffcf99" stroke-width="1.5" />'
        if highlight_target == "object"
        else ""
    )
    gripper_stroke = "#ffcf99" if highlight_target == "gripper" else "transparent"
    panel_fill = "#1b1f2b" if failure_style else "#141b29"
    panel_stroke = "rgba(255, 122, 144, 0.35)" if failure_style else "rgba(255,255,255,0.12)"
    title_html = html.escape(frame.stage)
    if focus_stage and focus_stage != frame.stage:
        title_html = f"{title_html} <span style='color:#ffcf99;font-size:0.9rem;'>聚焦：{html.escape(focus_stage)}</span>"
    subtitle_html = (
        f"<div class='run-copy' style='margin:-0.15rem 0 0.65rem 0;'>{html.escape(subtitle)}</div>"
        if subtitle
        else ""
    )
    return f"""
    <div class="scene-card">
        <div class="mini-label">{html.escape(title)}</div>
        <div style="color:#eef2ff;font-size:1.15rem;font-weight:700;margin:0.25rem 0 0.4rem 0;">{title_html}</div>
        {subtitle_html}
        <svg viewBox="0 0 320 220" width="100%" height="240">
            <rect x="10" y="12" width="300" height="196" rx="18" fill="{panel_fill}" stroke="{panel_stroke}" />
            <rect x="26" y="154" width="74" height="20" rx="8" fill="#27324a" />
            <rect x="214" y="128" width="68" height="44" rx="12" fill="#243349" stroke="#ffcf99" stroke-width="1.5" stroke-dasharray="4 4" />
            <text x="218" y="123" fill="#93a1bd" font-size="10">目标托盘 {html.escape(frame.target_state['target_slot'])}</text>
            <circle cx="{pickup_x}" cy="{pickup_y}" r="5" fill="#7bc7ff" opacity="0.75" />
            <circle cx="{dropoff_x}" cy="{dropoff_y}" r="5" fill="#ffcf99" opacity="0.85" />
            <line x1="46" y1="164" x2="{elbow_x}" y2="{elbow_y}" stroke="#a9b4ce" stroke-width="8" stroke-linecap="round" />
            <line x1="{elbow_x}" y1="{elbow_y}" x2="{arm_x}" y2="{arm_y}" stroke="#d8deec" stroke-width="7" stroke-linecap="round" />
            <circle cx="{elbow_x}" cy="{elbow_y}" r="7" fill="#7bc7ff" />
            <rect x="{arm_x - 10}" y="{arm_y - 7}" width="20" height="14" rx="5" fill="{gripper_fill}" stroke="{gripper_stroke}" stroke-width="2" />
            {object_halo}
            <circle cx="{obj_x}" cy="{obj_y}" r="7" fill="{object_fill}" />
        </svg>
        <div class="run-copy">目标物：{html.escape(frame.target_state['object_label'])} | 抓手：{html.escape(frame.gripper_state)} | 放置完成：{"是" if frame.target_state["placed"] else "否"}</div>
    </div>
    """


def render_svg_scene(
    frame: ReplayFrame | None,
    title: str = "简化动作视图",
    scene_meta: dict[str, Any] | None = None,
) -> None:
    st.markdown(build_svg_scene_html(frame, title, scene_meta), unsafe_allow_html=True)


def render_motion_scene(
    payload: dict[str, Any],
    fallback_frame: ReplayFrame | None,
    title: str,
    *,
    scene_meta: dict[str, Any] | None = None,
    height: int = 420,
) -> None:
    if effective_renderer_mode() == "threejs":
        render_threejs_scene(
            payload,
            build_svg_scene_html(fallback_frame, title, scene_meta),
            height=height,
        )
        return
    render_svg_scene(fallback_frame, title, scene_meta)


def render_strategy_board(data) -> None:
    st.subheader("策略版本看板")
    metrics = generate_strategy_metrics(data)
    cols = st.columns(len(metrics))
    for column, item in zip(cols, metrics):
        with column:
            st.markdown(
                f"""
                <div class="panel-card">
                    <div class="mini-label">{html.escape(item['name'])}</div>
                    <div style="color:#eef2ff;font-size:1.2rem;font-weight:700;">{html.escape(item['version'])}</div>
                    <div style="color:#ffcf99;margin:0.35rem 0 0.4rem 0;">成功率 {(item['success_rate'] * 100):.0f}%</div>
                    <div class="run-copy">平均耗时 {format_duration(item['avg_duration_ms'])}</div>
                    <div class="run-copy" style="margin-top:0.4rem;">{html.escape(item['notes'])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_launch_form(
    data,
    *,
    compact: bool = False,
    show_preview: bool = True,
    show_failure_warnings: bool = True,
) -> None:
    if not compact:
        st.subheader("启动任务")
    task_map = {item.id: item for item in data.task_templates}
    strategy_map = {item.id: item for item in data.strategy_versions}
    template_ids = [item.id for item in data.task_templates]
    strategy_ids = [item.id for item in data.strategy_versions]
    preset_keys = list(PRESET_LABELS.keys())

    def render_controls() -> None:
        if compact:
            select_left, select_right = st.columns(2)
            with select_left:
                template_id = st.selectbox(
                    "任务模板",
                    template_ids,
                    format_func=lambda item_id: task_map[item_id].name,
                    key="launch-task-template",
                )
            with select_right:
                strategy_id = st.selectbox(
                    "策略版本",
                    strategy_ids,
                    format_func=lambda item_id: f"{strategy_map[item_id].name} {strategy_map[item_id].version}",
                    key="launch-strategy",
                )
            preset_col, note_col = st.columns([0.78, 1.22])
            with preset_col:
                preset_key = st.selectbox(
                    "演示预设",
                    preset_keys,
                    format_func=lambda item_key: PRESET_LABELS[item_key],
                    key="launch-preset",
                )
            with note_col:
                operator_note = st.text_input(
                    "备注",
                    placeholder="例如：快节奏 / 强调失败复盘",
                    key="launch-operator-note",
                )
        else:
            col1, col2 = st.columns(2)
            with col1:
                template_id = st.selectbox(
                    "任务模板",
                    template_ids,
                    format_func=lambda item_id: task_map[item_id].name,
                    key="launch-task-template",
                )
            with col2:
                strategy_id = st.selectbox(
                    "策略版本",
                    strategy_ids,
                    format_func=lambda item_id: f"{strategy_map[item_id].name} {strategy_map[item_id].version}",
                    key="launch-strategy",
                )
            col3, col4 = st.columns(2)
            with col3:
                preset_key = st.selectbox(
                    "演示预设",
                    preset_keys,
                    format_func=lambda item_key: PRESET_LABELS[item_key],
                    key="launch-preset",
                )
            with col4:
                operator_note = st.text_input(
                    "备注",
                    placeholder="例如：面试演示用 / 强调失败复盘 / 快节奏 / 强调抓取",
                    key="launch-operator-note",
                )

        sync_launch_preview_state(template_id, strategy_id, preset_key, operator_note)
        reference = parse_dt(st.session_state.launch_preview_reference)
        preview_run, _, _ = create_preview_bundle(
            task_template=task_map[template_id],
            strategy=strategy_map[strategy_id],
            preset_key=preset_key,
            operator_note=operator_note,
            reference_time=reference,
            resolved_scenario=st.session_state.launch_preview_resolved_scenario,
        )
        dynamic_profile = extract_dynamic_profile(preview_run)
        st.caption(
            f"即将运行：{preview_run.result.scenario_label} · "
            f"{PACE_DISPLAY_LABELS[dynamic_profile['pace']]} · "
            f"{FOCUS_DISPLAY_LABELS[dynamic_profile['focus']]}"
        )
        if dynamic_profile["matched_keywords"]:
            st.caption(f"已识别备注指令：{' / '.join(dynamic_profile['matched_keywords'])}")
        if st.button("开始一次新验证", key="launch-submit", use_container_width=True):
            run_id = STORE.create_live_run(
                task_template_id=template_id,
                strategy_version_id=strategy_id,
                preset_key=preset_key,
                operator_note=operator_note,
                resolved_scenario=st.session_state.launch_preview_resolved_scenario,
                dynamic_profile=dynamic_profile,
            )
            clear_runtime_control()
            st.session_state.selected_run_id = run_id
            st.session_state.compare_left_id = run_id
            st.session_state.latest_overview_run_id = run_id
            st.session_state.page = "任务工作台"
            st.rerun()

    if compact:
        render_controls()
        if show_preview:
            st.markdown("<div style='height:0.35rem;'></div>", unsafe_allow_html=True)
            render_launch_preview_fragment(
                data,
                heading="实时动作预览",
                height=360,
                event_limit=3,
            )
    else:
        if show_preview:
            control_col, preview_col = st.columns([0.92, 1.08])
            with control_col:
                render_controls()
            with preview_col:
                render_launch_preview_fragment(data)
        else:
            render_controls()
    if show_failure_warnings:
        reasons = latest_failure_reasons(data)
        if reasons:
            st.markdown("<div style='margin-top: 0.5rem; margin-bottom: 0.5rem; font-weight: 600; color: #a1a1aa;'>⚠️ 历史执行中的常见失败原因 (供修复参考)</div>", unsafe_allow_html=True)
            for reason in reasons:
                st.warning(reason)
def render_run_grid(data) -> None:
    st.markdown(
        """
        <div class="panel-heading" style="margin-top:0.25rem;">最近验证任务</div>
        <div class="panel-helper">勾选 2 个任务进行对比，或点击查看详情和回放。</div>
        """,
        unsafe_allow_html=True,
    )
    
    if "compare_basket" not in st.session_state:
        st.session_state.compare_basket = set()

    task_map = {item.id: item for item in data.task_templates}
    strategy_map = {item.id: item for item in data.strategy_versions}
    recent_runs = ad_hoc_run_records(data)[:8]
    rows = [recent_runs[index : index + 2] for index in range(0, len(recent_runs), 2)]
    
    basket = st.session_state.compare_basket
    valid_ids = {run.id for run in recent_runs}
    basket.intersection_update(valid_ids)
    
    if len(basket) == 2:
        compare_col, _ = st.columns([0.3, 0.7])
        if compare_col.button("⚖️ 拿选中的去对比", use_container_width=True, type="primary"):
            left_id, right_id = list(basket)
            st.session_state.compare_left_id = left_id
            st.session_state.compare_right_id = right_id
            st.session_state.page = "版本对比"
            st.rerun()
            
    for row_index, row in enumerate(rows):
        columns = st.columns(len(row))
        for column, run in zip(columns, row):
            task_name = task_map[run.task_template_id].name if run.task_template_id in task_map else run.task_template_id
            strategy = strategy_map[run.strategy_version_id] if run.strategy_version_id in strategy_map else None
            strategy_name = f"{strategy.name} {strategy.version}" if strategy else run.strategy_version_id
            with column:
                st.markdown(
                    f"""
                    <div class="run-card">
                        {status_badge(run.status)}
                        <div class="run-title">{html.escape(task_name)}</div>
                        <div class="run-copy">{html.escape(strategy_name)}</div>
                        <div class="run-copy" style="margin-top:0.45rem;">开始于 {format_timestamp(run.started_at)}</div>
                        <div class="run-copy">耗时 {format_duration(run.duration_ms)}</div>
                        <div class="run-copy">结论：{html.escape(human_stage_summary(run))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                action_cols = st.columns([0.2, 0.4, 0.4])
                
                is_checked = run.id in basket
                def toggle_basket(run_id=run.id):
                    if run_id in st.session_state.compare_basket:
                        st.session_state.compare_basket.remove(run_id)
                    else:
                        st.session_state.compare_basket.add(run_id)

                action_cols[0].checkbox("对比", value=is_checked, key=f"cmp-check-{run.id}", on_change=toggle_basket, label_visibility="collapsed")
                
                if action_cols[1].button("看详情", key=f"detail-{row_index}-{run.id}", use_container_width=True):
                    st.session_state.selected_run_id = run.id
                    st.session_state.page = "任务工作台"
                    st.rerun()
                if action_cols[2].button("回放", key=f"replay-{row_index}-{run.id}", use_container_width=True):
                    st.session_state.selected_run_id = run.id
                    st.session_state.page = "任务工作台"
                    st.rerun()


def render_kpi_bar(data) -> None:
    visible_runs = ad_hoc_run_records(data)
    total = len(visible_runs)
    success_rate = round(
        sum(1 for run in visible_runs if run.result.success) / total * 100
    ) if total else 0
    active = sum(1 for run in visible_runs if run.status == "running")
    avg_duration_ms = sum(run.duration_ms for run in visible_runs if run.duration_ms) // max(total, 1)
    recent_runs = visible_runs[:7]
    previous_runs = visible_runs[7:14]
    recent_failures = len(
        {run.result.failure_reason for run in recent_runs if run.result.failure_reason}
    )

    if previous_runs:
        recent_success_rate = round(
            sum(1 for run in recent_runs if run.result.success) / max(len(recent_runs), 1) * 100
        )
        previous_success_rate = round(
            sum(1 for run in previous_runs if run.result.success) / len(previous_runs) * 100
        )
        delta = recent_success_rate - previous_success_rate
        if delta > 0:
            delta_class = "trend-up"
            delta_text = f"↑{delta}% vs 更早样本"
        elif delta < 0:
            delta_class = "trend-down"
            delta_text = f"↓{abs(delta)}% vs 更早样本"
        else:
            delta_class = "trend-flat"
            delta_text = "→ 与更早样本持平"
    else:
        delta_class = "trend-flat"
        delta_text = "样本不足，暂不比较"

    st.markdown(
        f"""
        <div class="kpi-container">
            <div class="kpi-card">
                <div class="kpi-label">总验证任务</div>
                <div class="kpi-value">{total}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">整体成功率</div>
                <div class="kpi-value">{success_rate}%</div>
                <div class="kpi-delta {delta_class}">{delta_text}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">进行中</div>
                <div class="kpi-value">{active}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">最近7次失败类型</div>
                <div class="kpi-value">{recent_failures}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">平均耗时</div>
                <div class="kpi-value">{avg_duration_ms // 1000}s</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_launch_card_compact(data) -> None:
    st.markdown(
        """
        <div class="panel-heading">快速启动一次验证</div>
        <div class="panel-helper">保留现有任务生成逻辑，重点把启动入口压缩在总览页左侧。</div>
        """,
        unsafe_allow_html=True,
    )
    render_launch_form(data, compact=True, show_preview=False, show_failure_warnings=True)


def render_strategy_health_board(data) -> None:
    metrics = sorted(
        generate_strategy_metrics(data),
        key=lambda item: (item["success_rate"], -item["avg_duration_ms"]),
        reverse=True,
    )[:3]
    metrics.extend([None] * (3 - len(metrics)))
    st.markdown(
        """
        <div class="panel-heading">策略健康看板</div>
        <div class="panel-helper">展示当前最值得关注的 3 个策略版本，便于在演示前快速判断稳定性。</div>
        """,
        unsafe_allow_html=True,
    )
    slots = st.columns(3, gap="medium")
    for col, item in zip(slots, metrics):
        with col:
            if item is None:
                st.metric(label="暂无更多策略", value="—")
                st.caption("当前无更多策略数据，保留卡位以维持布局稳定。")
            else:
                st.metric(
                    label=f"{item['name']} {item['version']}",
                    value=f"{item['success_rate'] * 100:.0f}%",
                    delta=f"平均耗时 {format_duration(item['avg_duration_ms'])}",
                )
                st.caption(item["notes"])


def render_latest_overview_run(data, run_id: str) -> tuple[bool, bool]:
    run, events, frames = iter_run_assets(data, run_id)
    if run is None or not frames:
        return False, False

    runtime_view = resolve_runtime_projection(run, events, frames)
    projected = runtime_view["projected"]
    dynamic_profile = runtime_view["dynamic_profile"]
    display_frame = runtime_view["display_frame"]
    scene_meta = runtime_view["scene_meta"]
    is_paused = runtime_view["paused"]
    animation_mode = "loop" if projected.completed else runtime_view["animation_mode"]
    payload = build_renderer_payload(
        run,
        events,
        frames,
        "overview-live",
        dynamic_profile=dynamic_profile,
        animation_mode=animation_mode,
        initial_elapsed_ms=projected.elapsed_ms,
        progress=projected.progress,
        current_stage=projected.current_stage,
        title="最新任务状态",
    )
    strategy_map = {item.id: item for item in data.strategy_versions}
    strategy = strategy_map.get(run.strategy_version_id)

    st.markdown("#### 最新任务状态")
    render_motion_scene(
        payload,
        display_frame,
        "最新任务状态",
        scene_meta=scene_meta,
        height=430,
    )
    st.progress(projected.progress, text=f"{projected.current_stage} | {run.result.scenario_label}")
    if strategy is not None:
        st.caption(f"策略：{strategy.name} {strategy.version}")
    else:
        st.caption(f"策略：{run.strategy_version_id}")

    if is_paused:
        st.warning("当前任务进度已暂停，总览与任务详情保持同步冻结。")

    if projected.completed:
        if run.result.failure_reason:
            st.error(run.result.failure_reason)
        else:
            st.success("最近一次验证已完成，右侧保留最终结果。")
        render_event_timeline(events, limit=4)
    else:
        render_event_timeline(projected.visible_events, limit=4)
        if not is_paused:
            st.caption("右侧已切换到最近一次验证的真实运行状态。")
    return True, (not projected.completed and not is_paused)


def render_live_preview_panel(data) -> None:
    latest_run_id = st.session_state.get("latest_overview_run_id")
    if latest_run_id:
        st.markdown(
            """
            <div class="panel-heading">最新任务状态</div>
            <div class="panel-helper">启动验证后，右侧优先展示这次真实运行的当前状态，完成后保留最终结果。</div>
            """,
            unsafe_allow_html=True,
        )
        rendered, should_refresh = render_latest_overview_run(data, latest_run_id)
        if rendered:
            if should_refresh:
                time.sleep(1)
                st.rerun()
            return
        st.session_state.latest_overview_run_id = None

    st.markdown(
        """
        <div class="panel-heading">实时动作预览</div>
        <div class="panel-helper">切换任务、策略和预设后立即刷新，右侧保留启动前的动作预览。</div>
        """,
        unsafe_allow_html=True,
    )
    render_launch_preview_fragment(
        data,
        heading="实时动作预览",
        height=430,
        event_limit=4,
    )


def render_running_summary_card(run, projected, dynamic_profile: dict[str, Any]) -> None:
    st.markdown(
        f"""
        <div class="panel-card" style="padding: 0.8rem 1rem;">
            <div class="mini-label" style="margin-bottom:0.5rem;">运行摘要</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.25rem 1rem;">
                <div class="run-copy"><b>目标工件：</b>{html.escape(run.input_params['object_label'])}</div>
                <div class="run-copy"><b>放置目标：</b>{html.escape(run.input_params['target_slot'])}</div>
                <div class="run-copy"><b>来源料仓：</b>{html.escape(run.input_params['source_bin'])}</div>
                <div class="run-copy"><b>预设场景：</b>{html.escape(run.result.scenario_label)}</div>
                <div class="run-copy"><b>动态节奏：</b>{html.escape(PACE_DISPLAY_LABELS[dynamic_profile['pace']])}</div>
                <div class="run-copy"><b>关注焦点：</b>{html.escape(FOCUS_DISPLAY_LABELS[dynamic_profile['focus']])}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if run.result.operator_note:
        st.info(f"备注：{run.result.operator_note}")


def render_completed_summary_card(run) -> None:
    st.markdown(
        f"""
        <div class="panel-card" style="padding: 0.8rem 1rem;">
            <div class="mini-label" style="margin-bottom:0.5rem;">结果摘要</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.25rem 1rem;">
                <div class="run-copy"><b>最终结论：</b>{html.escape(human_stage_summary(run))}</div>
                <div class="run-copy"><b>目标工件：</b>{html.escape(run.input_params['object_label'])}</div>
                <div class="run-copy" style="grid-column: 1 / -1;"><b>关键观察：</b>{html.escape(run.result.key_observation)}</div>
                <div class="run-copy" style="grid-column: 1 / -1;">{html.escape(run.result.notes)}</div>
                <div class="run-copy"><b>放置目标：</b>{html.escape(run.input_params['target_slot'])}</div>
                <div class="run-copy"><b>来源料仓：</b>{html.escape(run.input_params['source_bin'])}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_replay_summary_card(frame: ReplayFrame) -> None:
    st.markdown(
        f"""
        <div class="panel-card" style="padding: 0.8rem 1rem;">
            <div class="mini-label" style="margin-bottom:0.5rem;">回放摘要</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.25rem 1rem;">
                <div class="run-copy"><b>当前阶段：</b>{html.escape(frame.stage)}</div>
                <div class="run-copy"><b>工件：</b>{html.escape(frame.target_state['object_label'])}</div>
                <div class="run-copy"><b>抓手状态：</b>{html.escape(frame.gripper_state)}</div>
                <div class="run-copy"><b>末端位姿：</b>x={frame.arm_pose['x']} y={frame.arm_pose['y']}</div>
                <div class="run-copy"><b>目标托盘：</b>{html.escape(frame.target_state['target_slot'])}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_recent_tasks_table(data) -> None:
    runs = ad_hoc_run_records(data)[:12]
    if not runs:
        st.info("暂无任务记录，快去启动一次验证吧。")
        return

    task_map = {item.id: item for item in data.task_templates}
    strategy_map = {item.id: item for item in data.strategy_versions}
    df_data = []
    for run in runs:
        task_name = task_map.get(run.task_template_id)
        strategy_obj = strategy_map.get(run.strategy_version_id)
        summary = human_stage_summary(run)
        df_data.append(
            {
                "启动时间": format_timestamp(run.started_at),
                "任务模板": task_name.name if task_name else run.task_template_id,
                "策略版本": (
                    f"{strategy_obj.name} {strategy_obj.version}"
                    if strategy_obj
                    else run.strategy_version_id
                ),
                "状态": STATUS_STYLE.get(run.status, (run.status, "", ""))[0],
                "结果": "✅ 成功" if run.result.success else "❌ 失败",
                "耗时": format_duration(run.duration_ms),
                "结论": summary[:28] + "..." if len(summary) > 28 else summary,
            }
        )

    st.markdown(
        """
        <div class="panel-heading" style="margin-top:0.25rem;">最近验证任务</div>
        <div class="panel-helper">最近 12 条记录，聚焦真实任务名、策略显示名和可读结论。</div>
        """,
        unsafe_allow_html=True,
    )
    st.dataframe(
        df_data,
        use_container_width=True,
        hide_index=True,
        column_config={
            "启动时间": st.column_config.TextColumn("启动时间", width="medium"),
            "任务模板": st.column_config.TextColumn("任务模板", width="medium"),
            "策略版本": st.column_config.TextColumn(
                "策略版本",
                width="medium",
                help="名称 + 版本号，便于演示时快速识别策略。",
            ),
            "状态": st.column_config.TextColumn("状态", width="small"),
            "结果": st.column_config.TextColumn("结果", width="small"),
            "耗时": st.column_config.TextColumn("耗时", width="small"),
            "结论": st.column_config.TextColumn("结论", width="large"),
        },
    )
    st.caption("表格支持列头排序；完整历史与单条详情可在任务工作台页继续查看。")


def render_overview(data) -> None:
    render_command_center_header(
        kicker="Command Center",
        body="具身智能策略验证中控台 · 实时健康监测",
    )

    render_kpi_bar(data)

    left_col, right_col = st.columns([4, 6], gap="large")
    with left_col:
        render_launch_form(data, compact=False, show_preview=False, show_failure_warnings=True)
        st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
        render_strategy_health_board(data)
    with right_col:
        render_live_preview_panel(data)

    with st.expander("📋 最近验证任务", expanded=False):
        render_run_grid(data)


def run_selector(data, key: str, selected_id: str | None) -> str:
    options = build_run_selector_options(data)
    if not options:
        return ""
    labels = list(options.keys())
    default_index = next((idx for idx, label in enumerate(labels) if options[label] == selected_id), 0)
    chosen_label = st.selectbox("选择运行记录", labels, index=default_index, key=key)
    return options[chosen_label]


def _render_workspace_detail_tab(run, events, frames, runtime_view) -> None:
    """任务工作台 - 详情总览 tab（已完成态）。"""
    projected = runtime_view["projected"]
    dynamic_profile = runtime_view["dynamic_profile"]
    display_frame = runtime_view["display_frame"]
    scene_meta = runtime_view["scene_meta"]
    payload = build_renderer_payload(
        run, events, frames, "detail",
        dynamic_profile=dynamic_profile,
        animation_mode="static",
        initial_elapsed_ms=projected.elapsed_ms,
        progress=projected.progress,
        current_stage=projected.current_stage,
        title="最终验证结果",
    )
    st.markdown(
        f"""
        <div class="overview-title" style="font-size:2.3rem;margin:0 0 0.5rem 0;">
            {'任务成功' if run.result.success else '任务失败'}
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(human_stage_summary(run))
    scene_col, info_col = st.columns([7, 3], gap="large")
    with scene_col:
        render_motion_scene(
            payload, display_frame, "最终验证结果",
            scene_meta=scene_meta, height=480,
        )
        render_completed_summary_card(run)
        if st.button("拿这次运行去对比", use_container_width=True, key="workspace-to-compare"):
            st.session_state.compare_left_id = run.id
            st.session_state.page = "版本对比"
            st.rerun()
    with info_col:
        st.markdown("#### 运行指标")
        st.metric("质量分", f"{run.result.quality_score:.2f}")
        st.metric("耗时", format_duration(run.duration_ms))
        st.metric("预设场景", run.result.scenario_label)
        if run.result.failure_reason:
            st.error(run.result.failure_reason)
        if run.result.operator_note:
            st.info(f"备注：{run.result.operator_note}")
        st.markdown("#### 执行时间线")
        render_event_timeline(events)

def _render_workspace_replay_tab(run, events, frames) -> None:
    """任务工作台 - 帧级回放 tab（已完成态）。"""
    dynamic_profile = extract_dynamic_profile(run)
    frame_index = st.slider("回放进度", 0, len(frames) - 1, len(frames) - 1, key="workspace-replay-slider")
    frame = frames[frame_index]
    progress_value = (frame_index + 1) / len(frames)
    scene_meta = scene_meta_for_run(run, frames, frame, dynamic_profile)
    payload = build_renderer_payload(
        run, events, frames, "replay",
        dynamic_profile=dynamic_profile,
        initial_elapsed_ms=frame.offset_ms,
        progress=progress_value,
        current_stage=frame.stage,
        title="任务回放",
    )
    visible_events = [event for event in events if event.offset_ms <= frame.offset_ms]
    st.progress(progress_value, text=f"{frame.stage} | {format_timestamp(frame.timestamp)}")
    st.caption(
        f"动态规则：{PACE_DISPLAY_LABELS[dynamic_profile['pace']]} · "
        f"{FOCUS_DISPLAY_LABELS[dynamic_profile['focus']]}"
    )
    scene_col, info_col = st.columns([7, 3], gap="large")
    with scene_col:
        render_motion_scene(
            payload, frame, "任务回放",
            scene_meta=scene_meta, height=480,
        )
    with info_col:
        render_replay_summary_card(frame)
        st.markdown("#### 执行时间线")
        render_event_timeline(visible_events, limit=6)
    metric_cols = st.columns(4)
    metric_cols[0].metric("当前阶段", frame.stage)
    metric_cols[1].metric("当前进度", f"{progress_value * 100:.0f}%")
    metric_cols[2].metric("当前时间", format_duration(frame.offset_ms))
    metric_cols[3].metric("总时长", format_duration(run.duration_ms))


def _render_workspace_live(run, events, frames, runtime_view) -> None:
    """任务工作台 - 实时监控视图（运行态）。"""
    projected = runtime_view["projected"]
    dynamic_profile = runtime_view["dynamic_profile"]
    display_frame = runtime_view["display_frame"]
    scene_meta = runtime_view["scene_meta"]
    is_paused = runtime_view["paused"]
    payload = build_renderer_payload(
        run, events, frames, "detail",
        dynamic_profile=dynamic_profile,
        animation_mode=runtime_view["animation_mode"],
        initial_elapsed_ms=projected.elapsed_ms,
        progress=projected.progress,
        current_stage=projected.current_stage,
        title="实时任务状态",
    )
    st.markdown("#### 实时任务状态")

    @st.fragment
    def _scene_fragment() -> None:
        scene_col, info_col = st.columns([7, 3], gap="large")
        with scene_col:
            render_motion_scene(
                payload, display_frame, "实时任务状态",
                scene_meta=scene_meta, height=480,
            )
            st.progress(projected.progress, text=f"运行状态：{projected.current_stage}")
            pause_col, status_col = st.columns([0.18, 0.82], gap="medium")
            pause_label = "继续" if is_paused else "暂停"
            if pause_col.button(pause_label, key=f"detail-pause-toggle-{run.id}", use_container_width=True):
                st.session_state.page = "任务工作台"
                st.session_state.selected_run_id = run.id
                toggle_runtime_pause(run)
                st.rerun()
            with status_col:
                if is_paused:
                    st.warning("当前任务进度已暂停，总览与任务详情会同时冻结。")
                else:
                    st.caption("可使用\u201c暂停\u201d真正冻结当前任务进度，便于讲解当前动作和时间线。")
            render_running_summary_card(run, projected, dynamic_profile)
            if not is_paused:
                st.info("任务仍在运行，页面会每秒自动刷新一次。")
        with info_col:
            st.markdown(status_badge(projected.run_record.status), unsafe_allow_html=True)
            st.caption(f"当前阶段：{projected.current_stage}")
            st.metric("进度", f"{projected.progress * 100:.0f}%")
            st.metric("已用时", format_duration(projected.elapsed_ms))
            st.metric("预计总时长", format_duration(run.duration_ms))
            st.markdown("#### 执行时间线")
            render_event_timeline(projected.visible_events, limit=6)

    _scene_fragment()
    if not is_paused:
        time.sleep(1)
        st.rerun()


def render_task_workspace(data) -> None:
    """合并后的任务工作台：运行中 → 实时监控；已完成 → tabs 切换详情/回放。"""
    selected_run_id = st.session_state.selected_run_id or (data.run_records[0].id if data.run_records else None)
    strategy_map = {item.id: item for item in data.strategy_versions}
    selected_run, _, _ = iter_run_assets(data, selected_run_id) if selected_run_id else (None, [], [])
    if selected_run is not None:
        strategy = strategy_map.get(selected_run.strategy_version_id)
        strategy_label = (
            f"{strategy.name} {strategy.version}"
            if strategy is not None
            else selected_run.strategy_version_id
        )
        header_body = (
            f"任务工作台 · {selected_run.result.scenario_label} · {strategy_label}"
        )
    else:
        header_body = "任务工作台 · 查看运行状态、时间线、回放和结论"
    render_command_center_header(
        kicker="Task Workspace",
        body=header_body,
    )
    if not data.run_records:
        st.info("暂无运行记录，请先启动一次验证。")
        return

    run_id = run_selector(data, "workspace-selector", st.session_state.selected_run_id)
    if not run_id:
        st.info("暂无可选择的运行记录。")
        return
    st.session_state.selected_run_id = run_id
    run, events, frames = iter_run_assets(data, run_id)
    if run is None:
        st.error("未找到对应运行记录。")
        return
    if not frames:
        st.warning("该运行缺少动作帧，暂时无法展示。")
        return
    runtime_view = resolve_runtime_projection(run, events, frames)
    projected = runtime_view["projected"]

    if projected.completed:
        detail_tab, replay_tab = st.tabs(["📊 详情总览", "🔁 帧级回放"])
        with detail_tab:
            _render_workspace_detail_tab(run, events, frames, runtime_view)
        with replay_tab:
            _render_workspace_replay_tab(run, events, frames)
    else:
        _render_workspace_live(run, events, frames, runtime_view)


def render_compare(data) -> None:
    st.subheader("版本对比")
    if len(data.run_records) < 2:
        st.warning("至少需要两条运行记录才能做对比。")
        return
    run_labels = build_run_selector_options(data)
    labels = list(run_labels.keys())
    left_default = next((idx for idx, label in enumerate(labels) if run_labels[label] == st.session_state.compare_left_id), 0)
    right_default = next((idx for idx, label in enumerate(labels) if run_labels[label] == st.session_state.compare_right_id), 1 if len(labels) > 1 else 0)
    cols = st.columns(2)
    left_label = cols[0].selectbox("左侧运行", labels, index=left_default, key="compare-left")
    right_label = cols[1].selectbox("右侧运行", labels, index=right_default, key="compare-right")
    left_id = run_labels[left_label]
    right_id = run_labels[right_label]
    if left_id == right_id:
        st.warning("请选择两条不同的运行记录。")
        return
    st.session_state.compare_left_id = left_id
    st.session_state.compare_right_id = right_id
    left_run, left_events, left_frames = iter_run_assets(data, left_id)
    right_run, right_events, right_frames = iter_run_assets(data, right_id)
    summary = build_comparison_summary(left_run, right_run, left_events, right_events)
    st.markdown(
        f"<div class='compare-banner'>推荐优先展示 <strong>{html.escape(summary.recommended_run_id)}</strong>。原因：{html.escape(summary.recommended_reason)}</div>",
        unsafe_allow_html=True,
    )
    metric_cols = st.columns(3)
    metric_cols[0].metric("成功差异", summary.success_diff)
    metric_cols[1].metric("耗时差异", duration_delta_text(summary.duration_diff_ms))
    metric_cols[2].metric("推荐运行", summary.recommended_run_id)
    st.info(summary.failure_reason_diff)
    st.caption(summary.log_summary_diff)
    side_by_side = st.columns(2)
    for column, run, frames, side_title in (
        (side_by_side[0], left_run, left_frames, "左侧"),
        (side_by_side[1], right_run, right_frames, "右侧"),
    ):
        with column:
            final_frame = frames[-1] if frames else None
            side_events = left_events if side_title == "左侧" else right_events
            payload = build_renderer_payload(
                run,
                side_events,
                frames,
                "compare",
                initial_elapsed_ms=final_frame.offset_ms if final_frame else 0,
                progress=1.0 if final_frame else 0.0,
                current_stage=final_frame.stage if final_frame else human_stage_summary(run),
                title=f"{side_title}最终帧",
                compare_label=side_title,
            )
            st.markdown(
                f"""
                <div class="panel-card">
                    <div class="mini-label">{side_title}运行</div>
                    <div style="margin-top:0.3rem;">{status_badge(run.status)}</div>
                    <div class="run-copy">策略：{html.escape(run.strategy_version_id)}</div>
                    <div class="run-copy">耗时：{format_duration(run.duration_ms)}</div>
                    <div class="run-copy">结论：{html.escape(human_stage_summary(run))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            render_motion_scene(payload, final_frame, f"{side_title}最终帧", height=360)


def render_benchmark_lab(data) -> None:
    st.subheader("基准评测")
    task_options = {item.name: item.id for item in data.task_templates}
    strategy_options = {f"{item.name} {item.version}": item.id for item in data.strategy_versions}
    suite_options = {item.name: item.id for item in data.benchmark_suites}
    suite_map = {item.id: item for item in data.benchmark_suites}
    strategy_map = {item.id: item for item in data.strategy_versions}
    launch_col, help_col = st.columns([1, 1.05])
    with launch_col:
        st.markdown("#### 启动一轮批量评测")
        with st.form("benchmark-form", clear_on_submit=False):
            template_name = st.selectbox("任务模板", list(task_options.keys()), key="benchmark-task")
            suite_name = st.selectbox("评测套件", list(suite_options.keys()), key="benchmark-suite")
            strategy_name = st.selectbox("策略版本", list(strategy_options.keys()), key="benchmark-strategy")
            operator_note = st.text_input(
                "备注",
                placeholder="例如：投递具身智能岗位前的稳定性检查",
                key="benchmark-note",
            )
            submitted = st.form_submit_button("生成一轮评测结果", use_container_width=True)
            if submitted:
                batch_id = STORE.create_benchmark_batch(
                    task_template_id=task_options[template_name],
                    strategy_version_id=strategy_options[strategy_name],
                    suite_id=suite_options[suite_name],
                    operator_note=operator_note,
                )
                st.session_state.selected_benchmark_batch_id = batch_id
                st.rerun()
    with help_col:
        st.markdown(
            """
            <div class="panel-card">
                <div class="mini-label">为什么加这页</div>
                <div style="color:#eef2ff;font-size:1.15rem;font-weight:700;margin:0.35rem 0 0.5rem 0;">
                    把单次演示升级成最小评测闭环
                </div>
                <div class="run-copy">
                    单次运行只能说明“这个例子跑过了”。批量评测才能回答策略在不同场景下稳不稳、
                    失败集中在哪、适不适合做默认方案。
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    batches = benchmark_batches_sorted(data)
    if not batches:
        st.info("还没有评测批次。先在上面生成一轮评测结果。")
        return

    labels: list[str] = []
    label_to_id: dict[str, str] = {}
    for batch in batches:
        suite = suite_map.get(batch.suite_id)
        strategy = strategy_map.get(batch.strategy_version_id)
        suite_name = suite.name if suite else batch.suite_id
        strategy_name = (
            f"{strategy.name} {strategy.version}" if strategy else batch.strategy_version_id
        )
        label = f"{format_timestamp(batch.created_at)} | {strategy_name} | {suite_name}"
        labels.append(label)
        label_to_id[label] = batch.id

    selected_batch_id = st.session_state.selected_benchmark_batch_id
    default_index = next(
        (idx for idx, label in enumerate(labels) if label_to_id[label] == selected_batch_id),
        0,
    )
    chosen_label = st.selectbox("查看评测批次", labels, index=default_index, key="benchmark-batch-selector")
    batch_id = label_to_id[chosen_label]
    st.session_state.selected_benchmark_batch_id = batch_id
    batch = next(item for item in batches if item.id == batch_id)
    suite = suite_map[batch.suite_id]
    runs = benchmark_runs_for_batch(data, batch)
    summary = summarize_benchmark_batch(batch, suite, runs)

    metric_cols = st.columns(4)
    metric_cols[0].metric("成功率", f"{summary['success_rate'] * 100:.0f}%")
    metric_cols[1].metric("通过用例", f"{summary['success_count']} / {summary['total_cases']}")
    metric_cols[2].metric("平均耗时", format_duration(summary["avg_duration_ms"]))
    metric_cols[3].metric("评测套件", suite.name)
    st.markdown(
        f"""
        <div class="compare-banner">
            结论：{html.escape(summary['recommendation'])}
            <br />
            关注指标：{html.escape(" / ".join(summary["focus_metrics"]))}
        </div>
        """,
        unsafe_allow_html=True,
    )
    if batch.operator_note:
        st.caption(f"批次备注：{batch.operator_note}")
    st.info(summary["failure_breakdown_text"])

    case_rows = [summary["case_results"][index : index + 2] for index in range(0, len(summary["case_results"]), 2)]
    for row_index, row in enumerate(case_rows):
        columns = st.columns(len(row))
        for column, item in zip(columns, row):
            with column:
                badge = status_badge("succeeded" if item["status"] == "成功" else "failed")
                st.markdown(
                    f"""
                    <div class="run-card">
                        {badge}
                        <div class="run-title">{html.escape(item['case_name'])}</div>
                        <div class="run-copy">质量分 {item['quality_score']:.2f}</div>
                        <div class="run-copy">耗时 {format_duration(item['duration_ms'])}</div>
                        <div class="run-copy" style="margin-top:0.45rem;">{html.escape(item['summary'])}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                action_cols = st.columns(2)
                if action_cols[0].button(
                    "看详情",
                    key=f"benchmark-detail-{row_index}-{item['run_id']}",
                    use_container_width=True,
                ):
                    st.session_state.selected_run_id = item["run_id"]
                    st.session_state.page = "任务工作台"
                    st.rerun()
                if action_cols[1].button(
                    "回放",
                    key=f"benchmark-replay-{row_index}-{item['run_id']}",
                    use_container_width=True,
                ):
                    st.session_state.selected_run_id = item["run_id"]
                    st.session_state.page = "任务工作台"
                    st.rerun()


def main() -> None:
    st.set_page_config(page_title="仿真机械臂任务验证平台", page_icon="🦾", layout="wide", initial_sidebar_state="expanded")
    inject_styles()
    current_time = now_local()
    data = STORE.load()
    ensure_state(
        [run.id for run in ad_hoc_run_records(data)],
        [batch.id for batch in benchmark_batches_sorted(data)],
    )
    runtime_overrides = build_runtime_sync_overrides(data, current=current_time)
    if sync_run_statuses(data, current=current_time, runtime_overrides=runtime_overrides):
        STORE.save(data)
    with st.sidebar:
        st.markdown("### 导航")
        st.session_state.page = st.radio("页面", PAGES, index=PAGES.index(st.session_state.page))
        st.session_state.role = st.selectbox("当前角色视角", list(ROLE_HINTS.keys()), index=list(ROLE_HINTS.keys()).index(st.session_state.role))
        render_role_brief(st.session_state.role)
        st.session_state.renderer_mode = st.selectbox(
            "动作渲染器",
            ["threejs", "svg"],
            index=["threejs", "svg"].index(st.session_state.renderer_mode),
            format_func=lambda item: "Three.js 2.5D" if item == "threejs" else "SVG 回退",
        )
        if st.session_state.renderer_mode == "threejs" and not bundle_available():
            st.warning("Three.js bundle 不存在，当前已自动回退到 SVG。先执行 web/robot_renderer 的构建。")
        st.caption("默认数据由本地 JSON 自动初始化，适合单机录屏演示。")
    if st.session_state.page == "总览":
        render_overview(data)
    elif st.session_state.page == "任务工作台":
        render_task_workspace(data)
    elif st.session_state.page == "版本对比":
        render_compare(data)
    else:
        render_benchmark_lab(data)


if __name__ == "__main__":
    main()
