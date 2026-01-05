from __future__ import annotations

from copy import deepcopy
import random
from typing import Callable, List, Optional, Sequence, Tuple

from morota.opt.robot_conf.crossover import crossover
from morota.opt.robot_conf.initialization import perturb_population_from_workers
from morota.opt.robot_conf.mutation import mutate
from morota.opt.robot_conf.representation import Individual

EvaluateFunc = Callable[[Individual], List[float]]  # returns [obj1, obj2] (minimization)


# ============================================================
# NSGA-II helpers
# ============================================================
def _dominates(a: Individual, b: Individual) -> bool:
    """Minimization dominance."""
    ao = a.objectives
    bo = b.objectives
    if not ao or not bo:
        raise ValueError("Individuals must be evaluated before dominance checks.")

    not_worse = True
    strictly_better = False
    for x, y in zip(ao, bo):
        if x > y:
            not_worse = False
            break
        if x < y:
            strictly_better = True
    return not_worse and strictly_better


def _fast_non_dominated_sort(pop: List[Individual]) -> List[List[Individual]]:
    """Returns fronts: F0, F1, ... and sets ind.fitness['rank']."""
    S: List[List[int]] = [[] for _ in range(len(pop))]
    n = [0 for _ in range(len(pop))]
    fronts: List[List[int]] = [[]]

    for i, p in enumerate(pop):
        S[i] = []
        n[i] = 0
        for j, q in enumerate(pop):
            if i == j:
                continue
            if _dominates(p, q):
                S[i].append(j)
            elif _dominates(q, p):
                n[i] += 1
        if n[i] == 0:
            pop[i].fitness["rank"] = 0
            fronts[0].append(i)

    k = 0
    while fronts[k]:
        nxt: List[int] = []
        for i in fronts[k]:
            for j in S[i]:
                n[j] -= 1
                if n[j] == 0:
                    pop[j].fitness["rank"] = k + 1
                    nxt.append(j)
        k += 1
        fronts.append(nxt)

    fronts.pop()  # remove last empty
    return [[pop[i] for i in front] for front in fronts]


def _crowding_distance(front: List[Individual]) -> None:
    """Sets ind.fitness['crowding']."""
    l = len(front)
    if l == 0:
        return

    for ind in front:
        ind.fitness["crowding"] = 0.0

    if l <= 2:
        for ind in front:
            ind.fitness["crowding"] = float("inf")
        return

    m = len(front[0].objectives)
    for k in range(m):
        front.sort(key=lambda ind: ind.objectives[k])
        front[0].fitness["crowding"] = float("inf")
        front[-1].fitness["crowding"] = float("inf")

        fmin = front[0].objectives[k]
        fmax = front[-1].objectives[k]
        if abs(fmax - fmin) <= 1e-12:
            continue

        for i in range(1, l - 1):
            prev_v = front[i - 1].objectives[k]
            next_v = front[i + 1].objectives[k]
            d = (next_v - prev_v) / (fmax - fmin)
            if front[i].fitness["crowding"] != float("inf"):
                front[i].fitness["crowding"] += d


def _binary_tournament(pop: Sequence[Individual], rng: random.Random) -> Individual:
    """
    NSGA-II tournament:
      - smaller rank is better
      - if tie, larger crowding is better
    """
    a = rng.choice(pop)
    b = rng.choice(pop)

    ra = int(a.fitness.get("rank", 10**9))
    rb = int(b.fitness.get("rank", 10**9))
    if ra < rb:
        return a
    if rb < ra:
        return b

    ca = float(a.fitness.get("crowding", -float("inf")))
    cb = float(b.fitness.get("crowding", -float("inf")))
    if ca > cb:
        return a
    if cb > ca:
        return b

    return a


def _environmental_selection(union: List[Individual], pop_size: int) -> List[Individual]:
    """NSGA-II: fill next population from union using fronts and crowding."""
    fronts = _fast_non_dominated_sort(union)
    next_pop: List[Individual] = []

    for front in fronts:
        _crowding_distance(front)
        if len(next_pop) + len(front) <= pop_size:
            next_pop.extend(front)
        else:
            front_sorted = sorted(front, key=lambda ind: ind.fitness["crowding"], reverse=True)
            need = pop_size - len(next_pop)
            next_pop.extend(front_sorted[:need])
            break

    return next_pop


