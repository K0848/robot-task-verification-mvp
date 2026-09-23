"""Panda 真实页面验收：实际 Three.js 对象、运行事实、错误恢复与浏览器资源。"""
import argparse
import json
from pathlib import Path
import time
import numpy as np
import psutil  # 本机已有验收诊断库，不加入应用生产依赖。
from playwright.sync_api import expect, sync_playwright


def rotation(q):
    w,x,y,z=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8517')
    parser.add_argument('--evidence',type=Path,default=Path('docs/evidence/panda-browser'))
    parser.add_argument('--skip-faults',action='store_true')
    parser.add_argument('--only-context-loss',action='store_true')
    parser.add_argument('--only-comparison',action='store_true')
    args=parser.parse_args();args.evidence.mkdir(parents=True,exist_ok=True)
    results,errors=[],[]
    browser_pids=set()
    def memory():
        total=0
        for proc in psutil.Process().children(recursive=True):
            try:
                if 'chrome' in proc.name().lower():
                    browser_pids.add(proc.pid);total+=proc.memory_info().rss
            except (psutil.NoSuchProcess,psutil.AccessDenied):
                pass
        return total
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1100})
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(args.url);page.get_by_text('V2 物理仿真',exact=True).click()
        start=page.get_by_role('button',name='启动 V2 物理仿真',exact=True)
        expect(start).to_be_enabled();initial_memory=memory()
        def frame():
            view=page.frame_locator('iframe').last
            expect(view.locator('#play')).to_be_visible(timeout=45000)
            return view
        def seek(view,ms):
            view.locator('#seek').evaluate('(el,v)=>{el.value=String(v);el.dispatchEvent(new Event("input",{bubbles:true}));}',ms)
        def capture(name):
            page.screenshot(path=str(args.evidence/f'{name}.png'),full_page=True)
            if page.locator('iframe').count():
                page.locator('iframe').last.screenshot(path=str(args.evidence/f'{name}-replay.png'))
        def select(label,option):
            page.get_by_test_id('stSelectbox').filter(has_text=label).get_by_role('combobox').click()
            page.get_by_role('option',name=option,exact=True).click()
        def active_run():
            return page.get_by_text('执行状态：',exact=False).inner_text().split('运行 ID：')[-1].strip()
        if args.only_comparison:
            selections = page.get_by_test_id('stMultiSelect').inner_text()
            page.get_by_role('button',name='生成 V2 比较报告',exact=True).click()
            expect(page.get_by_role('button',name='下载 V2 比较报告',exact=True)).to_be_visible(timeout=30000)
            assert page.get_by_text('拒绝产生优劣结论',exact=False).count() == 0
            capture('comparison-after-integrity-fix')
            report={'case':'comparison_page_after_integrity_fix','status':'pass','selections':selections,'pageerrors':errors}
            assert not errors,errors
            (args.evidence/'comparison-regression.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            context.close();browser.close();print(json.dumps(report,ensure_ascii=False));return
        start.click();view=frame()
        expect(page.get_by_test_id('stMetricValue').first).to_have_text('成功',timeout=45000)
        expect(start).to_be_enabled();run_id=active_run()
        root=Path('data/v2_runs')/run_id
        if args.only_context_loss:
            seek(view, 6500)
            before = view.locator('#physical-root').get_attribute('data-object-position')
            view.locator('canvas').evaluate("canvas=>{const gl=canvas.getContext('webgl2');const extension=gl?.getExtension('WEBGL_lose_context');if(!extension)throw Error('context loss extension unavailable');extension.loseContext();}")
            expect(view.locator('#fallback-notice')).to_contain_text('WebGL 上下文丢失')
            expect(view.locator('#panda-svg')).to_be_visible()
            assert view.locator('#physical-root').get_attribute('data-object-position') == before
            assert float(view.locator('#physical-root').get_attribute('data-time-ms')) == 6500
            view.get_by_role('button',name='播放',exact=True).click();page.wait_for_timeout(350)
            view.get_by_role('button',name='暂停',exact=True).click()
            assert float(view.locator('#physical-root').get_attribute('data-time-ms')) > 6500
            capture('webgl-context-lost')
            assert not errors, errors
            report = {'case':'actual_webgl_context_loss','status':'pass','run_id':run_id,'pageerrors':errors}
            (args.evidence/'context-loss.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            context.close();browser.close();print(json.dumps(report));return
        raw=[json.loads(line) for line in (root/'trajectory.jsonl').read_text().splitlines()]
        scene=json.loads((root/'scene.json').read_text())
        transform=np.array([[1,0,0],[0,0,1],[0,-1,0]])
        max_position,max_angle=0.,0.
        for ms in [0,3400,4200,6500,10500,14000]:
            seek(view,ms)
            debug=view.locator('#physical-root').evaluate('()=>window.__ROBOT_DEBUG__()')
            selected=next(f for f in raw if f['sim_time_ms']==debug['sample_time_ms'])
            expected=next((f for f in reversed(raw) if f['sim_time_ms']<=ms),raw[0])
            assert selected['sim_time_ms']==expected['sim_time_ms']
            assert debug['mesh_count']==len(scene['geoms'])
            actual={str(g['id']):g for g in debug['geoms']}
            for geom,pose in zip(scene['geoms'],selected['geom_poses']):
                rendered=actual[str(geom['id'])]
                error=np.linalg.norm(np.array(rendered['position'])-transform@pose['position'])
                q=rendered['quaternion']
                angle=np.arccos(np.clip((np.trace((transform@rotation(pose['quaternion'])).T@rotation([q[3],*q[:3]]))-1)/2,-1,1))
                max_position,max_angle=max(max_position,float(error)),max(max_angle,float(angle))
            capture(f'baseline-{ms}')
        assert max_position<=1e-4,max_position
        assert max_angle<=1e-3,max_angle
        results.append({'case':'actual_mesh_poses','run_id':run_id,'status':'pass','max_position_error_m':max_position,'max_rotation_error_rad':max_angle})
        print('actual mesh poses passed',flush=True)
        seek(view,0);view.get_by_role('button',name='播放',exact=True).click();page.wait_for_timeout(1500)
        view.get_by_role('button',name='暂停',exact=True).click()
        paused=float(view.locator('#physical-root').get_attribute('data-time-ms'));assert paused>900
        page.wait_for_timeout(1000)
        assert float(view.locator('#physical-root').get_attribute('data-time-ms'))==paused
        view.get_by_role('button',name='播放',exact=True).click();page.wait_for_timeout(350)
        view.get_by_role('button',name='暂停',exact=True).click()
        assert float(view.locator('#physical-root').get_attribute('data-time-ms'))>paused
        seek(view,6500);before=view.locator('#physical-root').get_attribute('data-object-position')
        view.locator('#panda-view').select_option('svg')
        assert view.locator('#physical-root').get_attribute('data-object-position')==before
        expect(view.locator('#panda-svg')).to_be_visible();capture('baseline-svg')
        view.locator('#panda-view').select_option('threejs')
        assert float(view.locator('#physical-root').get_attribute('data-time-ms'))==6500
        view.locator('#speed').select_option('2');seek(view,0)
        view.get_by_role('button',name='播放',exact=True).click()
        intervals=view.locator('#physical-root').evaluate('''()=>new Promise(resolve=>{const a=[];let last=performance.now();function sample(now){a.push(now-last);last=now;if(a.length>=90)resolve(a);else requestAnimationFrame(sample)}requestAnimationFrame(sample)})''')
        view.get_by_role('button',name='暂停',exact=True).click()
        assert float(view.locator('#physical-root').get_attribute('data-time-ms'))>1000
        results.append({'case':'playback_and_views','status':'pass','raf_interval_median_ms':float(np.median(intervals)),'raf_interval_p95_ms':float(np.percentile(intervals,95))})
        print('playback controls passed',flush=True)
        select('策略参数版本','受控偏移策略（grasp_offset=0.08）');start.click()
        expect(page.get_by_test_id('stMetricValue').first).to_have_text('失败',timeout=45000)
        view=frame();seek(view,6500)
        pos=json.loads(view.locator('#physical-root').get_attribute('data-object-position'))
        assert abs(pos[0]-.45)<.02 and pos[2]<.05
        view.locator('#panda-events').select_option(view.locator('#panda-events option').last.get_attribute('value'))
        capture('offset-failure');results.append({'case':'offset_failure_and_events','run_id':active_run(),'status':'pass'})
        page.get_by_role('button',name='生成 V2 比较报告',exact=True).click()
        expect(page.get_by_role('button',name='下载 V2 比较报告',exact=True)).to_be_visible()
        expect(page.get_by_text('固定初始条件下的运行比较；重复次数不代表场景覆盖或生产稳定性。',exact=True)).to_be_visible()
        results.append({'case':'page_comparison_report','status':'pass'})
        loaded_memory=memory()
        if not args.skip_faults:
            page.get_by_text('本地验收诊断（非策略评测）',exact=True).click()
            for fault in ['crash','timeout']:
                select('故障注入',fault)
                previous_run = active_run()
                start.click()
                # Streamlit 重跑期间旧错误 DOM 可能短暂存在，必须等新 run 的终态再断言。
                expect(page.get_by_text('执行状态：',exact=False)).not_to_contain_text(previous_run, timeout=45000)
                expect(page.get_by_text('执行异常：',exact=False)).to_be_visible(timeout=45000)
                expect(start).to_be_enabled();error=page.get_by_text('执行异常：',exact=False).inner_text()
                assert ('timeout' in error) if fault=='timeout' else ('worker_exception' in error or 'worker_crash' in error)
                fault_directory = Path('data/v2_runs')/active_run()
                assert json.loads((fault_directory/'config.json').read_text())['fault_mode'] == fault
                if fault == 'crash':
                    assert 'injected Panda worker crash' in (fault_directory/'error.log').read_text(encoding='utf-8')
                capture(f'fault-{fault}');results.append({'case':f'page_{fault}','status':'pass','message':error})
            select('故障注入','none');select('策略参数版本','基线策略（grasp_offset=0.00）');start.click()
            expect(page.get_by_test_id('stMetricValue').first).to_have_text('成功',timeout=45000)
            view=frame();results.append({'case':'restart_after_fault','status':'pass','run_id':active_run()})
        assert not errors,errors
        context.close()
        context=browser.new_context(viewport={'width':1440,'height':1100})
        context.add_init_script("const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...args){if(String(type).includes('webgl'))return null;return original.call(this,type,...args);};")
        page=context.new_page();page.goto(args.url);page.get_by_text('V2 物理仿真',exact=True).click()
        page.get_by_role('button',name='启动 V2 物理仿真',exact=True).click();view=frame()
        expect(view.locator('#panda-svg')).to_be_visible()
        view.get_by_role('button',name='播放',exact=True).click();page.wait_for_timeout(350)
        view.get_by_role('button',name='暂停',exact=True).click()
        assert float(view.locator('#physical-root').get_attribute('data-time-ms'))>0
        capture('webgl-fallback');results.append({'case':'panda_webgl_fallback','status':'pass'})
        context.close();browser.close();time.sleep(.2)
        remaining=[pid for pid in browser_pids if psutil.pid_exists(pid)]
        assert not remaining,remaining
    report={'checks':results,'pageerrors':errors,'browser_memory':{'initial_rss_sum':initial_memory,'loaded_rss_sum':loaded_memory,'increment_bytes':loaded_memory-initial_memory,'scope':'sum of dedicated Chromium process RSS; shared pages may be counted multiple times'},'browser_processes_reaped':True}
    (args.evidence/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    main()
