from __future__ import annotations

import tempfile
import time
import unittest
from unittest.mock import Mock
from pathlib import Path
import json
import shutil

from robot_mvp.v2_runtime import V2JobManager, build_comparison_report, new_config, validate_config


class PandaRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.manager = V2JobManager(Path(self.temp_dir.name) / "runs")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def assert_reaped(self, handle) -> None:
        self.assertIsNotNone(handle.process.poll())
        for stream in (handle.process.stdout, handle.process.stderr):
            if stream is not None:
                self.assertTrue(stream.closed)

    def test_new_config_has_panda_defaults_without_changing_legacy(self) -> None:
        panda = new_config(model_id="panda-cube-v1")
        legacy = new_config()
        self.assertEqual((panda.max_steps, panda.initial_object_x, panda.target_x), (7000, .45, .45))
        self.assertEqual((legacy.max_steps, legacy.initial_object_x, legacy.target_x), (650, -.28, .28))

    def test_validate_config_rejects_string_bool_and_unsafe_run_id(self) -> None:
        for overrides in (
            {"wall_timeout_s": "1"},
            {"grasp_offset": True},
            {"run_id": "../escape"},
            {"run_id": "C:\\escape"},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    validate_config(new_config(**overrides))

    def test_real_worker_normal_and_failure(self) -> None:
        normal = self.manager.start(new_config(model_id="panda-cube-v1"))
        self.assertEqual(self.manager.wait(normal, timeout_s=30)["status"], "succeeded")
        self.assert_reaped(normal)
        failure = self.manager.start(new_config(model_id="panda-cube-v1", grasp_offset=.08))
        failure_status = self.manager.wait(failure, timeout_s=30)
        self.assertEqual(failure_status["status"], "failed")
        self.assert_reaped(failure)
        self.assertFalse(self.manager.artifacts.read_summary(failure.run_id)["success"])

    def test_poll_enforces_wall_timeout_and_allows_follow_up(self) -> None:
        handle = self.manager.start(new_config(model_id="panda-cube-v1", fault_mode="timeout", wall_timeout_s=.05))
        deadline = time.monotonic() + 5
        status = self.manager.poll(handle)
        while status["status"] not in {"succeeded", "failed", "cancelled"} and time.monotonic() < deadline:
            time.sleep(.03)
            status = self.manager.poll(handle)
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["error_code"], "wall_timeout")
        self.assert_reaped(handle)
        follow_up = self.manager.start(new_config(model_id="panda-cube-v1", max_steps=10))
        self.assertEqual(self.manager.wait(follow_up, timeout_s=30)["status"], "failed")
        self.assert_reaped(follow_up)

    def test_poll_converges_crash_and_missing_terminal_state(self) -> None:
        crash = self.manager.start(new_config(model_id="panda-cube-v1", fault_mode="crash"))
        deadline = time.monotonic() + 5
        status = self.manager.poll(crash)
        while status["status"] not in {"succeeded", "failed", "cancelled"} and time.monotonic() < deadline:
            time.sleep(.03)
            status = self.manager.poll(crash)
        self.assertEqual(status["status"], "failed")
        error_log = crash.artifact_dir / "error.log"
        self.assertTrue(error_log.exists())
        self.assertTrue(error_log.read_text(encoding="utf-8"))
        self.assert_reaped(crash)
        missing = self.manager.start(new_config(model_id="panda-cube-v1", max_steps=10))
        # 模拟一个正常退出码但只留下 running 状态的孤儿 worker，覆盖与崩溃不同的缺失终态分支。
        self.manager._reap(missing)
        missing.process = Mock(poll=lambda: 0, stdout=None, stderr=None)
        self.manager.artifacts.update_status(missing.run_id, status="running")
        status = self.manager.poll(missing)
        self.assertEqual(status["error_code"], "missing_terminal_state")
        self.assert_reaped(missing)

    def test_model_mismatch_rejects_comparison_conclusion(self) -> None:
        left = self.manager.start(new_config(model_id="panda-cube-v1"))
        self.assertEqual(self.manager.wait(left, timeout_s=30)["status"], "succeeded")
        self.assert_reaped(left)
        right = self.manager.start(new_config())
        self.assertEqual(self.manager.wait(right, timeout_s=30)["status"], "succeeded")
        self.assert_reaped(right)
        report = build_comparison_report([left.artifact_dir, right.artifact_dir])
        self.assertEqual(report["comparison_status"], "rejected")
        self.assertIn("拒绝产生优劣结论", report["conclusion"])

    def test_valid_panda_comparison_includes_only_valid_samples(self) -> None:
        left = self.manager.start(new_config(model_id="panda-cube-v1", strategy_id="baseline"))
        self.assertEqual(self.manager.wait(left, timeout_s=30)["status"], "succeeded")
        right = self.manager.start(new_config(model_id="panda-cube-v1", strategy_id="offset-grasp", grasp_offset=.08))
        self.assertEqual(self.manager.wait(right, timeout_s=30)["status"], "failed")
        report = build_comparison_report([left.artifact_dir, right.artifact_dir])
        self.assertEqual(report["comparison_status"], "comparable")
        self.assertEqual(report["sample_count"], 2)
        self.assertEqual(report["success_count"], 1)
        self.assertEqual(set(report["strategy_groups"]), {"baseline", "offset-grasp"})
        self.assertEqual(report["rejected_samples"], [])

    def test_q4_compare_fixtures_reject_scene_trajectory_events_and_result_corruption(self) -> None:
        # 用例自行生成真实且不同ID的输入；历史审查临时目录不属于可分发测试资源。
        left = self.manager.start(new_config(model_id="panda-cube-v1"))
        self.manager.wait(left, timeout_s=30)
        right = self.manager.start(new_config(model_id="panda-cube-v1", strategy_id="offset-grasp", grasp_offset=.08))
        self.manager.wait(right, timeout_s=30)
        source = right.artifact_dir
        self.assertEqual(build_comparison_report([left.artifact_dir, source])["comparison_status"], "comparable")
        cases = {
            "scene": lambda root: (root / "scene.json").write_text("{}", encoding="utf-8"),
            "trajectory_missing": lambda root: (root / "trajectory.jsonl").unlink(),
            "trajectory_invalid": lambda root: (root / "trajectory.jsonl").write_text("not-json\n", encoding="utf-8"),
            "events_invalid": lambda root: (root / "events.jsonl").write_text("not-json\n", encoding="utf-8"),
            "result_conflict": lambda root: self._make_result_conflict(root),
        }
        with tempfile.TemporaryDirectory() as directory:
            for name, mutate in cases.items():
                with self.subTest(case=name):
                    bad_parent = Path(directory) / name
                    bad = bad_parent / source.name
                    shutil.copytree(source, bad)
                    mutate(bad)
                    report = build_comparison_report([left.artifact_dir, bad])
                    self.assertEqual(report["comparison_status"], "rejected")
                    self.assertEqual(report["sample_count"], 0)
                    self.assertIsNone(report["success_count"])
                    self.assertIsNone(report["success_rate"])
                    self.assertEqual(report["strategy_groups"], {})
                    self.assertTrue(report["rejected_samples"])

    @staticmethod
    def _make_result_conflict(root: Path) -> None:
        path = root / "summary.json"
        summary = json.loads(path.read_text(encoding="utf-8"))
        summary["success"] = not summary["success"]
        path.write_text(json.dumps(summary), encoding="utf-8")

    def test_malformed_panda_identity_and_cross_run_summary_are_rejected(self) -> None:
        left = self.manager.start(new_config(model_id="panda-cube-v1"))
        self.assertEqual(self.manager.wait(left, timeout_s=30)["status"], "succeeded")
        self.assert_reaped(left)
        right = self.manager.start(new_config(model_id="panda-cube-v1", grasp_offset=.08))
        self.assertEqual(self.manager.wait(right, timeout_s=30)["status"], "failed")
        self.assert_reaped(right)
        meta_path = right.artifact_dir / "meta.json"
        summary_path = right.artifact_dir / "summary.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        # 分别破坏一个不变量，避免多个错误并存时断言依赖校验顺序。
        for mutation, reason in [("model", "model_hash"), ("run", "运行ID"), ("success", "success")]:
            with self.subTest(mutation=mutation):
                broken_meta = json.loads(json.dumps(meta))
                broken_summary = dict(summary)
                if mutation == "model": broken_meta["model"].pop("model_hash")
                elif mutation == "run": broken_summary["run_id"] = left.run_id
                else: broken_summary["success"] = "false"
                meta_path.write_text(json.dumps(broken_meta), encoding="utf-8")
                summary_path.write_text(json.dumps(broken_summary), encoding="utf-8")
                report = build_comparison_report([left.artifact_dir, right.artifact_dir])
                self.assertEqual(report["comparison_status"], "rejected")
                self.assertIn("invalid_artifacts", report["identity_differences"])
                self.assertTrue(any(reason in item["reason"] for item in report["rejected_samples"]))


if __name__ == "__main__":
    unittest.main()
