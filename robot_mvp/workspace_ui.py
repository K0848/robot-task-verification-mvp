"""面向用户的V2页面组合，只消费业务服务，不决定物理结果或可比性。"""
from __future__ import annotations

import html
import json
import math
import os

import streamlit as st

from robot_mvp.v2_service import DEFAULT_MODEL, V2RunService
from robot_mvp.v2_view import render_evidence

STATUS_LABELS = {'queued':'排队中','running':'执行中','succeeded':'已完成','failed':'已失败',
                 'cancelled':'已取消','unknown':'状态未知'}
STAGE_LABELS = {'queued':'准备任务','approach':'接近','descend':'下降','grasp':'抓取','lift':'抬升',
                'transport':'搬运','place':'放置','release':'释放','retreat':'回撤','settle':'稳定观察','complete':'已完成'}


def inject_workspace_styles() -> None:
    st.markdown("""<style>
    .block-container{max-width:1280px;padding-top:3.6rem}
    .rf-brand{font-size:13px;letter-spacing:.12em;color:#79dcd1;margin-bottom:14px}
    .rf-brand b{letter-spacing:0;color:#e7edf8;font-size:19px;margin-right:12px}
    .rf-subtitle{color:#a4b4c9;font-size:14px;line-height:1.6;margin:-10px 0 18px}
    .rf-context{display:flex;gap:10px;flex-wrap:wrap;color:#bfcbda;font-size:13px;margin:4px 0 14px}
    .rf-context span{border:1px solid #344659;border-radius:20px;padding:4px 10px;background:#122132}
    .rf-empty{border:1px dashed #3d5267;border-radius:12px;text-align:center;padding:48px 24px;background:#101b2b;color:#adbed1}
    .rf-empty strong{display:block;font-size:22px;color:#ecf3fb;margin-bottom:14px}
    .rf-record-title{font-size:15px;color:#e2edf8;font-weight:600;margin-bottom:4px}
    .rf-small{font-size:12px;color:#aebed0;line-height:1.7}
    .rf-pill{display:inline-block;padding:4px 10px;border-radius:20px;font-size:12px;border:1px solid #425065;color:#d8e4f4}
    .rf-pill.success{background:#102c27;color:#80e0bd;border-color:#255246}
    .rf-pill.failed{background:#352029;color:#ffb6ba;border-color:#64343c}
    .rf-pill.unknown{background:#202b3a;color:#ccd8e8}
    .st-key-rf-nav [role=radiogroup]{gap:8px;border-bottom:1px solid #26364b;padding-bottom:14px}
    .st-key-rf-nav [data-baseweb=radio]{padding:8px 16px;border:1px solid #344659;border-radius:8px;background:#101b2b}
    .st-key-rf-nav [data-baseweb=radio]:has(input:checked){border-color:#58cfbf;background:#12332f}
    .stButton button[data-testid=stBaseButton-primary]{background:#40c8b3;color:#06241f;border-color:#67e0cd;font-weight:650}
    .stButton button[data-testid=stBaseButton-primary] p{color:#06241f!important}
    button[data-testid=stPopoverButton]{background:#142437;color:#dfeaf6;border:1px solid #395069}
    button[data-testid=stPopoverButton] p{color:#dfeaf6!important}
    [data-testid=stPopoverBody]{background:#111e2f;color:#e1eaf4;border:1px solid #395069}
    .st-key-rf-result-metrics [data-testid=stHorizontalBlock]{flex-wrap:nowrap!important;gap:14px}
    .st-key-rf-result-metrics [data-testid=stColumn]{min-width:0!important;width:auto!important;flex:1 1 0!important}
    button:focus-visible,select:focus-visible,input:focus-visible,summary:focus-visible{outline:2px solid #68dcce!important;outline-offset:3px}
    .st-key-rf-config{background:#111d2c;border-color:#31455b;border-radius:12px}
    [data-testid=stMetricValue]{font-size:28px}
    @media(max-width:700px){.block-container{padding:3.6rem 1rem 1rem}.rf-empty{padding:30px 16px}.rf-brand b{display:block}.st-key-rf-nav [data-baseweb=radio]{padding:7px 10px}.st-key-rf-result-metrics [data-testid=stMetricValue]{font-size:23px}}
    @media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;animation-duration:0s!important;transition-duration:0s!important}}
    </style>""", unsafe_allow_html=True)


