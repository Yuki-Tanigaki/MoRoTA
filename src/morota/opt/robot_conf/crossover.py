# src/acta/ga/crossover.py
from __future__ import annotations

import random
from typing import Tuple

from morota.opt.robot_conf.representation import Individual


def one_point_crossover(
    parent1: Individual,
    parent2: Individual,
    rng: random.Random,
    *,
    p_cx: float = 1.0,
) -> Tuple[Individual, Individual]:
    """
    1点交叉（worker_types のリストを単純に切って入れ替える）

    - 交叉しない場合はコピーを返す
    - num_workers_max は両親で同じ前提（違うなら ValueError）
    """
    if parent1.num_workers_max != parent2.num_workers_max:
        raise ValueError("Parents must have the same num_workers_max for crossover.")

    n = parent1.num_workers_max

    # 交叉しない
    if n <= 1 or rng.random() >= p_cx:
        return parent1.copy(), parent2.copy()

    # cut は [1, n-1]
    cut = rng.randrange(1, n)

    g1 = parent1.worker_types
    g2 = parent2.worker_types

    c1_types = list(g1[:cut]) + list(g2[cut:])
    c2_types = list(g2[:cut]) + list(g1[cut:])

    return (
        Individual.from_worker_types(c1_types),
        Individual.from_worker_types(c2_types),
    )


def uniform_crossover(
    parent1: Individual,
    parent2: Individual,
    rng: random.Random,
    *,
    p_cx: float = 1.0,
    swap_prob: float = 0.5,
) -> Tuple[Individual, Individual]:
    """
    一様交叉（各遺伝子ごとに swap_prob で交換）

    - 交叉しない場合はコピーを返す
    """
    if parent1.num_workers_max != parent2.num_workers_max:
        raise ValueError("Parents must have the same num_workers_max for crossover.")

    n = parent1.num_workers_max

    if rng.random() >= p_cx:
        return parent1.copy(), parent2.copy()

    g1 = list(parent1.worker_types)
    g2 = list(parent2.worker_types)

    for i in range(n):
        if rng.random() < swap_prob:
            g1[i], g2[i] = g2[i], g1[i]

    return (
        Individual.from_worker_types(g1),
        Individual.from_worker_types(g2),
    )


def crossover(
    parent1: Individual,
    parent2: Individual,
    rng: random.Random,
    method: str = "one_point",
    p_cx: float = 1.0,
    swap_prob: float = 0.5,
) -> Tuple[Individual, Individual]:
    """
    呼び出し側が method 文字列だけで切り替えられる薄いラッパ。
    """
    if method == "one_point":
        return one_point_crossover(parent1, parent2, rng, p_cx=p_cx)
    if method == "uniform":
        return uniform_crossover(parent1, parent2, rng, p_cx=p_cx, swap_prob=swap_prob)

    raise ValueError(f"Unknown crossover method: {method}")
