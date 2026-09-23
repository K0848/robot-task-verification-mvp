"""S1 原生模型验证入口；不把运动检查宣称为抓取成功。"""
import argparse
import json
from pathlib import Path
import time

import mujoco
import numpy as np
from PIL import Image

from robot_mvp.panda_model import CRITERIA, HOME, initial_data, load_model, solve_ik


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(".tmp-tests/panda-spike"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    model, identity = load_model()
    loaded = time.perf_counter() - started
    data = initial_data(model)
    target = solve_ik(model, HOME, np.array([.45, 0, .20]))
    before = data.qpos[:9].copy()
    camera = mujoco.MjvCamera()
    camera.lookat[:] = [.35, 0, .30]
    camera.distance, camera.azimuth, camera.elevation = 1.5, 135, -25
    with mujoco.Renderer(model, height=480, width=640) as renderer:
        for step in range(2500):
            ratio = min(1., step / 1500)
            data.ctrl[:7] = HOME + (target - HOME) * (3 * ratio**2 - 2 * ratio**3)
            data.ctrl[7] = 255 if step < 1800 else 0
            mujoco.mj_step(model, data)
            if step in {1799, 2499}:
                mujoco.mj_forward(model, data)
                renderer.update_scene(data, camera)
                Image.fromarray(renderer.render()).save(args.output / f"{'open' if step == 1799 else 'closed'}.png")
        gap = float(data.qpos[7] + data.qpos[8])
        assert np.max(abs(data.qpos[:7] - before[:7])) > .1
        assert gap < .01
        assert np.isfinite(data.qpos).all()
    result = {"model": identity, "criteria": CRITERIA, "mujoco": mujoco.__version__,
              "load_s": loaded, "total_wall_s": time.perf_counter() - started,
              "sim_s": data.time, "closed_gap_m": gap, "nq": model.nq,
              "geoms": model.ngeom, "meshes": model.nmesh,
              "scope": "model motion and finger closing only; not grasp acceptance"}
    (args.output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in {"model", "criteria"}}))


if __name__ == "__main__":
    main()