def preset_label(preset: dict) -> str:
    name = preset['label'].split('（',1)[0]
    return f"{name} · 偏移 {preset['grasp_offset']*100:g} cm"


def parameter_label(record: dict, names: dict) -> str:
    key=str(record.get('strategy_id') or '未命名方案')
    name=names.get(key,key)
    value=record['parameters'].get('grasp_offset')
    offset=f'{value*100:g} cm' if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) else '未知'
    return f'{name} · 偏移 {offset}'


def record_label(record: dict, names: dict) -> str:
    success = record['task_success']
    outcome = '报告成功' if success is True else '报告失败' if success is False else STATUS_LABELS.get(record['status'],'未判定')
    return f"{record['created_at'][:19].replace('T',' ')} UTC · {parameter_label(record,names)} · {outcome} · #{record['run_id'][-6:]}"


def open_run(run_id: str, model_id: str = DEFAULT_MODEL) -> None:
    st.session_state[f'rf-view-run-{model_id}'] = run_id
    st.session_state['rf-page'] = '验证工作台'
    st.session_state['rf-legacy'] = False


def set_history_page(offset: int) -> None:
    st.session_state['rf-history-offset'] = max(0, offset)


@st.fragment(run_every='1s')
def render_running(service: V2RunService, handle) -> None:
    try:
        status = service.poll(handle)
    except (OSError,ValueError) as error:
        st.error(f'暂时无法读取执行状态：{error}。未自动删除记录或取消任务。')
        return
    if status['status'] in {'succeeded','failed','cancelled'}:
        st.rerun(scope='app')
    st.progress(float(status.get('progress',0)),text=f"后台执行中 · {STAGE_LABELS.get(status.get('stage'),status.get('stage','准备任务'))}")
    st.caption('可以查看历史记录；页面回放操作不会控制后台机器人。')


def render_record(service: V2RunService, run_id: str) -> None:
    try:
        record = service.get_run(run_id)
    except (OSError,ValueError) as error:
        st.error(f'无法打开运行：{error}')
        return
    st.caption(f"当前查看 · {record['created_at'][:19].replace('T',' ')} UTC · #{run_id[-6:]}")
    if record['integrity']=='invalid':
        st.error('该运行记录或证据无法通过核验，不展示为有效回放。')
        with st.expander('查看异常原因',expanded=True):
            for issue in record['issues']:st.write(f"{issue.get('file','记录')}：{issue['message']}")
            if record['report_available']:
                st.caption('以下为未与完整证据核对的原始报告。')
                st.json(record['summary'])
        return
    if record['integrity'] in {'pending','unavailable'}:
        if record['error_code']:
            st.error(f"执行异常 · 任务结果未判定：{record['error_message'] or record['error_code']}")
        else:
            st.info(f"记录状态：{STATUS_LABELS.get(record['status'],'未知')}。尚无可核对的完整任务报告。")
        if st.button('刷新运行状态',key=f'rf-refresh-{run_id}'):
            st.rerun()
        with st.expander('运行信息'):
            st.json(record)
        return
    render_evidence(service.manager.artifacts.run_dir(run_id))


