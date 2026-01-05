from __future__ import annotations

import random
from typing import Dict, List, Sequence

from morota.opt.task_order.representation import (
    Individual,
    RouteLayer,
    RepairLayer,
    TaskId,
    WorkerId,
)


def _assign_tasks_to_workers_randomly(
    worker_ids: Sequence[WorkerId],
    num_tasks: int,
    rng: random.Random,
) -> RouteLayer:
    """
    各タスクをなるべく均等にワーカーへ割り当てる。

    - 各タスクIDはちょうど1度だけ出現
    - 各ワーカーのタスク数差は高々1
    - worker_id は欠番OK
    - L_max 制約は設けない（repair用パラメータ）
    """
    wids = list(worker_ids)
    if not wids:
        raise ValueError("worker_ids is empty.")

    # タスクIDをシャッフル
    task_ids: List[TaskId] = list(range(num_tasks))
    rng.shuffle(task_ids)

    # 空ルート初期化
    routes: RouteLayer = {wid: [] for wid in wids}

    # --- 均等分配 ---
    n_workers = len(wids)
    for i, t_id in enumerate(task_ids):
        wid = wids[i % n_workers]
        routes[wid].append(t_id)

    # --- 各ワーカー内の順序もランダム化 ---
    for wid in wids:
        rng.shuffle(routes[wid])

    return routes

def _generate_random_repair_flags(
    worker_ids: Sequence[WorkerId],
    L_max: int,
    rng: random.Random,
    repair_prob: float,
) -> RepairLayer:
    """
    各ワーカーについて、長さ L_max の修理フラグ列をランダム生成する（dict keyed by worker_id）。
    実際に使われるのは「そのワーカーのタスク数 L_i 以下のインデックス」だけ。
    """
    wids = list(worker_ids)
    repairs: RepairLayer = {}
    for wid in wids:
        repairs[wid] = [rng.random() < repair_prob for _ in range(L_max)]
    return repairs


def random_individual(
    worker_ids: Sequence[WorkerId],
    num_tasks: int,
    L_max: int,
    rng: random.Random,
    repair_prob: float,
) -> Individual:
    """
    1 個体だけランダム生成して返すユーティリティ関数。
    """
    wids = list(worker_ids)

    routes = _assign_tasks_to_workers_randomly(
        worker_ids=wids,
        num_tasks=num_tasks,
        rng=rng,
    )
    repairs = _generate_random_repair_flags(
        worker_ids=wids,
        L_max=L_max,
        rng=rng,
        repair_prob=repair_prob,
    )

    return Individual(
        worker_ids=wids,
        num_tasks=num_tasks,
        L_max=L_max,
        routes=routes,
        repairs=repairs,
    )


def random_population(
    population_size: int,
    worker_ids: Sequence[WorkerId],
    num_tasks: int,
    L_max: int,
    rng: random.Random,
    repair_prob: float,
) -> List[Individual]:
    """
    指定した個体数ぶん、ランダムな個体を生成して返す（dict keyed by worker_id）。

    「初期集団を作るだけ」の GA 骨格用関数。
    """
    pop: List[Individual] = []
    wids = list(worker_ids)

    for _ in range(population_size):
        pop.append(
            random_individual(
                worker_ids=wids,
                num_tasks=num_tasks,
                L_max=L_max,
                rng=rng,  # 同じrngでOK（個体間でちゃんと乱数は進む）
                repair_prob=repair_prob,
            )
        )

    return pop
