from __future__ import annotations
from typing import Dict, List, Protocol
import random

from mesa import Model
from morota.config_loader import ScenarioConfig
from morota.domain.inventory import try_reserve_all
from morota.sim.agent import WorkerAgent, TaskAgent
from morota.sim.agent.depot_agent import DepotAgent


class ConfigurationPlanner(Protocol):
    """
    ロボット構成プランナーの基底クラス（Protocol）。
    """

    def build_wokers(self, model: Model, workers: list[WorkerAgent]) -> None:
        """
        モデル内にワーカーエージェントを構築・配置する。
        """
        ...

def _count_modules(modules: list) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for m in modules:
        counts[m.type] = counts.get(m.type, 0) + 1
    return counts


def _deficits(required: Dict[str, int], have: Dict[str, int]) -> Dict[str, int]:
    d: Dict[str, int] = {}
    for t, need in required.items():
        if have.get(t, 0) < need:
            d[t] = need - have.get(t, 0)
    return d


def _feasible_types(cfg, depot_snapshot: Dict[str, int]) -> List[str]:
    feasible: List[str] = []
    for rtype, spec in cfg.robot_types.items():
        ok = True
        for t, need in spec.required_modules.items():
            if depot_snapshot.get(t, 0) < need:
                ok = False
                break
        if ok:
            feasible.append(rtype)
    return feasible


class RandomConfigurationPlanner(ConfigurationPlanner):
    def __init__(self, seed: int, num_workers: int) -> None:
        self.rng = random.Random(seed)
        self.num_workers = num_workers

    def build_workers(self, model: Model) -> None:
        cfg: ScenarioConfig = model.cfg
        depot: DepotAgent = model.depot

        while len(model.workers) < self.num_workers:
            snap = depot.snapshot()                 # 観測（デバッグ用/例外メッセージ用）
            feasible = _feasible_types(cfg, snap)   # 観測に基づく候補抽出
            if not feasible:
                raise ValueError(f"No feasible robot_type with remaining stock: {snap}")

            declared_type = self.rng.choice(feasible)
            req = dict(cfg.robot_types[declared_type].required_modules)

            # 在庫を実際に確保
            reserved = depot.try_reserve_all(req)
            if reserved is None:
                # feasible 判定は snapshot に基づくので、将来「予約」などが入るとズレる可能性がある
                # なので "despite feasibility check" ではなく、リトライにするのが安全
                continue

            wid = len(model.workers)
            w = WorkerAgent(
                model=model,
                worker_id=wid,
                modules=reserved,
                declared_type=declared_type,
            )

            w.mode = "reconstruction"
            w.duration_left = cfg.sim.reconstruct_duration
            w._reserved_modules = w.modules
            w.modules = []

            model.workers[wid] = w

            x, y = depot.pos
            model.space.place_agent(w, (x, y))