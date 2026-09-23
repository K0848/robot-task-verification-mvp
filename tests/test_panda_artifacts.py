"""真实 Panda 产物的同源几何与损坏输入边界，不靠 DOM 字段证明画面。"""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import mujoco
import numpy as np

from robot_mvp.panda_model import initial_data, load_model
from robot_mvp.panda_runner import run_panda, write_json
from robot_mvp.v2_adapter import artifact_to_renderer_payload
from robot_mvp.v2_physics import SimulationConfig


class PandaArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_temp = tempfile.TemporaryDirectory()
        cls.source = Path(cls.source_temp.name) / "original"
        config = SimulationConfig(run_id="artifact-test", model_id="panda-cube-v1", max_steps=7000,
                                  initial_object_x=.45, target_x=.45)
        run_panda(config, cls.source, lambda status: None)

    @classmethod
    def tearDownClass(cls):
        cls.source_temp.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "run"
        shutil.copytree(self.source, self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def rewrite_frames(self, mutation):
        path = self.root / "trajectory.jsonl"
        frames = [json.loads(line) for line in path.read_text().splitlines()]
        mutation(frames)
        path.write_text("\n".join(json.dumps(frame) for frame in frames), encoding="utf-8")

    def test_compiled_geometry_matches_reconstructed_physics_at_key_frames(self):
        payload = artifact_to_renderer_payload(self.root)
        model, _ = load_model()
        data = initial_data(model)
        for ms in (2, 3400, 4200, 6500, 10500, 14000):
            f = min(payload["robot_frames"], key=lambda frame: abs(frame["sim_time_ms"]-ms))
            data.qpos[:] = f["qpos"]
            data.qvel[:] = f["qvel"]
            data.ctrl[:] = f["ctrl"]
            data.time = f["sim_time_ms"]/1000
            mujoco.mj_forward(model, data)
            for geom, pose in zip(payload["robot_scene"]["geoms"], f["geom_poses"]):
                np.testing.assert_allclose(pose["position"], data.geom_xpos[geom["id"]], atol=1e-7)
                rotation = np.zeros(9)
                mujoco.mju_quat2Mat(rotation, np.array(pose["quaternion"]))
                np.testing.assert_allclose(rotation, data.geom_xmat[geom["id"]], atol=1e-7)
        self.assertTrue(any(frame["target_state"]["held"] for frame in payload["frames"]))
        # 释放只是过程，不能把最终成功提前投影为“已稳定放置”。
        release = next(i for i, f in enumerate(payload["robot_frames"]) if f["released"])
        self.assertFalse(payload["frames"][release]["target_state"]["placed"])

    def test_empty_trajectory_rejected(self):
        (self.root / "trajectory.jsonl").write_text("")
        with self.assertRaisesRegex(ValueError, "缺少"):
            artifact_to_renderer_payload(self.root)

    def test_missing_pose_rejected(self):
        self.rewrite_frames(lambda frames: frames[0].pop("geom_poses"))
        with self.assertRaisesRegex(ValueError, "缺失"):
            artifact_to_renderer_payload(self.root)

    def test_nonmonotonic_time_rejected(self):
        self.rewrite_frames(lambda frames: frames[1].update(sim_time_ms=frames[0]["sim_time_ms"]))
        with self.assertRaisesRegex(ValueError, "时间"):
            artifact_to_renderer_payload(self.root)

    def test_invalid_quaternion_rejected(self):
        self.rewrite_frames(lambda frames: frames[0]["geom_poses"][0].update(quaternion=[0.,0.,0.,0.]))
        with self.assertRaisesRegex(ValueError, "四元数"):
            artifact_to_renderer_payload(self.root)

    def test_nonfinite_position_rejected(self):
        self.rewrite_frames(lambda frames: frames[0].update(object_position=[float("nan"),0,0]))
        with self.assertRaisesRegex(ValueError, "有限"):
            artifact_to_renderer_payload(self.root)

    def test_scene_corruption_rejected_but_report_unchanged(self):
        before = (self.root / "summary.json").read_bytes()
        (self.root / "scene.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "哈希"):
            artifact_to_renderer_payload(self.root)
        self.assertEqual(before, (self.root / "summary.json").read_bytes())

    def test_model_mismatch_rejected_even_with_valid_scene_checksum(self):
        scene = json.loads((self.root / "scene.json").read_text())
        scene["model_hash"] = "wrong"
        digest = write_json(self.root / "scene.json", scene)
        meta = json.loads((self.root / "meta.json").read_text())
        meta["scene_sha256"] = digest
        write_json(self.root / "meta.json", meta)
        with self.assertRaisesRegex(ValueError, "身份"):
            artifact_to_renderer_payload(self.root)

    def test_malformed_json_rejected(self):
        (self.root / "trajectory.jsonl").write_text("not-json")
        with self.assertRaises(ValueError):
            artifact_to_renderer_payload(self.root)


if __name__ == "__main__":
    unittest.main()
