from __future__ import annotations

import random
from typing import List, Optional

from morota.opt.robot_conf.representation import Individual, MaybeRobotType


def mutate(
    individual: Individual,
    rng: random.Random,
    cfg,
    p_mut_ind: float = 1.0,
    p_mut_gene: float = 0.10,
    p_activate_from_none: float = 0.50,
    p_deactivate_to_none: float = 0.10,
) -> Individual:
    """
    cfg.robot_types を参照して突然変異を行う。
    """
    if rng.random() >= p_mut_ind:
        return individual.copy()

    g: List[MaybeRobotType] = list(individual.worker_types)
    all_types: List[str] = list(cfg.robot_types.keys())

    if not all_types:
        return individual.copy()

    for i, cur in enumerate(g):
        if rng.random() >= p_mut_gene:
            continue

        if cur is None:
            if rng.random() < p_activate_from_none:
                g[i] = rng.choice(all_types)
        else:
            if rng.random() < p_deactivate_to_none:
                g[i] = None
            else:
                g[i] = rng.choice(all_types)

    return Individual.from_worker_types(g)