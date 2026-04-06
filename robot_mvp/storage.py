from __future__ import annotations

import json
from pathlib import Path

from robot_mvp.simulator import (
    create_benchmark_batch_bundle,
    create_live_run_bundle,
    iter_run_assets,
    seed_store_data,
    sync_run_statuses,
    sync_store_defaults,
)


class JsonStore:
    def __init__(self, path: Path):
        self.path = path

    def ensure_bootstrap(self) -> None:
        if self.path.exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.save(seed_store_data())

    def load(self):
        self.ensure_bootstrap()
        payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        from robot_mvp.models import StoreData

        data = StoreData.from_dict(payload)
        if sync_store_defaults(data):
            self.save(data)
        return data

    def save(self, data) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def sync_running_runs(self):
        data = self.load()
        if sync_run_statuses(data):
            self.save(data)
        return data

    def create_live_run(
        self,
        task_template_id: str,
        strategy_version_id: str,
        preset_key: str = "auto",
        operator_note: str | None = None,
        resolved_scenario: str | None = None,
        dynamic_profile: dict | None = None,
    ) -> str:
        data = self.load()
        task = next(item for item in data.task_templates if item.id == task_template_id)
        strategy = next(
            item for item in data.strategy_versions if item.id == strategy_version_id
        )
        run, events, frames = create_live_run_bundle(
            task_template=task,
            strategy=strategy,
            preset_key=preset_key,
            operator_note=operator_note,
            resolved_scenario=resolved_scenario,
            dynamic_profile=dynamic_profile,
        )
        data.run_records.append(run)
        data.run_events.extend(events)
        data.replay_frames.extend(frames)
        data.run_records.sort(key=lambda item: item.started_at, reverse=True)
        self.save(data)
        return run.id

    def create_benchmark_batch(
        self,
        task_template_id: str,
        strategy_version_id: str,
        suite_id: str,
        operator_note: str | None = None,
    ) -> str:
        data = self.load()
        task = next(item for item in data.task_templates if item.id == task_template_id)
        strategy = next(
            item for item in data.strategy_versions if item.id == strategy_version_id
        )
        suite = next(item for item in data.benchmark_suites if item.id == suite_id)
        batch, runs, events, frames = create_benchmark_batch_bundle(
            task_template=task,
            strategy=strategy,
            suite=suite,
            operator_note=operator_note,
        )
        data.benchmark_batches.insert(0, batch)
        data.run_records.extend(runs)
        data.run_events.extend(events)
        data.replay_frames.extend(frames)
        data.run_records.sort(key=lambda item: item.started_at, reverse=True)
        self.save(data)
        return batch.id

    def get_run_bundle(self, run_id: str):
        data = self.sync_running_runs()
        return iter_run_assets(data, run_id)
