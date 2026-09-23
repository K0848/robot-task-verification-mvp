"""固定配置串行重复，保留原始运行和由同帧 qpos 重建的原生截图。"""
import argparse
import json
from hashlib import sha256
from pathlib import Path
import shutil
import time

import mujoco
import numpy as np
from PIL import Image

from robot_mvp.panda_model import initial_data, load_model
from robot_mvp.panda_runner import write_json
from robot_mvp.v2_runtime import V2JobManager, new_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(".tmp-tests/panda-physics"))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--evidence", type=Path, help="仅复制摘要和原生截图，完整运行保留在 output")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manager = V2JobManager(args.output)
    results = []
    for strategy, offset in [("baseline", 0.), ("offset-grasp", .08)]:
        for iteration in range(args.repeats):
            run_id = f"panda-{strategy}-{iteration}"
            directory = args.output / run_id
            config = new_config(run_id=run_id, model_id="panda-cube-v1", strategy_id=strategy,
                                      max_steps=7000, initial_object_x=.45, target_x=.45, grasp_offset=offset)
            # 每轮使用独立 worker，避免把截图渲染器的内存高水位混入仿真峰值。
            handle = manager.start(config)
            status = manager.wait(handle, timeout_s=30)
            summary = manager.artifacts.read_summary(run_id)
            assert status['status'] == summary['final_status']
            assert summary["success"] == (offset == 0)
            performance = json.loads((directory / "performance.json").read_text())
            assert performance['process_id'] == handle.process.pid
            assert handle.process.poll() is not None
            assert performance['process_id'] != __import__('os').getpid()
            results.append({"run_id": run_id, "success": summary["success"], **performance})
            if iteration == 0:
                frames = [json.loads(line) for line in (directory / "trajectory.jsonl").read_text().splitlines()]
                model, _ = load_model()
                data = initial_data(model)
                camera = mujoco.MjvCamera()
                camera.lookat[:] = [.35, .05, .3]
                camera.distance, camera.azimuth, camera.elevation = 1.5, 135, -25
                with mujoco.Renderer(model, height=480, width=640) as renderer:
                    for target_ms in [0, 3400, 4200, 6500, 10500, 14000]:
                        frame = min(frames, key=lambda f: abs(f["sim_time_ms"]-target_ms))
                        data.qpos[:] = frame["qpos"]
                        data.qvel[:] = frame["qvel"]
                        data.ctrl[:] = frame["ctrl"]
                        data.time = frame["sim_time_ms"]/1000
                        mujoco.mj_forward(model, data)
                        scene = json.loads((directory / "scene.json").read_text())
                        for geom, pose in zip(scene["geoms"], frame["geom_poses"]):
                            np.testing.assert_allclose(data.geom_xpos[geom["id"]], pose["position"], atol=1e-7)
                        renderer.update_scene(data, camera)
                        Image.fromarray(renderer.render()).save(directory / f"native-{target_ms}.png")
            print(json.dumps(results[-1]), flush=True)
    report = {"runs": results, "scope": "fixed-condition repetition, not generalization", "verified_at": time.time(),
              "memory_scope": "fresh independent worker peak working set; native screenshots in parent excluded",
              "source_sha256": {name: sha256(Path(name).read_bytes()).hexdigest() for name in
                  ("robot_mvp/panda_model.py", "robot_mvp/panda_runner.py", "scripts/verify_panda_physics.py", "assets/robots/panda/SOURCES.json")}}
    write_json(args.output / "results.json", report)
    if args.evidence:
        args.evidence.mkdir(parents=True, exist_ok=True)
        write_json(args.evidence / "results.json", report)
        for source in args.output.glob("*/native-*.png"):
            shutil.copyfile(source, args.evidence / f"{source.parent.name}-{source.name}")


if __name__ == "__main__":
    main()
