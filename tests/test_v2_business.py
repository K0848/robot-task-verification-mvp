"""业务查询用真实隔离产物，不能依赖开发机历史目录或页面会话。"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from robot_mvp.v2_runtime import V2JobManager, new_config, build_comparison_report
from robot_mvp.v2_service import V2RunService


class V2BusinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        manager = V2JobManager(Path(cls.fixture.name))
        cls.ids = []
        for values in [dict(model_id='panda-cube-v1',strategy_id='baseline'),
                       dict(model_id='panda-cube-v1',strategy_id='offset-grasp',grasp_offset=.08),
                       dict(strategy_id='baseline')]:
            handle = manager.start(new_config(**values))
            manager.wait(handle, timeout_s=30)
            cls.ids.append(handle.run_id)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)/'runs'
        shutil.copytree(self.fixture.name,self.root)
        self.service = V2RunService(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def change(self,run_id,file,**values):
        path=self.root/run_id/file
        data=json.loads(path.read_text(encoding='utf-8'));data.update(values)
        path.write_text(json.dumps(data),encoding='utf-8')

    def make_record(self,run_id,status,**extra):
        directory=self.service.manager.artifacts.create(new_config(run_id=run_id,model_id='panda-cube-v1',**extra))
        self.service.manager.artifacts.update_status(run_id,status=status,error_code='worker_exception' if status=='failed' else None)
        return directory

    def test_default_catalog_is_panda_and_pagination_is_stable(self):
        page=self.service.list_runs(limit=1)
        self.assertEqual(page['total'],2)
        self.assertEqual(len(page['items']),1)
        self.assertTrue(page['has_more'])
        next_page=self.service.list_runs(limit=1,offset=1)
        self.assertNotEqual(page['items'][0]['run_id'],next_page['items'][0]['run_id'])
        self.assertEqual(self.service.list_runs(model_id='minimal_planar_pick_place')['total'],1)

    def test_detail_and_replay_do_not_need_live_handle(self):
        fresh=V2RunService(self.root)
        detail=fresh.get_run(self.ids[0])
        self.assertEqual(detail['integrity'],'verified')
        self.assertTrue(detail['task_success'])
        self.assertEqual(fresh.replay_payload(self.ids[0])['model_id'],'panda-cube-v1')

    def test_pending_and_execution_error_not_silently_dropped(self):
        self.make_record('pending','running')
        self.make_record('crashed','failed')
        items={item['run_id']:item for item in self.service.list_runs()['items']}
        self.assertIn('pending',items);self.assertIn('crashed',items)
        self.assertIsNone(items['crashed']['task_success'])
        self.assertFalse(items['crashed']['report_available'])
        self.assertEqual(items['pending']['integrity'],'pending')

    def test_diagnostic_runs_are_explicitly_excluded(self):
        self.make_record('fault-diagnostic','failed',fault_mode='crash')
        self.assertEqual(self.service.list_runs()['total'],2)
        self.assertEqual(self.service.list_runs(include_diagnostics=True)['total'],3)

    def test_corrupt_record_stays_visible_with_reason(self):
        (self.root/self.ids[0]/'summary.json').write_text('{')
        record=next(r for r in self.service.list_runs()['items'] if r['run_id']==self.ids[0])
        self.assertEqual(record['integrity'],'invalid')
        self.assertTrue(record['issues'])
        self.assertIsNone(record['task_success'])

    def test_overview_excludes_invalid_and_unknown_from_result_rate(self):
        self.make_record('crashed','failed')
        totals=self.service.overview()
        self.assertEqual(totals['verified_result_count'],2)
        self.assertEqual(totals['task_success_rate'],.5)
        self.assertEqual(totals['unknown_outcome_count'],1)
        (self.root/self.ids[0]/'scene.json').write_text('{}')
        totals=self.service.overview()
        self.assertEqual(totals['invalid_count'],1)
        self.assertEqual(totals['verified_result_count'],1)
        self.assertEqual(totals['task_success_rate'],0.)

    def test_no_valid_results_means_unknown_not_zero_percent(self):
        empty=V2RunService(Path(self.temporary.name)/'empty')
        self.assertIsNone(empty.overview()['task_success_rate'])
        self.assertEqual(empty.suggest_comparison()['run_ids'],[])

    def test_default_pair_uses_two_actual_parameter_sets(self):
        suggested=self.service.suggest_comparison()
        self.assertEqual(set(suggested['run_ids']),set(self.ids[:2]))
        report=self.service.compare(suggested['run_ids'])
        self.assertEqual(report['comparison_kind'],'controlled_parameter_comparison')

    def test_corrupt_evidence_is_not_a_default_candidate(self):
        (self.root/self.ids[1]/'events.jsonl').write_text('not json')
        self.assertEqual(self.service.suggest_comparison()['run_ids'],[])

    def test_duplicate_run_and_cross_model_are_rejected(self):
        self.assertEqual(self.service.compare([self.ids[0],self.ids[0]])['comparison_status'],'rejected')
        self.assertEqual(self.service.compare([self.ids[0],self.ids[2]])['comparison_status'],'rejected')

    def test_same_name_different_params_remain_distinct_groups(self):
        meta_path=self.root/self.ids[1]/'meta.json'
        meta=json.loads(meta_path.read_text(encoding='utf-8'));meta['config']['strategy_id']='baseline'
        meta_path.write_text(json.dumps(meta),encoding='utf-8')
        self.change(self.ids[1],'config.json',strategy_id='baseline')
        report=self.service.compare(self.ids[:2])
        self.assertEqual(report['comparison_kind'],'controlled_parameter_comparison')
        self.assertEqual(len(report['parameter_groups']),2)

    def test_same_params_are_repeatability_even_after_three_runs(self):
        original=self.root/self.ids[0]
        for name in ['repeat-a','repeat-b']:
            destination=self.root/name;shutil.copytree(original,destination)
            for file in ['config.json','status.json','meta.json','summary.json']:
                value=json.loads((destination/file).read_text(encoding='utf-8'));value['run_id']=name
                if file=='meta.json':value['config']['run_id']=name
                (destination/file).write_text(json.dumps(value),encoding='utf-8')
            for file in ['trajectory.jsonl','events.jsonl']:
                values=[dict(json.loads(line),run_id=name) for line in (destination/file).read_text(encoding='utf-8').splitlines()]
                (destination/file).write_text('\n'.join(json.dumps(v) for v in values),encoding='utf-8')
        report=self.service.compare([self.ids[0],'repeat-a','repeat-b'])
        self.assertEqual(report['comparison_kind'],'repeatability_check')
        self.assertEqual(report['evidence_status'],'evidence_insufficient')
        self.assertFalse(report['generalization_supported'])

    def test_unsafe_ids_and_invalid_filters_do_not_read_outside_root(self):
        for bad in ['../store','C:/tmp','folder/run']:
            with self.assertRaises(ValueError):self.service.get_run(bad)
        for values in [dict(limit=0),dict(offset=-1),dict(model_id='unknown'),dict(status='banana')]:
            with self.assertRaises(ValueError):self.service.list_runs(**values)

    def test_cli_queries_use_same_service_contract(self):
        for command, expected in [(['list','--limit','1'],'items'),(['show',self.ids[0]],'integrity'),(['overview'],'verified_result_count')]:
            result=subprocess.run([sys.executable,'-X','utf8','-m','robot_mvp.v2_cli',*command,'--artifacts',str(self.root)],
                                  capture_output=True,text=True,encoding='utf-8',timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn(expected,json.loads(result.stdout))
        duplicate=self.root/self.ids[0]
        result=subprocess.run([sys.executable,'-X','utf8','-m','robot_mvp.v2_cli','compare',str(duplicate),str(duplicate)],
                              capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(result.returncode,2)
        self.assertEqual(json.loads(result.stdout)['comparison_status'],'rejected')

    def test_invalid_report_shape_is_rejected_consistently(self):
        self.change(self.ids[0],'summary.json',failure=None)
        record=self.service.get_run(self.ids[0])
        self.assertEqual(record['integrity'],'invalid')
        self.assertFalse(record['report_available'])
        self.assertEqual(self.service.compare(self.ids[:2])['comparison_status'],'rejected')

    def test_config_copy_mismatch_is_never_a_verified_run(self):
        self.change(self.ids[0],'config.json',grasp_offset=.2)
        self.assertEqual(self.service.get_run(self.ids[0])['integrity'],'invalid')
        with self.assertRaises(ValueError):self.service.replay_payload(self.ids[0])

    def test_wrong_field_types_become_visible_issues_not_query_crashes(self):
        self.change(self.ids[0],'config.json',model_id=['wrong'])
        self.assertTrue(self.service.list_runs()['issues'])
        self.change(self.ids[1],'status.json',status=['bad'])
        self.assertEqual(self.service.get_run(self.ids[1])['integrity'],'invalid')


if __name__=='__main__':unittest.main()
