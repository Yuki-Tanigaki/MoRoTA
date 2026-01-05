from __future__ import annotations

import random
from typing import List, Mapping, Optional, Sequence

from morota.opt.robot_conf.representation import Individual, MaybeRobotType
from morota.sim.agent import WorkerAgent


# ============================================================
# internal utilities (stock / feasibility)
# ============================================================
def _can_build_type(cfg, stock: Mapping[str, int], robot_type: str) -> bool:
    spec = cfg.robot_types.get(robot_type)
    if spec is None:
        return False
    for t, need in spec.required_modules.items():
        if int(stock.get(t, 0)) < int(need):
            return False
    return True


def _consume_type(cfg, stock: dict[str, int], robot_type: str) -> None:
    spec = cfg.robot_types[robot_type]
    for t, need in spec.required_modules.items():
        stock[t] = int(stock.get(t, 0)) - int(need)


def _feasible_candidates(cfg, stock: Mapping[str, int]) -> List[str]:
    return [rt for rt in cfg.robot_types.keys() if _can_build_type(cfg, stock, rt)]


def _random_feasible_type(cfg, stock: Mapping[str, int], rng: random.Random) -> Optional[str]:
    cands = _feasible_candidates(cfg, stock)
    if not cands:
        return None
    return rng.choice(cands)


# ============================================================
# random initialization (NO worker info)
# ============================================================
def random_individual(
    *,
    num_workers_max: int,
    cfg,
    depot_snapshot: Mapping[str, int],
    rng: random.Random,
    p_use_worker: float = 0.80,
    shuffle_slots: bool = True,
) -> Individual:
    """
    ワーカー情報を一切使わず、depot_snapshot (在庫) 制約だけで
    feasible な Individual をランダム生成する。

    方針:
      - 各 worker slot を「使う/使わない(None)」を確率で決める
      - 使う場合、その時点の残在庫で作れる robot_type をランダムに選び、在庫を消費
      - 作れる type が無ければ None に落とす

    パラメータ:
      - p_use_worker: その枠を使う確率（高いほど多く作ろうとする）
      - shuffle_slots: 枠の処理順をシャッフル（左詰め固定による偏りを減らす）
    """
    stock: dict[str, int] = {k: int(v) for k, v in depot_snapshot.items()}
    genes: List[MaybeRobotType] = [None] * num_workers_max

    slots = list(range(num_workers_max))
    if shuffle_slots:
        rng.shuffle(slots)

    for i in slots:
        # 使わない
        if rng.random() > p_use_worker:
            genes[i] = None
            continue

        rt = _random_feasible_type(cfg, stock, rng)
        if rt is None:
            genes[i] = None
            continue

        genes[i] = rt
        _consume_type(cfg, stock, rt)

    ind = Individual.from_worker_types(genes)

    # 念のため最終チェック（ここで落ちるなら Individual/is_feasible 側がおかしい）
    if not ind.is_feasible(cfg, depot_snapshot):
        # ここに来たら生成ロジックと is_feasible の定義が不一致
        # デバッグしやすいように例外にする
        raise ValueError(f"random_individual produced infeasible genes: {genes}")

    return ind


def random_population(
    population_size: int,
    *,
    num_workers_max: int,
    cfg,
    depot_snapshot: Mapping[str, int],
    rng: random.Random,
    p_use_worker: float = 0.80,
    shuffle_slots: bool = True,
) -> List[Individual]:
    """
    random_individual を population_size 個作る。
    """
    pop: List[Individual] = []
    for _ in range(population_size):
        pop.append(
            random_individual(
                num_workers_max=num_workers_max,
                cfg=cfg,
                depot_snapshot=depot_snapshot,
                rng=rng,
                p_use_worker=p_use_worker,
                shuffle_slots=shuffle_slots,
            )
        )
    return pop


# ============================================================
# backward-compatible API (names kept)
# ============================================================
def perturb_individual_from_workers(
    workers: Sequence[WorkerAgent],
    num_workers_max: int,
    cfg,
    depot_snapshot: Mapping[str, int],
    rng: random.Random,
    repair_prob: float = 0.0,  # 互換のため未使用
    p_mut_gene: float = 0.15,  # 互換のため未使用
    p_activate_from_none: float = 0.50,  # 互換のため未使用
    p_deactivate_to_none: float = 0.10,  # 互換のため未使用
    max_retry: int = 300,  # 互換のため未使用
    prefer_declared: bool = True,  # 互換のため未使用
) -> Individual:
    """
    互換のため関数名は残すが、workers は使わない。
    「在庫だけ」で完全ランダム feasible 個体を生成する。
    """
    _ = workers  # 明示的に未使用
    _ = repair_prob, p_mut_gene, p_activate_from_none, p_deactivate_to_none, max_retry, prefer_declared
    return random_individual(
        num_workers_max=num_workers_max,
        cfg=cfg,
        depot_snapshot=depot_snapshot,
        rng=rng,
        p_use_worker=0.80,
        shuffle_slots=True,
    )


