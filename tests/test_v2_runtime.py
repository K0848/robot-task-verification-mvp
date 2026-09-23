from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from robot_mvp.v2_adapter import artifact_to_renderer_payload
from robot_mvp.v2_runtime import V2JobManager, build_comparison_report, new_config


class V2RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.manager = V2JobManager(Path(self.temp_dir.name) / "runs")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_job(self, **overrides):
        handle = self.manager.start(new_config(**overrides))
        status = self.manager.wait(handle, timeout_s=20)
        return handle, status

    def test_tc01_normal_run_writes_complete_physics_artifacts(self) -> None:
        handle, status = self.run_job(strategy_id="baseline")
        self.assertEqual(status["status"], "succeeded")
        required = {"meta.json", "status.json", "trajectory.jsonl", "events.jsonl", "summary.json"}
        self.assertTrue(required.issubset({item.name for item in handle.artifact_dir.iterdir()}))
        meta = self.manager.artifacts.read_meta(handle.run_id)
        summary = self.manager.artifacts.read_summary(handle.run_id)
        self.assertEqual(meta["trajectory_source"], "mujoco-runtime")
        self.assertEqual(meta["environment"]["runtime"], "native-mujoco")
        self.assertTrue(summary["success"])
        self.assertTrue(summary["success_criteria"]["grasp_locked"])

    def test_tc02_one_parameter_perturbation_is_recorded_as_failure(self) -> None:
        handle, status = self.run_job(strategy_id="offset-grasp", grasp_offset=0.08)
        self.assertEqual(status["status"], "failed")
        summary = self.manager.artifacts.read_summary(handle.run_id)
        self.assertFalse(summary["success"])
        self.assertEqual(summary["failure"]["classification"], "grasp")
        self.assertIn("偏移", summary["failure"]["possible_cause"])

    def test_tc03_worker_crash_and_timeout_do_not_block_parent(self) -> None:
        crash_handle, crash_status = self.run_job(fault_mode="crash")
        self.assertEqual(crash_status["status"], "failed")
        self.assertIn(crash_status["error_code"], {"worker_exception", "worker_crash"})

        timeout_handle = self.manager.start(new_config(fault_mode="timeout"))
        timeout_status = self.manager.wait(timeout_handle, timeout_s=0.2)
        self.assertEqual(timeout_status["status"], "failed")
        self.assertEqual(timeout_status["error_code"], "timeout")

    def test_tc04_comparison_keeps_same_initial_state_and_reports_insufficient_evidence(self) -> None:
        left, left_status = self.run_job(strategy_id="baseline", grasp_offset=0.0)
        right, right_status = self.run_job(strategy_id="offset-grasp", grasp_offset=0.08)
        self.assertEqual(left_status["status"], "succeeded")
        self.assertEqual(right_status["status"], "failed")
        report = build_comparison_report([left.artifact_dir, right.artifact_dir])
        self.assertTrue(report["same_initial_state"])
        self.assertEqual(report["strategy_ids"], ["baseline", "offset-grasp"])
        self.assertEqual(set(report["controlled_differences"]), {"grasp_offset"})
        self.assertEqual(report["controlled_differences"]["grasp_offset"], [0.0, 0.08])
        self.assertEqual(report["evidence_status"], "evidence_insufficient")
        self.assertIn("补测", report["conclusion"])

    def test_tc05_replay_uses_physics_trajectory_not_v1_snap_frames(self) -> None:
        handle, status = self.run_job(strategy_id="baseline")
        self.assertEqual(status["status"], "succeeded")
        payload = artifact_to_renderer_payload(handle.artifact_dir)
        self.assertEqual(payload["trajectory_source"], "mujoco-runtime")
        self.assertEqual(payload["coordinate_system"], "mujoco-world")
        self.assertGreater(len(payload["frames"]), 5)
        self.assertTrue(all("object_position" in frame for frame in payload["trajectory"]))
        self.assertTrue(all("arm_pose" in frame for frame in payload["frames"]))
        self.assertIn("object_z", payload["frames"][0]["target_state"])
        self.assertEqual(payload["resolved_scenario"], "")


if __name__ == "__main__":
    unittest.main()
