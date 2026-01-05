from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence

# --- 型エイリアス ---
TaskId = int
WorkerId = int

Route = List[TaskId]
RepairFlags = List[bool]

RouteLayer = Dict[WorkerId, Route]
RepairLayer = Dict[WorkerId, RepairFlags]


@dataclass
class Individual:
    """
    GA における「2レイヤ個体表現」(dict keyed by worker_id)。

    - routes[wid]  = [task_id, ...]
    - repairs[wid] = [bool, ...]  (長さ L_max)

    worker_id は欠番があっても良い（例: 0,1,2,4,7）。
    routes/repairs に存在しない wid は
      - routes: 空ルート []
      - repairs: 全False
    とみなして扱えるようにする。
    """

    # --- 問題サイズ情報 ---
    worker_ids: List[WorkerId]        # 実際に対象とする worker_id の一覧（順序も保持）
    num_tasks: int                    # |J|
    L_max: int                        # 修理フラグ列の固定長

    # --- レイヤ表現（dict） ---
    routes: RouteLayer                # wid -> route
    repairs: RepairLayer              # wid -> flags (len=L_max)

    # --- GA 用付帯情報 ---
    objectives: List[float] = field(default_factory=list)
    fitness: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # worker_ids の重複禁止（順序は保持したいので set 化ではなくチェック）
        if len(set(self.worker_ids)) != len(self.worker_ids):
            raise ValueError("worker_ids contains duplicates.")

        # routes/repairs は worker_ids の部分集合でもよいが、ここで正規化しておくと安全
        self._normalize_layers()

        # repairs の形状チェック
        for wid in self.worker_ids:
            flags = self.repairs[wid]
            if len(flags) != self.L_max:
                raise ValueError(f"repairs[{wid}] length {len(flags)} != L_max={self.L_max}")

        # タスク被覆チェック（各タスクがちょうど1回）
        if not self.check_task_coverage():
            raise ValueError("Task assignment is not a valid permutation of 0..(num_tasks-1).")

    # -----------------------
    # 内部: 正規化
    # -----------------------
    def _normalize_layers(self) -> None:
        """
        - worker_ids にいる wid について routes/repairs のキーを必ず用意
        - worker_ids にいないキーは捨てる（バグ混入を防ぐ）
        - repairs が欠けてたら全Falseで埋める
        """
        # routes
        new_routes: RouteLayer = {wid: list(self.routes.get(wid, [])) for wid in self.worker_ids}

        # repairs
        new_repairs: RepairLayer = {}
        for wid in self.worker_ids:
            flags = self.repairs.get(wid)
            if flags is None:
                new_repairs[wid] = [False] * self.L_max
            else:
                new_repairs[wid] = list(flags)

        self.routes = new_routes
        self.repairs = new_repairs

    # -----------------------
    # ヘルパ
    # -----------------------
    def copy(self) -> "Individual":
        """ディープコピーを返す。"""
        return Individual(
            worker_ids=list(self.worker_ids),
            num_tasks=self.num_tasks,
            L_max=self.L_max,
            routes={wid: list(route) for wid, route in self.routes.items()},
            repairs={wid: list(flags) for wid, flags in self.repairs.items()},
            objectives=list(self.objectives),
            fitness=copy.deepcopy(self.fitness),
        )

    @property
    def task_ids(self) -> List[TaskId]:
        ids: List[TaskId] = []
        for wid in self.worker_ids:
            ids.extend(self.routes.get(wid, []))
        return ids

    def count_tasks_per_worker(self) -> Dict[WorkerId, int]:
        return {wid: len(self.routes.get(wid, [])) for wid in self.worker_ids}

    # -----------------------
    # 生成系
    # -----------------------
    @classmethod
    def from_routes_and_flags(
        cls,
        *,
        worker_ids: Sequence[WorkerId],
        routes: Mapping[WorkerId, Sequence[TaskId]],
        repairs: Mapping[WorkerId, Sequence[bool]],
        num_tasks: int,
        L_max: int,
    ) -> "Individual":
        wid_list = list(worker_ids)
        return cls(
            worker_ids=wid_list,
            num_tasks=num_tasks,
            L_max=L_max,
            routes={wid: list(routes.get(wid, [])) for wid in wid_list},
            repairs={wid: list(repairs.get(wid, [False] * L_max)) for wid in wid_list},
        )

    @classmethod
    def empty(
        cls,
        *,
        worker_ids: Sequence[WorkerId],
        num_tasks: int,
        L_max: int,
    ) -> "Individual":
        wid_list = list(worker_ids)
        return cls(
            worker_ids=wid_list,
            num_tasks=num_tasks,
            L_max=L_max,
            routes={wid: [] for wid in wid_list},
            repairs={wid: [False] * L_max for wid in wid_list},
        )

    # -----------------------
    # ユーティリティ
    # -----------------------
    def check_task_coverage(self) -> bool:
        """
        「各タスクがちょうど1回だけどこかのワーカーに割り当てられているか」をチェックする。
        """
        all_ids = self.task_ids
        if len(all_ids) != self.num_tasks:
            return False
        return sorted(all_ids) == list(range(self.num_tasks))
