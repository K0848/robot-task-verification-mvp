from __future__ import annotations

import argparse
import json
from pathlib import Path

from robot_mvp.v2_runtime import V2JobManager, build_comparison_report, new_config
from robot_mvp.v2_service import V2RunService, DEFAULT_MODEL


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = ROOT / "data" / "v2_runs"


def main() -> int:
    parser = argparse.ArgumentParser(description="Robots V2 minimal verification harness")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    run_parser.add_argument("--strategy", default="baseline")
    run_parser.add_argument("--model", default="minimal_planar_pick_place")
    run_parser.add_argument("--grasp-offset", type=float, default=0.0)
    run_parser.add_argument("--fault", choices=["crash", "timeout"], default=None)
    run_parser.add_argument("--timeout", type=float, default=20.0)
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("run_dirs", nargs="+", type=Path)
    list_parser = subparsers.add_parser("list", help="查询V2运行，不读取V1演示")
    list_parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    list_parser.add_argument("--model", default=DEFAULT_MODEL)
    list_parser.add_argument("--status", default=None)
    list_parser.add_argument("--limit", type=int, default=50)
    list_parser.add_argument("--offset", type=int, default=0)
    list_parser.add_argument("--include-diagnostics", action="store_true")
    show_parser = subparsers.add_parser("show", help="按ID复查历史运行与证据完整性")
    show_parser.add_argument("run_id")
    show_parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    overview_parser = subparsers.add_parser("overview", help="只汇总指定模型的有效物理结果")
    overview_parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    overview_parser.add_argument("--model", default=DEFAULT_MODEL)

    args = parser.parse_args()
    if args.command in {"list", "show", "overview"}:
        service = V2RunService(args.artifacts)
        try:
            if args.command == "list":
                result = service.list_runs(model_id=args.model, status=args.status, limit=args.limit,
                    offset=args.offset, include_diagnostics=args.include_diagnostics)
            elif args.command == "show":
                result = service.get_run(args.run_id)
            else:
                result = service.overview(model_id=args.model)
        except (OSError, ValueError) as error:
            print(json.dumps({"error_code":"query_failed", "error_message":str(error)},ensure_ascii=False))
            return 2
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    if args.command == "run":
        manager = V2JobManager(args.artifacts)
        try:
            config = new_config(
                strategy_id=args.strategy,
                model_id=args.model,
                grasp_offset=args.grasp_offset,
                fault_mode=args.fault,
                wall_timeout_s=args.timeout,
            )
            handle = manager.start(config)
        except (TypeError, ValueError) as error:
            print(json.dumps({"status": "failed", "error_code": "invalid_config", "error_message": str(error)}, ensure_ascii=False, indent=2))
            return 2
        status = manager.wait(handle, timeout_s=args.timeout)
        print(json.dumps({"artifact_dir": str(handle.artifact_dir), **status}, ensure_ascii=False, indent=2))
        return 0 if status.get("status") == "succeeded" else 1
    try:
        report = build_comparison_report(args.run_dirs)
    except (OSError, ValueError) as error:
        print(json.dumps({"error_code":"comparison_failed", "error_message":str(error)},ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["comparison_status"] == "comparable" else 2


if __name__ == "__main__":
    raise SystemExit(main())
