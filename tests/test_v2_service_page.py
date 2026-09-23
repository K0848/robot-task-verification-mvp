"""现有页面只改业务接线，用实际worker检验参数/结果/建议比较，不评视觉改版。"""
import json
from pathlib import Path
import tempfile
import time
import unittest

from streamlit.testing.v1 import AppTest
from robot_mvp.v2_service import V2RunService


class V2ServicePageTests(unittest.TestCase):
    def test_page_uses_service_presets_and_distinct_default_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'runs'
            source=("from pathlib import Path\nimport app\nfrom robot_mvp.v2_service import V2RunService\n"
                    f"app.V2_SERVICE=V2RunService(Path({str(root)!r}))\napp.render_v2_simulation()")
            app=AppTest.from_string(source).run(timeout=20)
            def button(label):
                return next(item for item in app.button if item.label==label)
            def finish(outcome):
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    app.run(timeout=20)
                    self.assertFalse(app.exception)
                    if app.metric and app.metric[0].value==outcome:return
                    time.sleep(.05)
                self.fail('页面未收敛到预期终态')
            button('开始验证').click().run(timeout=20)
            finish('成功')
            app.selectbox(key='v2-strategy').set_value('offset-grasp').run(timeout=20)
            button('开始验证').click().run(timeout=20)
            finish('失败')
            service=V2RunService(root)
            pair=app.multiselect(key='v2-compare-panda-cube-v1').value
            self.assertEqual(len(pair),2)
            self.assertEqual({service.get_run(run_id)['parameters']['grasp_offset'] for run_id in pair},{0.,.08})
            button('生成比较').click().run(timeout=20)
            self.assertFalse(app.exception)
            reports=[json.loads(item.value) if isinstance(item.value,str) else item.value for item in app.json]
            comparison=next(item for item in reports if 'comparison_kind' in item)
            self.assertEqual(comparison['comparison_kind'],'controlled_parameter_comparison')
            # 新会话没有上次JobHandle，但同一后端历史仍能提供建议对比。
            fresh=AppTest.from_string(source).run(timeout=20)
            self.assertFalse(fresh.exception)
            self.assertEqual(set(fresh.multiselect(key='v2-compare-panda-cube-v1').value),set(pair))


if __name__=='__main__':unittest.main()