@st.fragment
def render_comparison(service: V2RunService, model_id: str = DEFAULT_MODEL) -> None:
    st.subheader('比较运行')
    st.caption('核对固定条件下的参数差异与结果，不自动推荐上线。')
    catalog=service.list_runs(model_id=model_id,limit=200)
    records=[record for record in catalog['items'] if record['integrity']=='metadata_only']
    if len(records)<2:
        st.info('本模型至少有两次完整运行后，可在这里比较或检查重复性。')
        return
    suggestion=service.suggest_comparison(model_id=model_id)
    names={preset['id']:preset['label'].split('（',1)[0] for preset in service.presets()}
    labels={record['run_id']:record_label(record,names) for record in records}
    defaults=suggestion['run_ids'] if all(run_id in labels for run_id in suggestion['run_ids']) else []
    if not defaults:st.caption(suggestion['reason'])
    if catalog['has_more']:st.caption('此处列出最近200条记录，完整历史请到运行记录分页查看。')
    selected=st.multiselect('选择比较记录',list(labels),default=defaults,format_func=labels.get,key=f'v2-compare-{model_id}')
    key=f'rf-comparison-result-{model_id}'
    if st.button('生成比较',disabled=len(selected)<2,key=f'rf-compare-{model_id}'):
        try:
            st.session_state[key]={'selection':tuple(selected),'report':service.compare(selected)}
        except (OSError,ValueError,TypeError,KeyError) as error:
            st.error(f'无法生成比较：{error}')
            st.session_state.pop(key,None)
    saved=st.session_state.get(key)
    if not saved or saved['selection']!=tuple(selected):return
    report=saved['report']
    if report['comparison_status']=='rejected':
        st.error(report['conclusion'])
    else:
        kind='重复性检查' if report['comparison_kind']=='repeatability_check' else '受控参数比较'
        st.markdown(f'#### {kind}')
        st.info(report['conclusion'])
        rows=[{'参数方案':' / '.join(names.get(name,name) for name in group['strategy_ids']),
               '抓取偏移 (cm)':group['configuration'].get('grasp_offset',0)*100,
               '运行数':group['sample_count'],'成功数':group['success_count'],
               '本组结果比例':f"{group['success_rate']:.0%}"} for group in report['parameter_groups']]
        st.dataframe(rows,hide_index=True,width='stretch')
        st.caption('比例只描述选中记录；重复次数不等于场景覆盖，证据仍不足以支持泛化。')
    with st.expander('比较依据与原始数据'):
        st.json(report)
    st.download_button('导出比较报告',json.dumps(report,ensure_ascii=False,indent=2),file_name='comparison.json',mime='application/json')


def render_workspace(service: V2RunService, *, model_id: str = DEFAULT_MODEL) -> None:
    st.title('验证工作台' if model_id==DEFAULT_MODEL else '旧平面物理任务')
    st.markdown('<div class="rf-subtitle">发起一次验证，复查动作与证据，再比较参数方案。</div>',unsafe_allow_html=True)
    models={item['id']:item for item in service.models()}
    model_label=models[model_id]['label'].split('（',1)[0]
    st.markdown(f'<div class="rf-context"><span>{html.escape(model_label)}</span><span>方块抓取与放置</span><span>物理仿真 · 非真机控制</span></div>',unsafe_allow_html=True)
    handle=st.session_state.get('v2_job_handle')
    active=False
    if handle:
        try:active=service.poll(handle)['status'] in {'queued','running'}
        except (OSError,ValueError):active=True
    presets={preset['id']:preset for preset in service.presets()}
    with st.container(border=True,key='rf-config'):
        controls=st.columns([3,1],vertical_alignment='bottom')
        with controls[0]:
            preset=st.selectbox('参数方案',list(presets),format_func=lambda value:preset_label(presets[value]),key='v2-strategy',disabled=active)
        fault=None
        if os.environ.get('ROBOTS_ENABLE_FAULT_TESTS')=='1':
            with st.expander('本地验收诊断（非策略评测）'):
                value=st.selectbox('故障注入',['none','crash','timeout'],key='v2-fault')
                fault=None if value=='none' else value
        with controls[1]:
            start=st.button('开始验证',type='primary',disabled=active,width='stretch',key='rf-start')
        st.caption('方案只改变控制参数，不预设成功或失败。采用脚本控制，不覆盖视觉感知误差。')
    selection_key=f'rf-view-run-{model_id}'
    if start:
        try:
            new_handle=service.start_run(preset,model_id=model_id,fault_mode=fault,wall_timeout_s=.5 if fault=='timeout' else 30.)
        except (OSError,ValueError) as error:
            st.error(f'未能启动验证：{error}')
        else:
            st.session_state.v2_job_handle=new_handle
            st.session_state[selection_key]=new_handle.run_id
            st.rerun()
    if selection_key not in st.session_state:
        recent=service.list_runs(model_id=model_id,limit=1)['items']
        st.session_state[selection_key]=recent[0]['run_id'] if recent else None
    if active:
        render_running(service,handle)
    selected=st.session_state[selection_key]
    if selected and not (active and handle.run_id==selected):
        render_record(service,selected)
    elif not active:
        st.markdown('<div class="rf-empty"><strong>从一次真实运行开始</strong>选择上方参数方案并开始验证。完成后，这里将显示机械臂回放、任务结论与可复查证据。</div>',unsafe_allow_html=True)
    with st.expander('比较参数与结果'):
        render_comparison(service,model_id)


