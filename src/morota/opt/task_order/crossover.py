from __future__ import annotations

from typing import Dict, List, Tuple
import random

from morota.opt.task_order.representation import Individual, WorkerId, TaskId, RouteLayer, RepairLayer


def crossover(
    parent_a: Individual,
    parent_b: Individual,
    rng: random.Random,
) -> Individual:
    # --- sanity checks ---
    if parent_a.worker_ids != parent_b.worker_ids:
        # 「集合として同じ」までは許したいなら set比較に変えてもOKだが、
        # GA全体の安定性のため、まずは一致を要求するのがおすすめ
        raise ValueError("Parents must have the same worker_ids (same order).")
    if parent_a.num_tasks != parent_b.num_tasks:
        raise ValueError("Parents must have the same num_tasks.")
    if parent_a.L_max != parent_b.L_max:
        raise ValueError("Parents must have the same L_max.")

    # routes
    child_routes = route_layer_srex_like_crossover_routes(parent_a, parent_b, rng)
    child_routes = repair_routes_feasibility_routes(
        child_routes,
        worker_ids=parent_a.worker_ids,
        num_tasks=parent_a.num_tasks,
        L_max=parent_a.L_max,
        rng=rng,
    )

    # repairs
    child_repairs = repair_layer_uniform_crossover_repairs(parent_a, parent_b, rng)

    # assemble
    return Individual(
        worker_ids=list(parent_a.worker_ids),
        num_tasks=parent_a.num_tasks,
        L_max=parent_a.L_max,
        routes=child_routes,
        repairs=child_repairs,
    )


def route_similarity(route_a: List[int], route_b: List[int]) -> int:
    # set化（順序は無視、共通要素数）
    return len(set(route_a) & set(route_b))


def route_layer_srex_like_crossover_routes(
    parent_a: Individual,
    parent_b: Individual,
    rng: random.Random,
    p_select: float = 0.5,
) -> RouteLayer:
    """
    routes だけ返す SREX-like 交叉（dict keyed by worker_id）。
    """
    wids = parent_a.worker_ids
    # ベースはAのroutesコピー
    child_routes: RouteLayer = {wid: list(parent_a.routes.get(wid, [])) for wid in wids}

    # 交換対象S（worker_idの集合）
    S = [wid for wid in wids if rng.random() < p_select]
    if not S:
        S = [rng.choice(wids)]

    # B側の候補 worker_ids をシャッフルしながら「最類似」を探す
    for wid in S:
        base_route = parent_a.routes.get(wid, [])
        candidates = list(wids)
        rng.shuffle(candidates)

        best_w = candidates[0]
        best_sim = -1
        for w2 in candidates:
            sim = route_similarity(base_route, parent_b.routes.get(w2, []))
            if sim > best_sim:
                best_sim = sim
                best_w = w2

        child_routes[wid] = list(parent_b.routes.get(best_w, []))

    return child_routes


def repair_routes_feasibility_routes(
    routes: RouteLayer,
    worker_ids: List[WorkerId],
    num_tasks: int,
    L_max: int,
    rng: random.Random,
) -> RouteLayer:
    """
    routes を修復する（dict keyed by worker_id）。

    - 重複タスクは最後の出現を残して削除
    - 未割当タスクはどこかに挿入
    - 可能なら各ワーカーの長さ <= L_max を維持（無理なら超えることもあるが極力避ける）
    """
    T = num_tasks
    wids = list(worker_ids)

    # コピー & 欠けキーを補完
    routes2: RouteLayer = {wid: list(routes.get(wid, [])) for wid in wids}

    # appearances[t] = [(wid, pos), ...]
    appearances: List[List[Tuple[WorkerId, int]]] = [[] for _ in range(T)]
    for wid in wids:
        route = routes2[wid]
        for pos, task in enumerate(route):
            if 0 <= task < T:
                appearances[task].append((wid, pos))

    # 重複削除（最後の1つを残す）
    # ここで「最後」は appearances[t] の最後（走査順依存）なので、
    # 走査順を wid順に固定している点に注意（それでOKならこのまま）
    for t in range(T):
        if len(appearances[t]) <= 1:
            continue

        # 最後以外を消す
        to_remove = appearances[t][:-1]
        # pos削除でインデックスがズレるので、同一wid内では pos 降順で消す
        to_remove_sorted = sorted(to_remove, key=lambda x: (wids.index(x[0]), -x[1]))

        for wid, pos in to_remove_sorted:
            route = routes2[wid]
            if 0 <= pos < len(route) and route[pos] == t:
                route.pop(pos)
            else:
                # ずれてたら保険で remove
                try:
                    route.remove(t)
                except ValueError:
                    pass

    # 割当済み集合
    assigned = set()
    for wid in wids:
        assigned.update(routes2[wid])

    unassigned = list(set(range(T)) - assigned)
    rng.shuffle(unassigned)

    # 未割当を挿入
    for t in unassigned:
        candidates = [wid for wid in wids if len(routes2[wid]) < L_max]
        if not candidates:
            candidates = list(wids)  # どうしても入らないなら全員候補
        wid = rng.choice(candidates)
        route = routes2[wid]
        pos = rng.randrange(len(route) + 1)
        route.insert(pos, t)

    return routes2


def repair_layer_uniform_crossover_repairs(
    parent_a: Individual,
    parent_b: Individual,
    rng: random.Random,
) -> RepairLayer:
    """
    repairs の一様交叉（dict keyed by worker_id）。
    """
    wids = parent_a.worker_ids
    L_max = parent_a.L_max

    child_repairs: RepairLayer = {}
    for wid in wids:
        fa = parent_a.repairs.get(wid, [False] * L_max)
        fb = parent_b.repairs.get(wid, [False] * L_max)

        flags = [False] * L_max
        for l in range(L_max):
            flags[l] = fa[l] if rng.random() < 0.5 else fb[l]
        child_repairs[wid] = flags

    return child_repairs