def perturb_population_from_workers(
    population_size: int,
    workers: Sequence[WorkerAgent],
    num_workers_max: int,
    cfg,
    depot_snapshot: Mapping[str, int],
    rng: random.Random,
    p_mut_gene: float = 0.15,  # 互換のため未使用
    p_activate_from_none: float = 0.50,  # 互換のため未使用
    p_deactivate_to_none: float = 0.10,  # 互換のため未使用
    max_retry: int = 300,  # 互換のため未使用
    prefer_declared: bool = True,  # 互換のため未使用
) -> List[Individual]:
    """
    互換のため関数名は残すが、workers は使わない。
    「在庫だけ」で完全ランダム feasible 集団を生成する。
    """
    _ = workers
    _ = p_mut_gene, p_activate_from_none, p_deactivate_to_none, max_retry, prefer_declared
    return random_population(
        population_size,
        num_workers_max=num_workers_max,
        cfg=cfg,
        depot_snapshot=depot_snapshot,
        rng=rng,
        p_use_worker=0.80,
        shuffle_slots=True,
    )









# from __future__ import annotations

# import random
# from typing import List, Mapping, Optional, Sequence

# from morota.opt.robot_conf.representation import Individual, MaybeRobotType
# from morota.sim.agent import WorkerAgent


# # -----------------------------
# # 内部ユーティリティ
# # -----------------------------
# def _extract_base_genes(
#     workers: Sequence[WorkerAgent],
#     num_workers_max: int,
#     prefer_declared: bool = True,
# ) -> List[MaybeRobotType]:
#     """
#     workers から基準遺伝子（robot_type or declared_type）を抜き出す。

#     - robot_type が None なら遺伝子も None
#     - workers が num_workers_max より短い場合、残りは None
#     """
#     genes: List[MaybeRobotType] = [None] * num_workers_max
#     n = min(len(workers), num_workers_max)

#     for i in range(n):
#         w = workers[i]
#         rt = None

#         if prefer_declared and hasattr(w, "declared_type"):
#             rt = getattr(w, "declared_type")
#         if rt is None and hasattr(w, "robot_type"):
#             rt = getattr(w, "robot_type")

#         genes[i] = rt if rt is not None else None

#     return genes


# def _can_build_type(cfg, stock: Mapping[str, int], robot_type: str) -> bool:
#     spec = cfg.robot_types.get(robot_type)
#     if spec is None:
#         return False
#     for t, need in spec.required_modules.items():
#         if int(stock.get(t, 0)) < int(need):
#             return False
#     return True


# def _consume_type(cfg, stock: dict[str, int], robot_type: str) -> None:
#     spec = cfg.robot_types[robot_type]
#     for t, need in spec.required_modules.items():
#         stock[t] = int(stock.get(t, 0)) - int(need)


# def _random_feasible_type(cfg, stock: Mapping[str, int], rng: random.Random) -> Optional[str]:
#     candidates: List[str] = []
#     for rt in cfg.robot_types.keys():
#         if _can_build_type(cfg, stock, rt):
#             candidates.append(rt)
#     if not candidates:
#         return None
#     return rng.choice(candidates)


# def _perturb_genes(
#     base: List[MaybeRobotType],
#     cfg,
#     rng: random.Random,
#     p_mut_gene: float,
#     p_activate_from_none: float,
#     p_deactivate_to_none: float,
# ) -> List[MaybeRobotType]:
#     """
#     基準遺伝子を確率的に摂動して提案遺伝子を作る（この段階では在庫チェックしない）。
#     """
#     all_types: List[str] = list(cfg.robot_types.keys())
#     genes = list(base)

#     for i, cur in enumerate(genes):
#         if rng.random() >= p_mut_gene:
#             continue

