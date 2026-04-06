from __future__ import annotations

import unittest
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from robot_mvp.simulator import (
    benchmark_runs_for_batch,
    build_comparison_summary,
    build_renderer_payload,
    compute_display_elapsed_ms,
    create_live_run_bundle,
    create_preview_bundle,
    extract_dynamic_profile,
    interpolate_replay_frame,
    iter_run_assets,
    make_seed_reference,
    parse_dt,
    parse_operator_note_dynamic_profile,
    project_run_view,
    resolve_focus_anchor_frame,
    seed_store_data,
    summarize_benchmark_batch,
    sync_run_statuses,
    sync_store_defaults,
)
from robot_mvp.models import ReplayFrame
from robot_mvp.storage import JsonStore

TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / '.tmp-tests'
TEST_TMP_ROOT.mkdir(exist_ok=True)


def make_store() -> tuple[JsonStore, Path]:
    store_path = TEST_TMP_ROOT / f'store-{uuid4().hex}.json'
    if store_path.exists():
        store_path.unlink()
    return JsonStore(store_path), store_path


class SimulatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reference = make_seed_reference()
        self.data = seed_store_data(self.reference)
        self.task = self.data.task_templates[0]
        self.strategy = self.data.strategy_versions[0]

    def test_seed_data_covers_core_objects(self) -> None:
        self.assertEqual(len(self.data.task_templates), 1)
        self.assertGreaterEqual(len(self.data.strategy_versions), 3)
        self.assertGreaterEqual(len(self.data.benchmark_suites), 2)
        self.assertGreaterEqual(len(self.data.run_records), 10)

    def test_every_run_has_events_and_frames(self) -> None:
        for run in self.data.run_records:
            current, events, frames = iter_run_assets(self.data, run.id)
            self.assertIsNotNone(current)
            self.assertGreaterEqual(len(events), 4)
            self.assertGreaterEqual(len(frames), 6)
            self.assertEqual(sorted(event.offset_ms for event in events), [event.offset_ms for event in events])
            self.assertEqual(sorted(frame.offset_ms for frame in frames), [frame.offset_ms for frame in frames])

    def test_project_run_view_completes_live_run(self) -> None:
        run, events, frames = create_live_run_bundle(
            task_template=self.task,
            strategy=self.strategy,
            preset_key='grasp_slip',
            operator_note='smoke test',
        )
        future = parse_dt(run.ended_at) + timedelta(seconds=1)
        completed = project_run_view(run, events, frames, now=future)
        self.assertTrue(completed.completed)
        self.assertEqual(completed.run_record.status, 'failed')
        self.assertEqual(completed.visible_events[-1].stage, '任务失败')

    def test_comparison_summary_prefers_successful_run(self) -> None:
        success_run = next(run for run in self.data.run_records if run.result.success)
        failure_run = next(run for run in self.data.run_records if not run.result.success)
        _, success_events, _ = iter_run_assets(self.data, success_run.id)
        _, failure_events, _ = iter_run_assets(self.data, failure_run.id)
        summary = build_comparison_summary(success_run, failure_run, success_events, failure_events)
        self.assertEqual(summary.recommended_run_id, success_run.id)
        self.assertIn('成功', summary.success_diff)

    def test_operator_note_keyword_protocol_maps_to_dynamic_profile(self) -> None:
        profile = parse_operator_note_dynamic_profile('面试演示用，快节奏，强调抓取')
        self.assertEqual(profile['pace'], 'fast')
        self.assertEqual(profile['focus'], 'grasp')
        self.assertAlmostEqual(profile['pace_multiplier'], 1.35)
        self.assertEqual(profile['matched_keywords'], ['快节奏', '强调抓取'])

    def test_interpolate_replay_frame_clamps_and_blends(self) -> None:
        success_run = next(run for run in self.data.run_records if run.result.success)
        _, _, frames = iter_run_assets(self.data, success_run.id)
        first = interpolate_replay_frame(frames, -100)
        mid = interpolate_replay_frame(frames, (frames[2].offset_ms + frames[3].offset_ms) / 2)
        last = interpolate_replay_frame(frames, frames[-1].offset_ms + 999)

        self.assertIsNotNone(first)
        self.assertIsNotNone(mid)
        self.assertIsNotNone(last)
        self.assertEqual(first.offset_ms, frames[0].offset_ms)
        self.assertEqual(last.offset_ms, frames[-1].offset_ms)
        self.assertGreater(mid.arm_pose['x'], frames[2].arm_pose['x'])
        self.assertLess(mid.arm_pose['x'], frames[3].arm_pose['x'])

    def test_interpolate_replay_frame_keeps_object_at_pickup_before_grasp(self) -> None:
        frames = [
            ReplayFrame(
                run_id='demo',
                timestamp='2026-04-05T10:00:00',
                arm_pose={'x': 10, 'y': 20, 'z': 5},
                gripper_state='open',
                target_state={
                    'object_label': '连接法兰',
                    'target_slot': 'Tray-01',
                    'object_x': 12,
                    'object_y': 15,
                    'pickup_x': 12,
                    'pickup_y': 15,
                    'dropoff_x': 70,
                    'dropoff_y': 40,
                    'held': False,
                    'placed': False,
                },
                offset_ms=0,
                stage='接近目标',
            ),
            ReplayFrame(
                run_id='demo',
                timestamp='2026-04-05T10:00:01',
                arm_pose={'x': 20, 'y': 40, 'z': 10},
                gripper_state='closed',
                target_state={
                    'object_label': '连接法兰',
                    'target_slot': 'Tray-01',
                    'object_x': 20,
                    'object_y': 40,
                    'pickup_x': 12,
                    'pickup_y': 15,
                    'dropoff_x': 70,
                    'dropoff_y': 40,
                    'held': True,
                    'placed': False,
                },
                offset_ms=1000,
                stage='执行抓取',
            ),
        ]

        early = interpolate_replay_frame(frames, 250)
        late = interpolate_replay_frame(frames, 750)

        self.assertEqual(early.target_state['object_x'], 12.0)
        self.assertEqual(early.target_state['object_y'], 15.0)
        self.assertGreater(late.target_state['object_x'], 12.0)
        self.assertGreater(late.target_state['object_y'], 15.0)

    def test_interpolate_replay_frame_keeps_object_with_gripper_before_release(self) -> None:
        frames = [
            ReplayFrame(
                run_id='demo',
                timestamp='2026-04-05T10:00:00',
                arm_pose={'x': 20, 'y': 40, 'z': 10},
                gripper_state='closed',
                target_state={
                    'object_label': '连接法兰',
                    'target_slot': 'Tray-01',
                    'object_x': 20,
                    'object_y': 40,
                    'pickup_x': 12,
                    'pickup_y': 15,
                    'dropoff_x': 70,
                    'dropoff_y': 40,
                    'held': True,
                    'placed': False,
                },
                offset_ms=0,
                stage='接近托盘',
            ),
            ReplayFrame(
                run_id='demo',
                timestamp='2026-04-05T10:00:01',
                arm_pose={'x': 70, 'y': 40, 'z': 10},
                gripper_state='open',
                target_state={
                    'object_label': '连接法兰',
                    'target_slot': 'Tray-01',
                    'object_x': 70,
                    'object_y': 40,
                    'pickup_x': 12,
                    'pickup_y': 15,
                    'dropoff_x': 70,
                    'dropoff_y': 40,
                    'held': False,
                    'placed': True,
                },
                offset_ms=1000,
                stage='放置校验',
            ),
        ]

        early = interpolate_replay_frame(frames, 250)
        late = interpolate_replay_frame(frames, 750)

        self.assertEqual(early.target_state['object_x'], 20.0)
        self.assertEqual(early.target_state['object_y'], 40.0)
        self.assertGreater(late.target_state['object_x'], 20.0)

    def test_live_run_persists_dynamic_profile_without_changing_result_logic(self) -> None:
        run, events, _ = create_live_run_bundle(
            task_template=self.task,
            strategy=self.strategy,
            preset_key='grasp_slip',
            operator_note='快节奏 强调失败 smoke test',
        )
        profile = extract_dynamic_profile(run)
        display_elapsed = compute_display_elapsed_ms(10_000, run.duration_ms, profile)

        self.assertEqual(run.input_params['requested_preset'], 'grasp_slip')
        self.assertEqual(run.input_params['resolved_scenario'], 'grasp_slip')
        self.assertEqual(profile['pace'], 'fast')
        self.assertEqual(profile['focus'], 'failure')
        self.assertEqual(run.result.final_status, 'failed')
        self.assertEqual([event.offset_ms for event in events], sorted(event.offset_ms for event in events))
        self.assertGreater(display_elapsed, 10_000)

    def test_preview_bundle_uses_same_resolved_scenario_and_focus_fallback(self) -> None:
        strategy = next(item for item in self.data.strategy_versions if item.id == 'stable-policy')
        run, _, frames = create_preview_bundle(
            task_template=self.task,
            strategy=strategy,
            preset_key='auto',
            operator_note='慢速讲解 强调失败',
            reference_time=self.reference,
        )
        anchor = resolve_focus_anchor_frame(
            frames,
            extract_dynamic_profile(run)['focus'],
            success=run.result.success,
        )
        self.assertEqual(run.input_params['resolved_scenario'], 'success')
        self.assertEqual(anchor.stage, '执行抓取')

    def test_strategy_default_pace_is_applied_without_note_keywords(self) -> None:
        fast_strategy = next(item for item in self.data.strategy_versions if item.id == 'fast-motion')
        stable_strategy = next(item for item in self.data.strategy_versions if item.id == 'stable-policy')

        fast_run, _, _ = create_preview_bundle(
            task_template=self.task,
            strategy=fast_strategy,
            preset_key='success',
            operator_note='',
            reference_time=self.reference,
            resolved_scenario='success',
        )
        stable_run, _, _ = create_preview_bundle(
            task_template=self.task,
            strategy=stable_strategy,
            preset_key='success',
            operator_note='',
            reference_time=self.reference,
            resolved_scenario='success',
        )

        self.assertEqual(extract_dynamic_profile(fast_run)['pace'], 'fast')
        self.assertEqual(extract_dynamic_profile(stable_run)['pace'], 'slow')

    def test_operator_note_can_override_strategy_default_pace(self) -> None:
        strategy = next(item for item in self.data.strategy_versions if item.id == 'stable-policy')
        run, _, _ = create_preview_bundle(
            task_template=self.task,
            strategy=strategy,
            preset_key='success',
            operator_note='快节奏',
            reference_time=self.reference,
            resolved_scenario='success',
        )

        profile = extract_dynamic_profile(run)
        self.assertEqual(profile['pace'], 'fast')
        self.assertAlmostEqual(profile['pace_multiplier'], 1.35)
        self.assertEqual(profile['matched_keywords'], ['快节奏'])

    def test_sync_store_defaults_migrates_existing_strategy_names(self) -> None:
        self.data.strategy_versions[0].name = 'Baseline Heuristic'
        self.data.strategy_versions[1].name = 'Stable Policy'
        self.data.strategy_versions[2].name = 'Fast Motion'

        changed = sync_store_defaults(self.data)

        self.assertTrue(changed)
        name_map = {item.id: item.name for item in self.data.strategy_versions}
        self.assertEqual(name_map['heuristic-baseline'], '规则阈值基线策略')
        self.assertEqual(name_map['stable-policy'], '稳定抓取补偿策略')
        self.assertEqual(name_map['fast-motion'], '高速节拍转运策略')

    def test_sync_run_statuses_honors_runtime_override(self) -> None:
        run, _, _ = create_live_run_bundle(
            task_template=self.task,
            strategy=self.strategy,
            preset_key='success',
            operator_note='pause smoke test',
        )
        self.data.run_records = [run]
        override_now = parse_dt(run.started_at) + timedelta(milliseconds=run.duration_ms // 2)
        future_now = parse_dt(run.ended_at) + timedelta(seconds=5)

        changed = sync_run_statuses(
            self.data,
            current=future_now,
            runtime_overrides={run.id: override_now},
        )

        self.assertFalse(changed)
        self.assertEqual(self.data.run_records[0].status, 'running')

    def test_renderer_payload_covers_required_runtime_fields(self) -> None:
        run = next(item for item in self.data.run_records if item.result.success)
        _, events, frames = iter_run_assets(self.data, run.id)
        payload = build_renderer_payload(
            run,
            events,
            frames,
            'detail',
            initial_elapsed_ms=12_000,
            progress=0.42,
            current_stage='执行抓取',
            title='实时任务状态',
        )
        self.assertEqual(payload['view_mode'], 'detail')
        self.assertEqual(payload['highlight_mode'], extract_dynamic_profile(run)['focus'])
        self.assertIn('object_label', payload['scene'])
        self.assertEqual(payload['animation']['mode'], 'live')
        self.assertGreaterEqual(len(payload['frames']), 1)
        self.assertGreaterEqual(len(payload['events']), 1)

    def test_benchmark_summary_prefers_stable_policy_for_core_suite(self) -> None:
        store, store_path = make_store()
        try:
            data = store.load()
            suite = next(item for item in data.benchmark_suites if item.id == 'embodied-core-v1')
            strategy = next(item for item in data.strategy_versions if item.id == 'stable-policy')
            batch_id = store.create_benchmark_batch(
                task_template_id=data.task_templates[0].id,
                strategy_version_id=strategy.id,
                suite_id=suite.id,
                operator_note='benchmark smoke',
            )
            data = store.load()
            batch = next(item for item in data.benchmark_batches if item.id == batch_id)
            runs = benchmark_runs_for_batch(data, batch)
            summary = summarize_benchmark_batch(batch, suite, runs)
            self.assertEqual(summary['success_count'], summary['total_cases'])
            self.assertGreaterEqual(summary['success_rate'], 0.99)
            self.assertIn('默认', summary['recommendation'])
        finally:
            if store_path.exists():
                store_path.unlink()


class StorageTests(unittest.TestCase):
    def test_store_bootstrap_and_live_run_creation(self) -> None:
        store, store_path = make_store()
        try:
            data = store.load()
            self.assertGreaterEqual(len(data.run_records), 10)

            run_id = store.create_live_run(
                task_template_id=data.task_templates[0].id,
                strategy_version_id=data.strategy_versions[1].id,
                preset_key='success',
                operator_note='integration',
            )
            run, events, frames = store.get_run_bundle(run_id)
            self.assertIsNotNone(run)
            self.assertEqual(run.id, run_id)
            self.assertGreater(len(events), 0)
            self.assertGreater(len(frames), 0)
            self.assertIn('dynamic_profile', run.input_params)
            self.assertEqual(run.input_params['resolved_scenario'], 'success')

            batch_id = store.create_benchmark_batch(
                task_template_id=data.task_templates[0].id,
                strategy_version_id=data.strategy_versions[1].id,
                suite_id=data.benchmark_suites[0].id,
                operator_note='batch integration',
            )
            data = store.load()
            batch = next(item for item in data.benchmark_batches if item.id == batch_id)
            self.assertEqual(batch.id, batch_id)
            self.assertGreater(len(batch.run_ids), 0)
            benchmark_runs = benchmark_runs_for_batch(data, batch)
            self.assertEqual(len(benchmark_runs), len(batch.run_ids))
            self.assertTrue(all('benchmark-generated' in item.tags for item in benchmark_runs))
        finally:
            if store_path.exists():
                store_path.unlink()


if __name__ == '__main__':
    unittest.main()
