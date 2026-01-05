from __future__ import annotations

import random
from typing import List

from morota.opt.task_order.representation import Individual, WorkerId


def mutate(
    child: Individual,
    rng: random.Random,
    mutation_rate: float = 0.1,
    # --- routes側（どれを選ぶかの比率） ---
    p_route_swap: float = 0.40,
    p_route_insert: float = 0.35,
    p_route_exchange: float = 0.25,
    # --- repairs側（bit flipの期待回数） ---
    repair_flip_rate: float = 1.0,
) -> None:
    """
    child(Individual) を破壊的に mutate する（dict keyed by worker_id）。

    mutation_rate:
      - この呼び出し1回あたり mutate する確率

    repair_flip_rate:
      - 1個体あたりの repairs の期待反転回数（例: 1.0 なら平均1bit flip）
    """
    if rng.random() >= mutation_rate:
        return

    # 1) routes mutate（安全操作のみ：重複/欠損が起きない）
    _mutate_routes(child, rng, p_route_swap, p_route_insert, p_route_exchange)

    # 2) repairs mutate（bit列に対する軽い摂動）
    _mutate_repairs(child, rng, repair_flip_rate)


# ============================================================
# routes mutation (feasibility-preserving)
# ============================================================

def _mutate_routes(
    ind: Individual,
    rng: random.Random,
    p_swap: float,
    p_insert: float,
    p_exchange: float,
) -> None:
    """
    routes について「常に全タスクがちょうど1回」を壊さない変異のみ行う。

    - intra swap    : 同一ワーカー内で2点 swap
    - intra insert  : 同一ワーカー内で1タスクを抜いて別位置へ挿入
    - inter exchange: 異なる2ワーカー間で各1タスクを交換（両方空でないとき）
    """
    s = p_swap + p_insert + p_exchange
    if s <= 0.0:
        return

    r = rng.random() * s
    if r < p_swap:
        _route_intra_swap(ind, rng)
    elif r < p_swap + p_insert:
        _route_intra_insert(ind, rng)
    else:
        _route_inter_exchange(ind, rng)


def _route_intra_swap(ind: Individual, rng: random.Random) -> None:
    # 長さ2以上のルートを持つ worker_id を選ぶ
    candidates: List[WorkerId] = [
        wid for wid in ind.worker_ids
        if len(ind.routes.get(wid, [])) >= 2
    ]
    if not candidates:
        return

    wid = rng.choice(candidates)
    rt = ind.routes[wid]
    a, b = rng.sample(range(len(rt)), 2)
    rt[a], rt[b] = rt[b], rt[a]


def _route_intra_insert(ind: Individual, rng: random.Random) -> None:
    # 長さ2以上のルートを持つ worker_id を選ぶ
    candidates: List[WorkerId] = [
        wid for wid in ind.worker_ids
        if len(ind.routes.get(wid, [])) >= 2
    ]
    if not candidates:
        return

    wid = rng.choice(candidates)
    rt = ind.routes[wid]

    frm = rng.randrange(len(rt))
    task = rt.pop(frm)
    to = rng.randrange(len(rt) + 1)
    rt.insert(to, task)


def _route_inter_exchange(ind: Individual, rng: random.Random) -> None:
    # 空でない worker_id を2つ選んで、各1要素を交換（重複/欠損は起きない）
    non_empty: List[WorkerId] = [
        wid for wid in ind.worker_ids
        if len(ind.routes.get(wid, [])) >= 1
    ]
    if len(non_empty) < 2:
        return

    w1, w2 = rng.sample(non_empty, 2)
    r1 = ind.routes[w1]
    r2 = ind.routes[w2]

    p1 = rng.randrange(len(r1))
    p2 = rng.randrange(len(r2))

    r1[p1], r2[p2] = r2[p2], r1[p1]


# ============================================================
# repairs mutation (no normalization)
# ============================================================

def _mutate_repairs(
    ind: Individual,
    rng: random.Random,
    flip_rate: float,
) -> None:
    """
    repairs のビット列を mutate（dict keyed by worker_id）。

    flip_rate を「期待反転回数」として扱い、
    - 小数込みの回数指定 → floor回 + 余り確率で+1回
    """
    wids = ind.worker_ids
    L = ind.L_max

    if not wids or L <= 0:
        return
    if flip_rate <= 0.0:
        return

    # flip回数（期待値 flip_rate）
    n = int(flip_rate)
    if rng.random() < (flip_rate - n):
        n += 1
    if n <= 0:
        n = 1  # mutate する以上、最低1回は反転

    for _ in range(n):
        wid = rng.choice(wids)
        li = rng.randrange(L)

        flags = ind.repairs.get(wid)
        if flags is None:
            # 念のため（通常は Individual.__post_init__ が埋めているはず）
            ind.repairs[wid] = [False] * L
            flags = ind.repairs[wid]

        flags[li] = not flags[li]
