"""前端主流程与历史边界：真实隔离记录、空状态、分页及导航。"""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from streamlit.testing.v1 import AppTest
from robot_mvp.v2_runtime import V2JobManager, new_config


class WorkspaceUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=tempfile.TemporaryDirectory()
        manager=V2JobManager(Path(cls.fixture.name))
        cls.run_ids=[]
        for strategy,offset in [('baseline',0.),('offset-grasp',.08)]:
            handle=manager.start(new_config(model_id='panda-cube-v1',strategy_id=strategy,grasp_offset=offset))
            manager.wait(handle,timeout_s=30)
            cls.run_ids.append(handle.run_id)

    @classmethod
    def tearDownClass(cls):cls.fixture.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)/'runs'
        shutil.copytree(self.fixture.name,self.root)

    def tearDown(self):self.temp.cleanup()

    def application(self, *, empty=False, forbid_v1=False):
        root=Path(self.temp.name)/'empty' if empty else self.root
        setup=("import app\nfrom pathlib import Path\nfrom robot_mvp.v2_service import V2RunService\n"
               f"app.V2_SERVICE=V2RunService(Path({str(root)!r}))\n")
        if forbid_v1:
            setup+="from unittest.mock import Mock\napp.STORE=Mock()\napp.STORE.load.side_effect=AssertionError('主入口不应读取V1')\n"
        else:
            setup+=f"from robot_mvp.storage import JsonStore\napp.STORE=JsonStore(Path({str(Path(self.temp.name)/'v1.json')!r}))\n"
        return AppTest.from_string(setup+'app.main()').run(timeout=30)

    def test_default_workspace_is_not_v1_dashboard(self):
        app=self.application(empty=True,forbid_v1=True)
        self.assertFalse(app.exception)
        self.assertEqual(app.radio(key='rf-page').value,'验证工作台')
        self.assertFalse(app.metric)
        self.assertFalse(any(item.label in {'仿真模型','当前角色视角','演示预设'} for item in app.selectbox))
        self.assertFalse(any(item.label=='清除当前运行引用' for item in app.button))
        self.assertTrue(any(item.label=='开始验证' for item in app.button))

    def test_history_opens_real_record_in_workspace(self):
        app=self.application(forbid_v1=True)
        app.radio(key='rf-page').set_value('运行记录').run(timeout=30)
        self.assertFalse(app.exception)
        app.button(key=f'rf-open-{self.run_ids[1]}').click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(app.radio(key='rf-page').value,'验证工作台')
        self.assertEqual(app.metric[0].value,'失败')

    def test_history_filter_and_empty_state(self):
        app=self.application()
        app.radio(key='rf-page').set_value('运行记录').run(timeout=30)
        app.selectbox(key='rf-history-status').set_value('执行中').run(timeout=30)
        self.assertFalse(app.exception)
        self.assertTrue(any('没有运行记录' in item.value for item in app.info))
        app.selectbox(key='rf-history-status').set_value('失败（含执行异常）').run(timeout=30)
        self.assertEqual(len([item for item in app.button if item.label=='查看']),1)

    def test_history_paginates_without_changing_records(self):
        manager=V2JobManager(self.root)
        for index in range(12):
            manager.artifacts.create(new_config(run_id=f'queued-{index}',model_id='panda-cube-v1'))
        app=self.application()
        app.radio(key='rf-page').set_value('运行记录').run(timeout=30)
        self.assertEqual(len([item for item in app.button if item.label=='查看']),10)
        next(item for item in app.button if item.label=='下一页').click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(len([item for item in app.button if item.label=='查看']),4)
        self.assertTrue(next(item for item in app.button if item.label=='下一页').disabled)

    def test_corrupt_record_visible_and_not_rendered_as_valid(self):
        (self.root/self.run_ids[1]/'summary.json').write_text('{',encoding='utf-8')
        app=self.application()
        app.radio(key='rf-page').set_value('运行记录').run(timeout=30)
        self.assertTrue(any('记录异常' in item.value for item in app.markdown))
        app.button(key=f'rf-open-{self.run_ids[1]}').click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertTrue(any('无法通过核验' in item.value for item in app.error))

    def test_legacy_is_explicit_and_returnable(self):
        app=self.application(empty=True)
        app.button(key='rf-open-legacy').click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertTrue(any('历史区域' in item.value for item in app.warning))
        next(item for item in app.button if item.label=='返回主工作区').click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value,'验证工作台')


if __name__=='__main__':unittest.main()
