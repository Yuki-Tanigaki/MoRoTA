from __future__ import annotations
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Counter, Dict, Tuple

from mesa import Model
from mesa.space import ContinuousSpace

from morota.sim.failure_models import FailureModel
from morota.sim.agent import WorkerAgent, TaskAgent, DepotAgent
from morota.config_loader import ScenarioConfig
from morota.sim.module import build_modules_from_cfg
from morota.utils.datacollector import OptDataCollector, StepDataCollector

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
        self.opt_collector = OptDataCollector(out_dir=out_dir, scenario_name=scenario_name, prefix=prefix)
        self.opt_collector.open()
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

        # タスクアロケーター
        ta_module = import_module(cfg.task_allocator.module)
        ta_class = getattr(ta_module, cfg.task_allocator.class_name)
        self.task_allocator = ta_class(**cfg.task_allocator.params)

        # ワーカーの作成
        self.workers: Dict[int, WorkerAgent] = {}
        self.configuration_planner.build_workers(self)
        # self._debug_show_depot_and_workers()

        # 故障モデル
        f_module = import_module(cfg.failure_model.module)
        f_cls = getattr(f_module, cfg.failure_model.class_name)
        self.failure_model: FailureModel = f_cls(**cfg.failure_model.params)

    def _debug_show_depot_and_workers(self) -> None:
        # --- Depot 在庫 ---
        print("\n[DEBUG] Depot stock snapshot")
        # DepotAgent に snapshot() がある前提（なければ fall back）
        if hasattr(self.depot, "snapshot"):
            stock = self.depot.snapshot()
        else:
            # 最低限: _stock_count / _stock_by_type があれば見る
            stock = {}
            if hasattr(self.depot, "_stock_count"):
                stock = dict(getattr(self.depot, "_stock_count"))
            elif hasattr(self.depot, "_stock_by_type"):
                sbt = getattr(self.depot, "_stock_by_type")
                stock = {k: len(v) for k, v in sbt.items()}
        print(stock)

        # --- Worker 所持 ---
        print("\n[DEBUG] Workers modules")
        for wid, w in self.workers.items():
            # Module object なら m.type、dictなら ["type"] を想定
            def _mtype(m):
                return getattr(m, "type", None) or (m.get("type") if isinstance(m, dict) else str(m))

            counts = Counter(_mtype(m) for m in w.modules)
            print(f"  worker#{wid} @pos={getattr(w,'pos',None)}: {dict(counts)}")


    # ==========================================================
    # 座標ユーティリティ
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

    def step(self):
        self.configuration_planner.build_workers(self)        
        workers = list(self.workers.values())
        tasks = list(self.tasks.values())
        for t in tasks:
            t.begin_step()

        # 各ワーカーのタスク選択
        self.task_allocator.assign_tasks(self)

        # for w in workers:
        #     print(w.mode)
        # print(self.steps)
        # self._debug_show_depot_and_workers()

        # 全エージェントのステップ実行
        self.agents.do("step")

        for t in tasks:
            t.end_step()

        if self.write_csv:
            self.data_collector.collect(self)

    def all_tasks_done(self) -> bool:
        return all(t.status == "done" for t in self.tasks.values())

    def get_makespan(self) -> float:
        # 1つでも未完了タスクがあれば未達成
        if any(t.finished_step is None for t in self.tasks.values()):
            return self.cfg.sim.max_steps * self.time_step

        return max(t.finished_step for t in self.tasks.values()) * self.time_step
    
    def finalize(self) -> None:
        self.data_collector.close()