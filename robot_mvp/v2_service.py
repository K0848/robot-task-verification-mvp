"""V2 用户业务入口：运行查询、参数方案、可信统计与比较，不依赖页面会话。"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from robot_mvp.v2_adapter import artifact_to_renderer_payload
from robot_mvp.v2_runtime import V2JobManager, _read_json, build_comparison_report, new_config, validate_summary, validate_config
from robot_mvp.v2_physics import SimulationConfig

DEFAULT_MODEL = 'panda-cube-v1'
MODEL_OPTIONS = (
    {'id':DEFAULT_MODEL, 'label':'Panda 机械臂与夹爪（接触抓放）', 'source':'panda_physics'},
    {'id':'minimal_planar_pick_place', 'label':'历史平面任务（位置示意）', 'source':'legacy_planar_physics'},
)
PARAMETER_PRESETS = (
    {'id':'baseline', 'label':'基线策略（grasp_offset=0.00）', 'grasp_offset':0.0},
    {'id':'offset-grasp', 'label':'受控偏移策略（grasp_offset=0.08）', 'grasp_offset':0.08},
)
STATES = {'queued','running','succeeded','failed','cancelled','unknown'}
MAX_PAGE_SIZE = 200  # 限制一次列表响应，不限制磁盘保留的历史数量。


class V2RunService:
    def __init__(self, artifacts_root: Path):
        self.manager = V2JobManager(artifacts_root)

    def models(self) -> list[dict]:
        return [dict(item) for item in MODEL_OPTIONS]

    def presets(self) -> list[dict]:
        return [dict(item) for item in PARAMETER_PRESETS]

    def start_run(self, preset_id: str, *, model_id: str = DEFAULT_MODEL,
                  fault_mode: str | None = None, wall_timeout_s: float = 30.):
        self._check_model(model_id)
        preset = next((item for item in PARAMETER_PRESETS if item['id'] == preset_id), None)
        if preset is None:
            raise ValueError(f'未知参数方案：{preset_id}')
        return self.manager.start(new_config(model_id=model_id, strategy_id=preset_id,
            grasp_offset=preset['grasp_offset'], fault_mode=fault_mode, wall_timeout_s=wall_timeout_s))

    def poll(self, handle):
        return self.manager.poll(handle)

    @staticmethod
    def _check_model(model_id: str) -> None:
        if not isinstance(model_id,str) or model_id not in {item['id'] for item in MODEL_OPTIONS}:
            raise ValueError(f'未知模型：{model_id}')

    def get_run(self, run_id: str, *, validate_evidence: bool = True) -> dict[str, Any]:
        directory = self.manager.artifacts.run_dir(run_id)
        if not directory.is_dir():
            raise FileNotFoundError(f'运行不存在：{run_id}')
        issues = []
        def read(name, required=False):
            try:
                value = _read_json(directory/name)
                if not isinstance(value, dict):
                    raise ValueError('必须是JSON对象')
                return value
            except FileNotFoundError:
                if required:
                    issues.append({'file':name,'message':'文件缺失'})
            except (OSError, ValueError) as error:
                issues.append({'file':name,'message':str(error)})
            return {}

        config = read('config.json', True)
        status = read('status.json', True)
        meta, summary = read('meta.json'), read('summary.json')
        environment = meta.get('environment') if isinstance(meta.get('environment'),dict) else {}
        model_id = config.get('model_id') or environment.get('model_name')
        if not isinstance(model_id,str):
            model_id = None
        try:
            validate_config(SimulationConfig(**config))
        except (ValueError, TypeError) as error:
            issues.append({'file':'config.json','message':str(error)})
        if meta and meta.get('config') != config:
            issues.append({'file':'meta.json','message':'配置文件与元数据副本不一致'})
        source = next((item['source'] for item in MODEL_OPTIONS if item['id'] == model_id), 'unknown')
        if source == 'unknown':
            issues.append({'file':'config.json','message':'模型身份缺失或不支持'})
        if environment.get('model_name') is not None and environment.get('model_name') != model_id:
            issues.append({'file':'meta.json','message':'配置与元数据模型不一致'})
        for name, value in [('config.json',config),('status.json',status),('meta.json',meta),('summary.json',summary)]:
            if value and value.get('run_id') != run_id:
                issues.append({'file':name,'message':'运行ID与目录不一致'})
        state = status.get('status','unknown')
        if not isinstance(state,str) or state not in STATES - {'unknown'}:
            issues.append({'file':'status.json','message':'未知执行状态'})
            state = 'unknown'
        outcome = summary.get('success')
        report_available = bool(summary)
        if summary:
            try:
                validate_summary(summary)
            except ValueError as error:
                issues.append({'file':'summary.json','message':str(error)})
                report_available = False
            if state in {'succeeded','failed'} and summary.get('final_status') != state:
                issues.append({'file':'status.json','message':'执行终态与任务报告不一致'})
        elif state == 'succeeded' or (state == 'failed' and not status.get('error_code')):
            issues.append({'file':'summary.json','message':'终态缺少任务报告或执行错误原因'})

        integrity = ('invalid' if issues else 'pending' if state in {'queued','running'}
                     else 'metadata_only' if report_available else 'unavailable')
        if validate_evidence and integrity == 'metadata_only':
            try:
                artifact_to_renderer_payload(directory)
                integrity = 'verified'
            except (OSError, ValueError, KeyError, TypeError) as error:
                issues.append({'file':'evidence','message':str(error)})
                integrity = 'invalid'
        # 旧错误运行可能没有meta。兼容时间来源显式标记，不伪造创建时间字段。
        created_at, created_source = meta.get('created_at'), 'meta.created_at'
        try:
            stamp = datetime.fromisoformat(created_at.replace('Z','+00:00'))
            if stamp.tzinfo is None:
                raise ValueError('缺少时区')
            created_at = stamp.astimezone(timezone.utc).isoformat()
        except (AttributeError, TypeError, ValueError):
            origin = directory/'config.json' if (directory/'config.json').exists() else directory
            created_at = datetime.fromtimestamp(origin.stat().st_mtime, timezone.utc).isoformat()
            created_source = 'config_file_mtime' if origin.is_file() else 'directory_mtime'
        return {
            'run_id':run_id, 'model_id':model_id, 'source':source,
            'created_at':created_at, 'created_at_source':created_source,
            'status':state, 'stage':status.get('stage'), 'progress':status.get('progress'),
            'strategy_id':config.get('strategy_id'), 'parameters':{'grasp_offset':config.get('grasp_offset')},
            'diagnostic':config.get('fault_mode') in ('crash','timeout'), 'fault_mode':config.get('fault_mode'),
            'task_success':outcome if isinstance(outcome,bool) and integrity not in {'invalid','pending'} else None,
            'integrity':integrity, 'issues':issues, 'report_available':report_available,
            'replay_available':True if integrity=='verified' else None if integrity=='metadata_only' else False,
            'error_code':status.get('error_code'), 'error_message':status.get('error_message'),
            'config':config, 'summary':summary if report_available else None,
            'process_liveness':'not_observed',
        }

    def _records(self, model_id, status, include_diagnostics):
        self._check_model(model_id)
        if status is not None and (not isinstance(status,str) or status not in STATES):
            raise ValueError(f'未知状态筛选：{status}')
        records, issues = [], []
        for run_id in self.manager.artifacts.list_run_ids():
            try:
                record = self.get_run(run_id, validate_evidence=False)
            except (OSError, ValueError) as error:
                issues.append({'run_id':run_id,'message':str(error)})
                continue
            if record['source']=='unknown':
                issues.append({'run_id':run_id,'message':'无法确定所属模型','details':record['issues']})
                continue
            if record['model_id'] != model_id or (record['diagnostic'] and not include_diagnostics):
                continue
            if status is None or record['status']==status:
                records.append(record)
        records.sort(key=lambda record:(record['created_at'],record['run_id']),reverse=True)
        return records,issues

    def list_runs(self, *, model_id=DEFAULT_MODEL, status=None, include_diagnostics=False, limit=50, offset=0):
        if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=MAX_PAGE_SIZE:
            raise ValueError(f'limit必须为1～{MAX_PAGE_SIZE}')
        if isinstance(offset,bool) or not isinstance(offset,int) or offset<0:
            raise ValueError('offset必须为非负整数')
        records,issues=self._records(model_id,status,include_diagnostics)
        return {'items':records[offset:offset+limit], 'total':len(records), 'limit':limit, 'offset':offset,
                'has_more':offset+limit<len(records), 'issues':issues, 'model_id':model_id,
                'validation_level':'metadata_only', 'include_diagnostics':include_diagnostics}

    def replay_payload(self, run_id):
        record=self.get_run(run_id,validate_evidence=False)
        if record['integrity']!='metadata_only':
            raise ValueError(f"运行不可回放：{record['integrity']}；{record['issues']}")
        return artifact_to_renderer_payload(self.manager.artifacts.run_dir(run_id))

    def compare(self, run_ids):
        return build_comparison_report([self.manager.artifacts.run_dir(run_id) for run_id in run_ids])

    def suggest_comparison(self, *, model_id=DEFAULT_MODEL):
        records,issues=self._records(model_id,None,False)
        candidates=[item for item in records if item['integrity']=='metadata_only']
        # 建议针对实际参数，不用名字或最新两条记录冒充基线和候选。
        baseline=next((p['grasp_offset'] for p in PARAMETER_PRESETS if p['id']=='baseline'))
        for left in candidates:
            if left['parameters']['grasp_offset']!=baseline:continue
            for right in candidates:
                if right['parameters']['grasp_offset']==baseline:continue
                report=self.compare([left['run_id'],right['run_id']])
                if report['comparison_status']=='comparable':
                    return {'run_ids':[left['run_id'],right['run_id']], 'reason':'相同条件下基线与不同参数方案', 'issues':issues}
                issues.extend(report['rejected_samples'])
        return {'run_ids':[], 'reason':'尚无同条件的基线与不同参数运行；同参数重复可手动做重复性检查', 'issues':issues}

    def overview(self, *, model_id=DEFAULT_MODEL):
        records,issues=self._records(model_id,None,False)
        verified, invalid, unknown, execution_errors = [],0,0,0
        counts={state:0 for state in STATES}
        for item in records:
            counts[item['status']]+=1
            if item['error_code']:execution_errors+=1
            record=self.get_run(item['run_id']) if item['integrity']=='metadata_only' else item
            if record['integrity']=='invalid':invalid+=1
            elif record['integrity']=='verified':verified.append(record)
            else:unknown+=1
        success=sum(item['task_success'] is True for item in verified)
        return {'model_id':model_id, 'total_runs':len(records), 'execution_counts':counts,
                'verified_result_count':len(verified), 'task_success_count':success,
                'task_failure_count':len(verified)-success,
                'task_success_rate':success/len(verified) if verified else None,
                'invalid_count':invalid, 'unknown_outcome_count':unknown, 'execution_error_count':execution_errors,
                'issues':issues, 'scope':'descriptive_verified_runs_for_one_model_not_a_benchmark',
                'diagnostics_included':False, 'generalization_supported':False}
