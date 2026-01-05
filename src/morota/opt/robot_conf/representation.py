from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

# --- 型エイリアス ---
WorkerId = int
RobotType = str
MaybeRobotType = Optional[RobotType]  # None は「そのワーカーを使わない」


def _count_types(worker_types: List[MaybeRobotType]) -> Dict[RobotType, int]:
    out: Dict[RobotType, int] = {}
    for rt in worker_types:
        if rt is None:
            continue
        out[rt] = out.get(rt, 0) + 1
    return out


def _add_counts(a: Dict[str, int], b: Mapping[str, int]) -> Dict[str, int]:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, 0) + int(v)
    return out


def _deficits(required: Mapping[str, int], have: Mapping[str, int]) -> Dict[str, int]:
    d: Dict[str, int] = {}
    for t, need in required.items():
        need_i = int(need)
        have_i = int(have.get(t, 0))
        if have_i < need_i:
            d[t] = need_i - have_i
    return d


@dataclass
class Individual:
    """
    ロボット構成最適化（Configuration）用の個体表現。

    - worker_types[i] はワーカー i の robot_type 名（例: "TWSH"）または None
      None は「そのワーカーを使わない」を意味する。
    - num_workers_max は遺伝子長（固定）。
      有効ワーカー数は None 以外の個数で可変にできる。

    目的関数（例）:
      1) 合計性能（最大化したい → NSGA-II実装側で符号反転など）
      2) 故障時リスク（最小化）
    """
    num_workers_max: int
    worker_types: List[MaybeRobotType]

    objectives: List[float] = field(default_factory=list)
    fitness: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.worker_types) != self.num_workers_max:
            raise ValueError(
                f"len(worker_types)={len(self.worker_types)} != num_workers_max={self.num_workers_max}"
            )

    # -----------------------
    # 基本ユーティリティ
    # -----------------------
    def copy(self) -> "Individual":
        return Individual(
            num_workers_max=self.num_workers_max,
            worker_types=list(self.worker_types),
            objectives=list(self.objectives),
            fitness=copy.deepcopy(self.fitness),
        )

    @property
    def active_worker_ids(self) -> List[WorkerId]:
        return [i for i, rt in enumerate(self.worker_types) if rt is not None]

    @property
    def num_active_workers(self) -> int:
        return len(self.active_worker_ids)

    def count_robot_types(self) -> Dict[RobotType, int]:
        return _count_types(self.worker_types)

    # -----------------------
    # 在庫制約（デポ）関連
    # -----------------------
    def total_required_modules(self, cfg) -> Dict[str, int]:
        """
        この個体（構成）が要求するモジュール総数（type→count）を返す。
        cfg.robot_types[rt].required_modules を参照する。
        """
        req_total: Dict[str, int] = {}
        for rt in self.worker_types:
            if rt is None:
                continue
            if rt not in cfg.robot_types:
                raise ValueError(f"Unknown robot_type in individual: {rt}")

            spec = cfg.robot_types[rt]
            req_total = _add_counts(req_total, spec.required_modules)
        return req_total

    def is_feasible(self, cfg, depot_snapshot: Mapping[str, int]) -> bool:
        """
        在庫(depot_snapshot)でこの構成が組めるか。
        """
        req_total = self.total_required_modules(cfg)
        return not _deficits(req_total, depot_snapshot)

    def deficits(self, cfg, depot_snapshot: Mapping[str, int]) -> Dict[str, int]:
        """
        在庫不足分（type→不足数）を返す。0なら feasible。
        """
        req_total = self.total_required_modules(cfg)
        return _deficits(req_total, depot_snapshot)

    # -----------------------
    # 生成系
    # -----------------------
    @classmethod
    def empty(cls, num_workers_max: int) -> "Individual":
        """
        全ワーカー未使用（全部 None）で初期化。
        """
        return cls(
            num_workers_max=num_workers_max,
            worker_types=[None] * num_workers_max,
        )

    @classmethod
    def from_worker_types(cls, worker_types: List[MaybeRobotType]) -> "Individual":
        return cls(
            num_workers_max=len(worker_types),
            worker_types=list(worker_types),
        )

    @classmethod
    def random_init(
        cls,
        *,
        num_workers_max: int,
        cfg,
        depot_snapshot: Mapping[str, int],
        rng,
        p_none: float = 0.2,
        max_retry: int = 2000,
    ) -> "Individual":
        """
        在庫制約を満たす範囲でランダム初期化。
        - p_none: None（未使用）にする確率
        - max_retry: 失敗時の再試行回数

        注意: ここでは「構成だけ」を作る。実際の在庫予約（depot.try_reserve_all）は
              シミュレーション投入フェーズで行う。
        """
        all_types: List[str] = list(cfg.robot_types.keys())

        # 先に在庫をローカルに消費しながら組み上げる（feasible構成を作りやすい）
        stock: Dict[str, int] = {k: int(v) for k, v in depot_snapshot.items()}

        def can_add(rt: str, stock_now: Mapping[str, int]) -> bool:
            spec = cfg.robot_types[rt]
            for t, need in spec.required_modules.items():
                if int(stock_now.get(t, 0)) < int(need):
                    return False
            return True

        def consume(rt: str, stock_now: Dict[str, int]) -> None:
            spec = cfg.robot_types[rt]
            for t, need in spec.required_modules.items():
                stock_now[t] = int(stock_now.get(t, 0)) - int(need)

        for _ in range(max_retry):
            stock_local = dict(stock)
            genes: List[MaybeRobotType] = [None] * num_workers_max

            # 各遺伝子を順に決める
            for i in range(num_workers_max):
                if rng.random() < p_none:
                    genes[i] = None
                    continue

                # 追加可能なtypeからランダム選択
                feasible_types = [rt for rt in all_types if can_add(rt, stock_local)]
                if not feasible_types:
                    genes[i] = None
                    continue

                rt = rng.choice(feasible_types)
                genes[i] = rt
                consume(rt, stock_local)

            indiv = cls(num_workers_max=num_workers_max, worker_types=genes)
            if indiv.is_feasible(cfg, depot_snapshot):
                return indiv

        # 最後の手段：空個体
        return cls.empty(num_workers_max=num_workers_max)