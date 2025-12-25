from __future__ import annotations
from typing import Dict, List, Protocol
import random

from mesa import Model
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
    """
    既存 worker の不足補充 → 不足なら新規作成（declared_type はランダム）
    """

    def __init__(self, seed: int, num_workers: int) -> None:
        self.rng = random.Random(seed)
        self.num_workers = num_workers

    def build_workers(self, model: Model, workers: List[WorkerAgent]) -> None:
        cfg = model.cfg
        depot: DepotAgent = model.depot  # model が depot を持つ前提

        # --- 1) 既存 worker を順に補充（declared_type は変えない） ---
        for w in workers:
            if not w.declared_type:
                continue

            spec = cfg.robot_types[w.declared_type]
            have = _count_modules(w.modules)
            need_more = _deficits(dict(spec.required_modules), have)
            if not need_more:
                continue

            # DepotAgent.request_modules は「可能な分だけ払い出し」なので、
            # ここは不足分が出ても良い（とりあえず追加する）仕様にしている。
            granted = depot.request_modules(need_more)
            if granted:
                w.modules.extend(granted)
                w.refresh_capability_from_modules()

        # --- 2) num_workers に達するまで新規 worker を作成 ---
        while len(workers) < self.num_workers:
            snap = depot.snapshot()
            feasible = _feasible_types(cfg, snap)
            if not feasible:
                raise ValueError(f"No feasible robot_type with remaining stock: {snap}")

            declared_type = self.rng.choice(feasible)
            req = dict(cfg.robot_types[declared_type].required_modules)

            # 一括確保（足りないなら None で在庫は減らない）
            reserved = depot.try_reserve_all(req)
            if reserved is None:
                # feasible を snapshot から作ってるので基本起きないはずだが、競合があるなら起き得る
                continue

            wid = len(workers)
            w = WorkerAgent(
                model=model,
                worker_id=wid,
                modules=reserved,
                declared_type=declared_type,
            )

            model.workers[wid] = w