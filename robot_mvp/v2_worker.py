from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path

from robot_mvp.v2_physics import SimulationConfig, run_physics
from robot_mvp.v2_runtime import validate_config


def _write_status(artifact_dir: Path, payload: dict) -> None:
    temporary = artifact_dir / "status.json.tmp"
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    target = artifact_dir / "status.json"
    for _ in range(10):
        try:
            temporary.replace(target)
            return
        except PermissionError:
            # On Windows the parent polling process can briefly hold a read
            # handle. Retry the atomic replacement instead of killing a valid run.
            time.sleep(0.01)
    target.write_text(temporary.read_text(encoding="utf-8"), encoding="utf-8")
    temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="V2 MuJoCo simulation worker")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        config = SimulationConfig(**json.loads(args.config.read_text(encoding="utf-8")))
        validate_config(config)
        run_physics(config, args.artifact_dir, lambda payload: _write_status(args.artifact_dir, payload))
        return 0
    except Exception as error:  # The parent needs a structured failure instead of a silent dead worker.
        known_config = locals().get("config")
        # 先关闭并落盘完整 traceback，再发布 failed；父进程看到终态后可能立即回收 worker。
        (args.artifact_dir / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        _write_status(
            args.artifact_dir,
            {
                "run_id": known_config.run_id if known_config is not None else "unknown",
                "status": "failed",
                "stage": "worker",
                "progress": 0.0,
                "error_code": "worker_exception",
                "error_message": str(error),
            },
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
