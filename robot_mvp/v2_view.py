"""V2 只读证据视图，不复用 V1 的抽象机械臂/像素坐标。"""
import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from robot_mvp.renderer import JS_BUNDLE
from robot_mvp.v2_adapter import artifact_to_renderer_payload
from robot_mvp.v2_runtime import validate_summary


def render_evidence(artifact_dir: Path) -> None:
    # 回放损坏不应掩盖独立存在的结果报告，两类证据分别显示可信边界。
    try:
        result = json.loads((artifact_dir / 'summary.json').read_text(encoding='utf-8'))
        validate_summary(result)
        failure, criteria = result['failure'], result['success_criteria']
    except (OSError, ValueError, KeyError, TypeError) as error:
        st.error(f"运行报告不完整：{error}")
        return
    payload = None
    try:
        payload = artifact_to_renderer_payload(artifact_dir)
    except (OSError, ValueError, KeyError, TypeError) as error:
        st.error(f"运行产物不完整，无法回放：{error}。以下仅为独立读取的报告，尚未核对轨迹。")
    with st.container(key='rf-result-metrics'):
        cols = st.columns(3)
        cols[0].metric('任务结果', '成功' if result['success'] else '失败')
        cols[1].metric('仿真时长', f"{result['duration_ms']/1000:.2f} s")
        cols[2].metric('运行证据', '已核对' if payload else '不可验证')
    st.caption('以下为已结束运行的记录回放，不是实时控制机器人。')
    if payload and payload.get('robot_scene'):
        st.caption('Panda · 物理仿真记录 · 脚本控制，不覆盖视觉感知误差。')
    elif payload:
        st.caption('历史平面任务：工具/物体位置示意，不是完整机械臂。')
    if payload and JS_BUNDLE.exists():
        # 产物字符串进入 script 时转义 <，避免日志内容结束脚本标签。
        encoded = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c')
        components.html(
            '<div id="physical-root"></div><script>' + JS_BUNDLE.read_text(encoding='utf-8')
            + '</script><script>window.__V2_PAYLOAD__=' + encoded
            + ';try{window.RobotRenderer.renderPhysical(document.getElementById("physical-root"),window.__V2_PAYLOAD__);}'
            + 'catch(e){document.getElementById("physical-root").textContent="回放初始化失败："+e.message;}</script>',
            height=710 if payload.get('robot_scene') else 665, scrolling=True,
        )
    elif payload:
        st.warning('V2 交互回放需要前端构建：npm run build --prefix web/robot_renderer。结果报告仍可查看。')
    st.subheader('运行结论')
    if result['success']:
        st.success(failure['observation'])
    else:
        st.error(f"观察：{failure['observation']}")
        st.write('失败分类：', failure.get('classification') or '未知')
        st.write('可能原因（待验证）：', failure.get('possible_cause') or '未知')
        st.write('不能据此确定：', failure.get('unknown') or '暂无补充')
    st.write(f"目标距离 {criteria['target_distance_m']:.4f} m；当前阈值 {criteria['target_distance_threshold_m']:.4f} m。")
    st.caption('结论来自运行证据；单次仿真不代表策略普遍更好或真机表现。')
    if 'stable_duration_s' in criteria:
        st.write(f"接触抬升：{'已满足' if criteria['lifted'] else '未满足'} · 实际释放：{'已满足' if criteria['released'] else '未满足'} · 连续稳定 {criteria['stable_duration_s']:.2f} s / 要求 {criteria['stable_window_s']:.2f} s")
    with st.expander('技术详情与原始数据'):
        st.caption(f"运行ID：{result['run_id']} · 记录帧数：{len(payload['frames']) if payload else '不可验证'}")
        st.json(result)
        if payload:
            st.json(payload['environment'])
        st.download_button('导出原始报告', json.dumps(result, ensure_ascii=False, indent=2), file_name=f"{result['run_id']}-summary.json", mime='application/json')