def render_history(service: V2RunService) -> None:
    st.title('运行记录')
    st.markdown('<div class="rf-subtitle">只展示Panda物理运行。找到记录，再打开工作台核对完整证据。</div>',unsafe_allow_html=True)
    names={preset['id']:preset['label'].split('（',1)[0] for preset in service.presets()}
    statuses={'全部':None,'排队中':'queued','执行中':'running','已完成':'succeeded','失败（含执行异常）':'failed','状态未知':'unknown'}
    with st.container(border=True):
        cols=st.columns([2,1])
        with cols[0]:chosen=st.selectbox('执行状态',list(statuses),key='rf-history-status')
        with cols[1]:size=st.selectbox('每页记录',[10,20,50],key='rf-history-size')
        with st.expander('更多筛选'):
            diagnostic=st.checkbox('包含诊断注入记录',value=False,key='rf-history-diagnostic')
    signature=(chosen,size,diagnostic)
    if st.session_state.get('rf-history-filter')!=signature:
        st.session_state['rf-history-filter']=signature
        st.session_state['rf-history-offset']=0
    offset=st.session_state.get('rf-history-offset',0)
    catalog=service.list_runs(status=statuses[chosen],limit=size,offset=offset,include_diagnostics=diagnostic)
    if offset and offset>=catalog['total']:
        st.session_state['rf-history-offset']=0;st.rerun()
    if catalog['issues']:
        st.warning(f"有{len(catalog['issues'])}条记录无法确定归属，未静默当作正常数据。")
        with st.expander('目录异常原因'):st.json(catalog['issues'])
    if not catalog['items']:
        st.info('当前筛选下没有运行记录。可以返回验证工作台开始一次验证。')
        return
    st.caption(f"共 {catalog['total']} 条 · 当前 {offset+1}–{offset+len(catalog['items'])} 条。列表为轻量摘要，打开后核验完整证据。")
    for record in catalog['items']:
        with st.container(border=True):
            columns=st.columns([4,2,1],vertical_alignment='center')
            with columns[0]:
                st.markdown(f"<div class='rf-record-title'>{html.escape(record['created_at'][:19].replace('T',' '))} UTC</div><div class='rf-small'>{html.escape(parameter_label(record,names))} · #{html.escape(record['run_id'][-6:])}</div>",unsafe_allow_html=True)
            with columns[1]:
                success=record['task_success']
                label='记录异常' if record['integrity']=='invalid' else '报告：成功' if success is True else '报告：失败' if success is False else STATUS_LABELS.get(record['status'],'未判定')
                kind='unknown' if success is None else 'success' if success else 'failed'
                st.markdown(f'<span class="rf-pill {kind}">{html.escape(label)}</span>',unsafe_allow_html=True)
                if record['error_code']:st.caption('执行异常 · 任务结果未判定')
                elif record['integrity']=='metadata_only':st.caption('完整证据待核对')
            with columns[2]:
                st.button('查看',key=f"rf-open-{record['run_id']}",help=f"打开运行 {record['run_id']}",on_click=open_run,args=(record['run_id'],))
    previous,next_page=st.columns(2)
    previous.button('上一页',disabled=offset==0,key='rf-history-prev',
                    on_click=set_history_page,args=(max(0,offset-size),))
    next_page.button('下一页',disabled=not catalog['has_more'],key='rf-history-next',
                     on_click=set_history_page,args=(offset+size,))
