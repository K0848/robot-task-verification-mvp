"""Panda 正式验收断言先于控制实现；不把旧平面模型的结果当证据。"""
import json
import shutil
from pathlib import Path
import tempfile
import unittest

import mujoco
import numpy as np

from robot_mvp.panda_model import ASSET_ROOT, CRITERIA, initial_data, load_model, source_manifest

from robot_mvp.v2_physics import SimulationConfig


class PandaTaskTests(unittest.TestCase):
    def test_missing_mesh_is_rejected_without_touching_original_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'panda'
            shutil.copytree(ASSET_ROOT, root)
            # 故障只施加在本用例创建的副本，不移动或删除正在使用的模型资产。
            (root/'assets/finger_0.obj').unlink()
            with self.assertRaisesRegex(ValueError, 'finger_0.obj'):
                source_manifest(root)
            self.assertTrue((ASSET_ROOT/'assets/finger_0.obj').exists())

    def test_replaced_source_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SOURCES.json"
            source = json.loads((ASSET_ROOT / "SOURCES.json").read_text())
            source["commit"] = "wrong-commit"
            path.write_text(json.dumps(source))
            with self.assertRaisesRegex(ValueError, "来源清单"):
                source_manifest(Path(directory))

    def test_model_contains_only_finger_sync_not_object_weld(self):
        model, _ = load_model()
        self.assertTrue(all(kind == mujoco.mjtEq.mjEQ_JOINT for kind in model.eq_type))

    def test_contact_pick_place_and_single_offset_failure(self):
        from robot_mvp.panda_runner import run_panda
        with tempfile.TemporaryDirectory() as directory:
            for offset, expected in [(0., True), (.08, False)]:
                with self.subTest(offset=offset):
                    run_id = f"panda-test-{offset}"
                    root = Path(directory) / run_id
                    config = SimulationConfig(run_id=run_id, model_id="panda-cube-v1", max_steps=7000,
                                              initial_object_x=.45, target_x=.45, grasp_offset=offset)
                    summary = run_panda(config, root, lambda status: None)
                    self.assertEqual(summary["success"], expected)
                    frames = [json.loads(line) for line in (root / "trajectory.jsonl").read_text().splitlines()]
                    self.assertTrue(all(frame["sim_time_ms"] >= 0 for frame in frames))
                    self.assertTrue(all(len(frame["geom_poses"]) > 20 for frame in frames))
                    self.assertGreater(max(frame["gripper_width_m"] for frame in frames), .06)
                    if expected:
                        self.assertTrue(summary["success_criteria"]["lifted"])
                        self.assertTrue(summary["success_criteria"]["released"])
                        self.assertGreaterEqual(summary["success_criteria"]["stable_duration_s"], .5)
                        self.assertGreater(max(frame["object_position"][2] for frame in frames), .06)
                        supported = [f for f in frames if f["object_position"][2] > .06
                                     and min(f["contacts"].values()) > .01]
                        self.assertGreaterEqual(supported[-1]["sim_time_ms"]-supported[0]["sim_time_ms"], 250)
                        separated = [f for f in frames if f["released"]]
                        self.assertTrue(separated)
                        self.assertGreaterEqual(separated[0]["gripper_width_m"], .06)
                        self.assertLess(max(separated[0]["contacts"].values()), .01)
                        # 不仅相信 summary：用记录中的速度/位置复核最后半秒的稳定窗口。
                        for f in frames:
                            if f["sim_time_ms"] >= frames[-1]["sim_time_ms"]-500:
                                self.assertLessEqual(np.linalg.norm(np.array(f["object_position"][:2])-[.45,.2]), .04)
                                self.assertLessEqual(np.linalg.norm(f["qvel"][9:12]), CRITERIA["linear_speed_max_m_s"])
                    else:
                        self.assertFalse(summary["success_criteria"]["lifted"])
                        self.assertLess(max(frame["object_position"][2] for frame in frames), .05)
                    self.assertNotIn("grasp_lock", (root / "meta.json").read_text())


if __name__ == "__main__":
    unittest.main()