# ============================================================
# NSGA-II class
# ============================================================
class NSGA2:
    def __init__(
        self,
        *,
        model,                      # ScenarioModel を想定（cfg, workers, depot）
        num_workers_max: int,
        pop_size: int,
        generations: int,
        evaluate: EvaluateFunc,
        seed: Optional[int] = None,
        # operators
        cx_method: str = "uniform",  # "one_point" | "uniform"
        p_cx: float = 0.9,
        swap_prob: float = 0.5,
        p_mut_ind: float = 1.0,
        p_mut_gene: float = 0.10,
        p_activate_from_none: float = 0.50,
        p_deactivate_to_none: float = 0.10,
        # feasibility
        penalize_infeasible: bool = True,
        infeasible_penalty: float = 1e12,
    ) -> None:
        self.model = model
        self.cfg = model.cfg

        self.num_workers_max = num_workers_max
        self.pop_size = pop_size
        self.generations = generations
        self.evaluate = evaluate

        self.cx_method = cx_method
        self.p_cx = p_cx
        self.swap_prob = swap_prob

        self.p_mut_ind = p_mut_ind
        self.p_mut_gene = p_mut_gene
        self.p_activate_from_none = p_activate_from_none
        self.p_deactivate_to_none = p_deactivate_to_none

        self.penalize_infeasible = penalize_infeasible
        self.infeasible_penalty = float(infeasible_penalty)

        self.rng = random.Random(seed)

        self.population: List[Individual] = []
        self.pareto_front: List[Individual] = []

    # -------------------------
    # 評価
    # -------------------------
    def _evaluate_individual(self, ind: Individual) -> None:
        if self.penalize_infeasible:
            snap = self.model.depot.snapshot()
            if not ind.is_feasible(self.cfg, snap):
                ind.objectives = [self.infeasible_penalty, self.infeasible_penalty]
                ind.fitness["feasible"] = False
                return

        ind.objectives = list(self.evaluate(ind))
        ind.fitness["feasible"] = True

    def _evaluate_population(self) -> None:
        for ind in self.population:
            self._evaluate_individual(ind)

    # -------------------------
    # 初期化
    # -------------------------
    def initialize(self) -> None:
        self.population = perturb_population_from_workers(
            population_size=self.pop_size,
            workers=list(self.model.workers.values()),
            num_workers_max=self.num_workers_max,
            cfg=self.cfg,
            depot_snapshot=self.model.depot.snapshot(),
            rng=self.rng,
            p_mut_gene=0.15,  # 初期は少し多様性
            p_activate_from_none=self.p_activate_from_none,
            p_deactivate_to_none=self.p_deactivate_to_none,
            max_retry=500,
            prefer_declared=True,
        )
        self._evaluate_population()

        # rank/crowding をセット（トーナメント用）
        fronts = _fast_non_dominated_sort(self.population)
        for f in fronts:
            _crowding_distance(f)

    # -------------------------
    # 実行
    # -------------------------
    def run(self) -> List[Individual]:
        self.initialize()

        for _gen in range(self.generations):
            # ---- offspring generation ----
            offspring: List[Individual] = []
            while len(offspring) < self.pop_size:
                p1 = _binary_tournament(self.population, self.rng)
                p2 = _binary_tournament(self.population, self.rng)

                c1, c2 = crossover(
                    p1, p2, self.rng,
                    method=self.cx_method,
                    p_cx=self.p_cx,
                    swap_prob=self.swap_prob,
                )

                c1 = mutate(
                    c1, self.rng, cfg=self.cfg,
                    p_mut_ind=self.p_mut_ind,
                    p_mut_gene=self.p_mut_gene,
                    p_activate_from_none=self.p_activate_from_none,
                    p_deactivate_to_none=self.p_deactivate_to_none,
                )
                c2 = mutate(
                    c2, self.rng, cfg=self.cfg,
                    p_mut_ind=self.p_mut_ind,
                    p_mut_gene=self.p_mut_gene,
                    p_activate_from_none=self.p_activate_from_none,
                    p_deactivate_to_none=self.p_deactivate_to_none,
                )

                offspring.append(c1)
                if len(offspring) < self.pop_size:
                    offspring.append(c2)

            # ---- evaluate offspring ----
            for ind in offspring:
                self._evaluate_individual(ind)

            # ---- environmental selection ----
            union = self.population + offspring
            self.population = _environmental_selection(union, self.pop_size)

            # 次世代トーナメント用の rank/crowding を更新
            fronts = _fast_non_dominated_sort(self.population)
            for f in fronts:
                _crowding_distance(f)

        # ---- final pareto front (rank=0) ----
        fronts = _fast_non_dominated_sort(self.population)
        self.pareto_front = [deepcopy(ind) for ind in fronts[0]] if fronts else []
        return self.pareto_front
