from __future__ import annotations
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Dict, Tuple

from mesa import Model
from mesa.space import ContinuousSpace

from morota.sim.failure_models import FailureModel
from morota.sim.agent import WorkerAgent, TaskAgent, DepotAgent
from morota.config_loader import ScenarioConfig
from morota.sim.module import build_modules_from_cfg
from morota.sim.task_selection import TaskSelector
from morota.utils.datacollector import StepDataCollector

class ScenarioModel(Model):
    def __init__(self, cfg: ScenarioConfig, seed: int, write_csv: bool):
        super().__init__(seed=seed)

        self.cfg = cfg
        self.time_step = cfg.sim.time_step

        # データ収集
        out_dir = Path(cfg.output_dir)
        scenario_name = cfg.scenario_name
        prefix = f"seed{seed:04d}"
        self.data_collector = StepDataCollector(out_dir=out_dir, scenario_name=scenario_name, prefix=prefix, flush_every=1)
        self.data_collector.open()
        self.write_csv = write_csv

        # シミュレーション空間設定
        self.space = ContinuousSpace(
            x_max=cfg.space.width,
            y_max=cfg.space.height,
            torus=False,    # 非ループ空間
        )

        # モジュールリスト
        modules = build_modules_from_cfg(cfg)

        # モジュールデポ
        self.depot = DepotAgent(model=self, modules=modules)
        x, y = cfg.module_depot_pos  # unpack
        self.space.place_agent(self.depot, (x, y))

        # タスク
        self.tasks: Dict[int, TaskAgent] = {}
        for t_spec in cfg.tasks:
            agent = TaskAgent(
                model=self,
                task_id=t_spec.task_id,
                total_work=t_spec.total_work,
                remaining_work=t_spec.remaining_work,
            )
            self.tasks[t_spec.task_id] = agent
            x, y = t_spec.position  # unpack
            self.space.place_agent(agent, (x, y))

        # ロボット構成プランナー
        cp_module = import_module(cfg.configuration_planner.module)
        cp_class = getattr(cp_module, cfg.configuration_planner.class_name)
        self.configuration_planner = cp_class(**cfg.configuration_planner.params)
        self.type_priority = cfg.type_priority

        # タスク割当
        ta_module = import_module(cfg.task_allocator.module)
        ta_class = getattr(ta_module, cfg.task_allocator.class_name)
        self.task_allocator = ta_class(**cfg.task_allocator.params)

        # ワーカー
        self.workers: Dict[int, WorkerAgent] = {}
        for w_spec in cfg.workers:
            agent = WorkerAgent(
                model=self,
                worker_id=w_spec.worker_id,
                speed=w_spec.speed,
                throughput=w_spec.throughput,
                speed_eta=w_spec.speed_eta,
                throughput_eta=w_spec.throughput_eta,
                initial_H=w_spec.initial_H,
                fatigue_move=w_spec.fatigue_move,
                fatigue_work=w_spec.fatigue_work,
            )
            self.workers[w_spec.worker_id] = agent
            x, y = w_spec.position  # unpack
            self.space.place_agent(agent, (x, y))

        # 故障モデル
        f_module = import_module(cfg.failure_model.module)
        f_cls = getattr(f_module, cfg.failure_model.class_name)
        self.failure_model: FailureModel = f_cls(**cfg.failure_model.params)
        # タスク選択ポリシー
        ts_module = import_module(cfg.task_selector.module)
        ts_class = getattr(ts_module, cfg.task_selector.class_name)
        self.task_selector: TaskSelector = ts_class(**cfg.task_selector.params)
        
        self.command_center.initialize_full_info(
            workers=self.workers.values(),
            tasks=self.tasks.values(),
        )
    
    # ==========================================================
    # 通信距離判定：エージェント/座標どちらでも使えるユーティリティ
    # ==========================================================
    def _get_pos(self, obj) -> Tuple[float, float]:
        """Agent または座標タプルを pos に変換するヘルパー."""
        if hasattr(obj, "pos"):
            return tuple(obj.pos)  # type: ignore[arg-type]
        return tuple(obj)          # すでに (x, y) の場合を想定

    def distance(self, a, b) -> float:
        """a と b の距離を返す（ContinuousSpace の設定に従う）."""
        pa = self._get_pos(a)
        pb = self._get_pos(b)
        # ContinuousSpace の get_distance を使えば torus 設定も反映される
        return self.space.get_distance(pa, pb)

    def can_communicate(self, a, b) -> bool:
        """a と b が通信可能距離内かどうか."""
        return self.distance(a, b) <= self.communication_range

    def step(self):
        workers = list(self.workers.values())
        # 全 worker について _next_info_state を計算
        for w in workers:
            w.prepare_communicate()
        
        self.command_center.communicate()

        # 全 worker の info_state を一斉に更新
        for w in workers:
            w.communicate()
        
        tasks = list(self.tasks.values())
        for t in tasks:
            t.begin_step()

        # 各ワーカーのタスク選択
        self.task_selector.assign_tasks(self)

        # 全エージェントのステップ実行
        self.agents.do("step")

        for t in tasks:
            t.end_step()

        if self.write_csv:
            self.data_collector.collect(self)

    def all_tasks_done(self) -> bool:
        return all(t.status == "done" for t in self.tasks.values())

    def get_makespan(self) -> float:
        # TaskAgent.finished_step の最大値 × time_step
        finished_steps = [
            t.finished_step for t in self.tasks.values() if t.finished_step is not None
        ]
        if not finished_steps:
            return self.cfg.max_steps
        return max(finished_steps) * self.time_step
    
    def finalize(self) -> None:
        self.data_collector.close()