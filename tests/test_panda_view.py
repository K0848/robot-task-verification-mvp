"""报告与回放失败隔离：无效数据不让整个页面异常。"""
from pathlib import Path
import json
import tempfile
import unittest

from streamlit.testing.v1 import AppTest
from robot_mvp.panda_runner import run_panda
from robot_mvp.v2_physics import SimulationConfig


class PandaViewTests(unittest.TestCase):
    def test_malformed_report_structure_is_explicit_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = {'run_id':'bad-report','success':True,'final_status':'succeeded','duration_ms':10,
                      'failure':None,'success_criteria':{}}
            (root/'summary.json').write_text(json.dumps(report))
            app = AppTest.from_string("from pathlib import Path\nfrom robot_mvp.v2_view import render_evidence\nrender_evidence(Path(" + repr(str(root)) + "))")
            app.run(timeout=10)
            self.assertFalse(app.exception)
            self.assertTrue(any('报告不完整' in e.value for e in app.error))
            self.assertFalse(app.metric)

    def test_corrupt_scene_keeps_report_readable_without_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = SimulationConfig(run_id="view-test", model_id="panda-cube-v1", max_steps=7000,
                                      initial_object_x=.45, target_x=.45)
            run_panda(config, root, lambda status: None)
            (root / "scene.json").write_text("{}")
            app = AppTest.from_string("from pathlib import Path\nfrom robot_mvp.v2_view import render_evidence\nrender_evidence(Path(" + repr(str(root)) + "))")
            app.run(timeout=20)
            self.assertFalse(app.exception)
            self.assertTrue(any("无法回放" in error.value for error in app.error))
            self.assertTrue(any("运行结论" in title.value for title in app.subheader))
            self.assertEqual(app.metric[2].value, "不可验证")


if __name__ == "__main__":
    unittest.main()