#         if cur is None:
#             # None -> type (or keep None)
#             if rng.random() < p_activate_from_none and all_types:
#                 genes[i] = rng.choice(all_types)
#             else:
#                 genes[i] = None
#         else:
#             # type -> None or type' へ
#             if rng.random() < p_deactivate_to_none:
#                 genes[i] = None
#             else:
#                 genes[i] = rng.choice(all_types) if all_types else cur

#     return genes


# def _fix_to_feasible(
#     proposed: List[MaybeRobotType],
#     *,
#     cfg,
#     depot_snapshot: Mapping[str, int],
#     rng: random.Random,
# ) -> List[MaybeRobotType]:
#     """
#     proposed を depot_snapshot 制約の範囲で feasible に寄せる。
#     - 左から順に確定していき、無理なら代替 feasible type を探す。なければ None。
#     """
#     stock: dict[str, int] = {k: int(v) for k, v in depot_snapshot.items()}
#     fixed: List[MaybeRobotType] = [None] * len(proposed)

#     for i, rt in enumerate(proposed):
#         if rt is None:
#             fixed[i] = None
#             continue

#         if _can_build_type(cfg, stock, rt):
#             fixed[i] = rt
#             _consume_type(cfg, stock, rt)
#             continue

#         alt = _random_feasible_type(cfg, stock, rng)
#         if alt is None:
#             fixed[i] = None
#         else:
#             fixed[i] = alt
#             _consume_type(cfg, stock, alt)

#     return fixed


# # -----------------------------
# # 外部API（初期化関数群）
# # -----------------------------
# def perturb_individual_from_workers(
#     workers: Sequence[WorkerAgent],
#     num_workers_max: int,
#     cfg,
#     depot_snapshot: Mapping[str, int],
#     rng: random.Random,
#     repair_prob: float = 0.0,  # 互換のためのダミー（構成最適化のみなら未使用）
#     p_mut_gene: float = 0.15,
#     p_activate_from_none: float = 0.50,
#     p_deactivate_to_none: float = 0.10,
#     max_retry: int = 300,
#     prefer_declared: bool = True,
# ) -> Individual:
#     """
#     workers の robot_type を基準に、摂動した構成 Individual を 1 つ生成する。

#     - worker.robot_type（or declared_type）を遺伝子として抽出
#     - None は未使用ワーカー
#     - 摂動 → feasible化（在庫制約に合わせて組み直し）
#     """
#     base = _extract_base_genes(
#         workers,
#         num_workers_max=num_workers_max,
#         prefer_declared=prefer_declared,
#     )

#     # リトライしながら feasible な個体を狙う
#     for _ in range(max_retry):
#         proposed = _perturb_genes(
#             base,
#             cfg=cfg,
#             rng=rng,
#             p_mut_gene=p_mut_gene,
#             p_activate_from_none=p_activate_from_none,
#             p_deactivate_to_none=p_deactivate_to_none,
#         )
#         fixed = _fix_to_feasible(
#             proposed,
#             cfg=cfg,
#             depot_snapshot=depot_snapshot,
#             rng=rng,
#         )
#         ind = Individual.from_worker_types(fixed)
#         if ind.is_feasible(cfg, depot_snapshot):
#             return ind

#     # どうしても無理なら、空に寄せる（全部 None）
#     return Individual.empty(num_workers_max=num_workers_max)


# def perturb_population_from_workers(
#     population_size: int,
#     workers: Sequence[WorkerAgent],
#     num_workers_max: int,
#     cfg,
#     depot_snapshot: Mapping[str, int],
#     rng: random.Random,
#     p_mut_gene: float = 0.15,
#     p_activate_from_none: float = 0.50,
#     p_deactivate_to_none: float = 0.10,
#     max_retry: int = 300,
#     prefer_declared: bool = True,
# ) -> List[Individual]:
#     """
#     workers を基準解として、摂動で初期集団を作る。
#     """
#     pop: List[Individual] = []
#     for _ in range(population_size):
#         pop.append(
#             perturb_individual_from_workers(
#                 workers=workers,
#                 num_workers_max=num_workers_max,
#                 cfg=cfg,
#                 depot_snapshot=depot_snapshot,
#                 rng=rng,
#                 p_mut_gene=p_mut_gene,
#                 p_activate_from_none=p_activate_from_none,
#                 p_deactivate_to_none=p_deactivate_to_none,
#                 max_retry=max_retry,
#                 prefer_declared=prefer_declared,
#             )
#         )
#     return pop
