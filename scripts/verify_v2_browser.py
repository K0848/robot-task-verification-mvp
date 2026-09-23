"""真实浏览器验收；先启动 Streamlit，使用已安装的 Playwright，不由脚本安装依赖。"""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8516')
parser.add_argument('--evidence', type=Path, default=Path('docs/evidence/v2-fixed-20260922'))
args = parser.parse_args()
args.evidence.mkdir(parents=True, exist_ok=True)
results = []


def capture(page, name):
    page.screenshot(path=str(args.evidence / f'{name}.png'), full_page=True)


def replay(page):
    frame = page.frame_locator('iframe').last
    expect(frame.locator('#play')).to_be_visible(timeout=30000)
    return frame


def seek(frame, value):
    frame.locator('#seek').evaluate('(el,value)=>{el.value=String(value);el.dispatchEvent(new Event("input",{bubbles:true}));}', value)


def select_legacy_model(page):
    # 默认入口已升级 Panda；旧回归必须显式选择平面模型，避免错用新结果。
    page.get_by_text('Panda 机械臂与夹爪（接触抓放）', exact=True).click()
    page.get_by_role('option', name='历史平面任务（位置示意）', exact=True).click()


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width':1440,'height':1100})
    errors=[]
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(args.url)
    page.get_by_text('V2 物理仿真', exact=True).click()
    select_legacy_model(page)
    start=page.get_by_role('button',name='启动 V2 物理仿真',exact=True)
    start.click()
    frame=replay(page)
    expect(start).to_be_enabled(timeout=10000)
    expect(page.get_by_test_id('stMetricValue').first).to_have_text('成功')
    # 真实点击后时间推进，跨过原先的 1s fragment 刷新窗口，不允许重置到首帧。
    frame.get_by_role('button',name='播放',exact=True).click()
    page.wait_for_timeout(1600)
    frame.get_by_role('button',name='暂停',exact=True).click()
    t=float(frame.locator('#physical-root').get_attribute('data-time-ms'))
    assert t>1000, t
    page.wait_for_timeout(1200)
    assert float(frame.locator('#physical-root').get_attribute('data-time-ms'))==t
    frame.get_by_role('button',name='播放',exact=True).click()
    page.wait_for_timeout(300)
    frame.get_by_role('button',name='暂停',exact=True).click()
    assert float(frame.locator('#physical-root').get_attribute('data-time-ms'))>t
    seek(frame,4000)
    expected=frame.locator('#physical-root').get_attribute('data-object-position')
    capture(page,'01-baseline-3d')
    frame.get_by_label('回放渲染器').select_option('svg')
    assert frame.locator('#physical-root').get_attribute('data-object-position')==expected
    assert float(frame.locator('#physical-root').get_attribute('data-time-ms'))==4000
    expect(frame.locator('svg')).to_be_visible()
    expect(frame.locator('svg [data-entity="object"]')).to_be_visible()
    assert frame.locator('pre code').count()==0
    capture(page,'02-baseline-svg')
    frame.get_by_label('回放渲染器').select_option('threejs')
    assert float(frame.locator('#physical-root').get_attribute('data-time-ms'))==4000
    frame.get_by_label('回放倍速').select_option('2')
    seek(frame,0);frame.get_by_role('button',name='播放',exact=True).click();page.wait_for_timeout(500)
    frame.get_by_role('button',name='暂停',exact=True).click()
    assert float(frame.locator('#physical-root').get_attribute('data-time-ms'))>700
    duration=float(frame.locator('#seek').get_attribute('max'))
    seek(frame,duration)
    baseline_final=json.loads(frame.locator('#physical-root').get_attribute('data-object-position'))
    assert abs(baseline_final[0]-.28)<.08
    # 从页面暴露的运行 ID 找到同一 artifact，核对展示与原始轨迹，而非只检查 renderer 存在。
    run_caption=page.get_by_text('执行状态：',exact=False).inner_text()
    run_id=run_caption.split('运行 ID：')[-1].strip()
    raw=[json.loads(line) for line in (Path('data/v2_runs')/run_id/'trajectory.jsonl').read_text(encoding='utf-8').splitlines()]
    assert baseline_final==raw[-1]['object_position']
    seek(frame,4000)
    expected4000=next(f['object_position'] for f in raw if f['sim_time_ms']==4000)
    assert json.loads(frame.locator('#physical-root').get_attribute('data-object-position'))==expected4000
    results.append({'case':'baseline_play_pause_seek_switch','run_id':run_id,'status':'pass'})
    # 不刷新页面即可连续启动另一版。
    page.get_by_test_id('stSelectbox').filter(has_text='策略参数版本').get_by_role('combobox').click()
    page.get_by_role('option').filter(has_text='受控偏移').click()
    expect(start).to_be_enabled();start.click();frame=replay(page)
    expect(page.get_by_test_id('stMetricValue').first).to_have_text('失败',timeout=30000)
    expect(start).to_be_enabled()
    seek(frame,4000)
    offset_position=json.loads(frame.locator('#physical-root').get_attribute('data-object-position'))
    assert abs(offset_position[0]+.28)<.01
    option=frame.locator('#events option').filter(has_text='未建立抓取约束').first
    frame.locator('#events').select_option(option.get_attribute('value'))
    assert frame.locator('#physical-root').get_attribute('data-stage')=='grasp'
    expect(page.get_by_text('可能原因（待验证）：',exact=False)).to_be_visible()
    capture(page,'03-offset-event')
    frame.get_by_label('回放渲染器').select_option('svg');capture(page,'04-offset-svg')
    results.append({'case':'offset_failure_event_and_restart','status':'pass'})
    page.get_by_role('button',name='清除当前运行引用',exact=True).click()
    expect(start).to_be_enabled()
    # 受影响的 V1 页面仍能打开，不宣称覆盖全部 V1 功能。
    page.get_by_text('总览',exact=True).click()
    expect(page.get_by_role('button',name='开始一次新验证',exact=True)).to_be_visible()
    results.append({'case':'v1_overview_smoke','status':'pass'})
    assert not errors, errors
    page.close()
    ctx=browser.new_context(viewport={'width':1440,'height':1100})
    ctx.add_init_script("const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...args){if(String(type).includes('webgl'))return null;return original.call(this,type,...args);};")
    page=ctx.new_page();page.goto(args.url);page.get_by_text('V2 物理仿真',exact=True).click()
    select_legacy_model(page)
    page.get_by_role('button',name='启动 V2 物理仿真',exact=True).click();frame=replay(page)
    expect(frame.locator('#fallback-notice')).to_contain_text('已回退 SVG')
    expect(frame.locator('svg')).to_be_visible()
    frame.get_by_role('button',name='播放',exact=True).click();page.wait_for_timeout(400)
    frame.get_by_role('button',name='暂停',exact=True).click()
    assert float(frame.locator('#physical-root').get_attribute('data-time-ms'))>0
    capture(page,'05-webgl-fallback')
    results.append({'case':'webgl_unavailable_svg_playback','status':'pass'})
    ctx.close();browser.close()
args.evidence.joinpath('results.json').write_text(json.dumps({'checks':results,'pageerrors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,ensure_ascii=False))
