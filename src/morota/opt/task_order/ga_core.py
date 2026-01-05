from __future__ import annotations

from copy import deepcopy
import random
from typing import List, Callable, Optional, Sequence

from morota.opt.task_order.crossover import crossover
from morota.opt.task_order.mutation import mutate
from morota.opt.task_order.representation import Individual, WorkerId
from morota.opt.task_order.initialization import random_population


EvaluateFunc = Callable[[Individual], List[float]]


class SimpleGA:
    def __init__(
        self,
        worker_ids: Sequence[WorkerId],
        num_tasks: int,
        L_max: int,
        pop_size: int,
        generations: int,
        elitism_rate: float,
        evaluate: EvaluateFunc,
        tournament_size: int = 2,
        mutation_rate: float = 0.1,
        seed: Optional[int] = None,
        repair_prob: float = 0.9,
    ):
        self.worker_ids = list(worker_ids)
        if not self.worker_ids:
            raise ValueError("worker_ids is empty.")
        if len(set(self.worker_ids)) != len(self.worker_ids):
            raise ValueError("worker_ids contains duplicates.")

        self.num_tasks = num_tasks
        self.L_max = L_max

        self.pop_size = pop_size
        self.generations = generations
        self.elitism_rate = elitism_rate
        self.evaluate = evaluate

        self.tournament_size = tournament_size
        self.mutation_rate = mutation_rate
        self.repair_prob = float(repair_prob)

        self.rng = random.Random(seed)

        self.population: List[Individual] = []
        self.best: Optional[Individual] = None

    # -------------------------
    # 初期化
    # -------------------------
    def initialize(self) -> None:
        self.population = random_population(
            population_size=self.pop_size,
            worker_ids=self.worker_ids,
            num_tasks=self.num_tasks,
            L_max=self.L_max,
            rng=self.rng,
            repair_prob=self.repair_prob,
        )
        for ind in self.population:
            ind.objectives = self.evaluate(ind)

    # -------------------------
    # 親選択
    # -------------------------
    def tournament_select(self) -> Individual:
        comps = self.rng.sample(self.population, self.tournament_size)
        return min(comps, key=lambda ind: ind.objectives[0])

    # -------------------------
    # GA 実行
    # -------------------------
    def run(self) -> Individual:
        self.initialize()

        elite_k = max(1, int(self.pop_size * self.elitism_rate))

        for _gen in range(self.generations):
            # --- 現世代からエリートを抜き出して保存 ---
            elites = sorted(self.population, key=lambda ind: ind.objectives[0])[:elite_k]
            elites = [deepcopy(e) for e in elites]

            # --- 次世代個体群の生成 ---
            need = self.pop_size - elite_k
            offspring: List[Individual] = []
            for _ in range(need):
                p1 = self.tournament_select()
                p2 = self.tournament_select()

                child = crossover(p1, p2, self.rng)
                mutate(child, self.rng, self.mutation_rate)
                child.objectives = self.evaluate(child)
                offspring.append(child)

            self.population = elites + offspring

        self.best = min(self.population, key=lambda ind: ind.objectives[0])
        return self.best
