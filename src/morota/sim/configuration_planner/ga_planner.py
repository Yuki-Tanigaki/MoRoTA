# src/morota/sim/configuration_planner/genetic_configuration_planner.py
from __future__ import annotations

from copy import deepcopy
import random
from typing import TYPE_CHECKING, Dict, List, Optional, Protocol, Sequence, Tuple

from mesa import Model
from morota.config_loader import ScenarioConfig
from morota.sim.agent.worker_agent import WorkerAgent
from morota.sim.agent.depot_agent import DepotAgent

from morota.opt.robot_conf.evaluator import ConfigurationEvaluator
from morota.opt.robot_conf.representation import Individual
from morota.opt.robot_conf.nsga2 import NSGA2
from morota.sim.configuration_planner.base_planner import ConfigurationPlanner

if TYPE_CHECKING:
    from morota.sim.model import ScenarioModel


def _select_one_from_pareto_chebyshev(
    front0: List[Individual],
    weight: Sequence[float],
    ideal: Optional[Sequence[float]] = None,
) -> Individual:
    """
    Pareto front から 1 個体を選ぶ（最小化）。
    各目的を front 内で正規化した重み付きチェビシェフ関数で選択する。
    """
    if not front0:
        raise ValueError("Pareto front is empty.")

    m = len(front0[0].objectives)
    if len(weight) != m:
        raise ValueError(f"Weight dimension mismatch: {len(weight)} != {m}")

    # --- 理想点 z ---
    if ideal is None:
        ideal = [
            min(ind.objectives[i] for ind in front0)
            for i in range(m)
        ]

    # --- nadir（max）点 ---
    nadir = [
        max(ind.objectives[i] for ind in front0)
        for i in range(m)
    ]

    best: Optional[Individual] = None
    best_value = float("inf")

    for ind in front0:
        cheb_vals = []

        for i in range(m):
            wi = float(weight[i])
            if wi <= 0.0:
                raise ValueError("All weights must be positive.")

            zi = float(ideal[i])
            fi = float(ind.objectives[i])
            ni = float(nadir[i])

            denom = ni - zi
            if denom <= 0.0:
                # front 内でこの目的は全て同値 → 影響させない
                norm = 0.0
            else:
                norm = (fi - zi) / denom  # [0,1]

            cheb_vals.append(wi * norm)

        cheb = max(cheb_vals)
        if cheb < best_value:
            best_value = cheb
            best = ind

    return best if best is not None else front0[0]


def hypervolume_2d_min(front: Iterable[Tuple[float, float]], ref: Tuple[float, float]) -> float:
    """
    2目的最小化の Hypervolume (HV)。
    front: (f1, f2) の集合（非劣解集合であることが望ましいが、多少混ざっても動く）
    ref: 参照点（front より「悪い」点: ref1 >= f1 かつ ref2 >= f2 を満たすのが基本）

    戻り値: front が ref を支配する領域の面積（2D）
    """
    R1, R2 = float(ref[0]), float(ref[1])

    pts: List[Tuple[float, float]] = []
    for f1, f2 in front:
        x, y = float(f1), float(f2)
        # ref を支配できない点は HV に寄与しない
        if x <= R1 and y <= R2:
            pts.append((x, y))
    if not pts:
        return 0.0

    # f1 昇順、同値なら f2 昇順
    pts.sort(key=lambda p: (p[0], p[1]))

    # 右から左へ。y_best は「これまで見た中で最小の f2」
    hv = 0.0
    y_best = R2
    # 右から走査
    for x, y in reversed(pts):
        if y < y_best:
            hv += (R1 - x) * (y_best - y)
            y_best = y
    return hv

class GeneticPlanner(ConfigurationPlanner):
    """
    NSGA-II により robot configuration（worker_types）を最適化して、
    その結果に基づいて WorkerAgent 群を生成・配置する Planner。

    RandomConfigurationPlanner と違い：
      - depot snapshot を制約として個体の feasible を判定
      - ただし実在庫確保は depot.try_reserve_all() に従う（失敗時はスキップ or リトライ）
    """

    def __init__(
        self,
        interval: int,
        seed: int,
        num_workers_max: int,
        pop_size: int,
        generations: int,
        trials: int = 1,
        preference: Sequence[float] = (1.0, 1.0),
        # NSGA-II operator params
        cx_method: str = "uniform",
        p_cx: float = 0.9,
        swap_prob: float = 0.5,
        p_mut_gene: float = 0.10,
        p_activate_from_none: float = 0.50,
        p_deactivate_to_none: float = 0.10,
    ) -> None:
        self.interval = int(interval)
        self.seed = int(seed)
        self.num_workers_max = int(num_workers_max)
        self.pop_size = int(pop_size)
        self.generations = int(generations)
        self.trials = int(trials)
        self.preference = preference

        self.cx_method = cx_method
        self.p_cx = float(p_cx)
        self.swap_prob = float(swap_prob)
        self.p_mut_gene = float(p_mut_gene)
        self.p_activate_from_none = float(p_activate_from_none)
        self.p_deactivate_to_none = float(p_deactivate_to_none)

        self._best_individual: Optional[Individual] = None

    # --------------------------------------------------
    # NSGA-II を実行して構成（best individual）を作る
    # --------------------------------------------------
    def _ensure_plan(self, model: "ScenarioModel") -> None:
        cfg: ScenarioConfig = model.cfg

        evaluator = ConfigurationEvaluator(cfg)
        # evaluator が self.model を参照しているので、ここで注入
        evaluator.model = model  # type: ignore[attr-defined]

        def evaluate(ind: Individual) -> List[float]:
            return evaluator(ind)  # [obj1, obj2] minimization

        results: List[Tuple[Tuple[float, float], int, Individual]] = []

        base_seed = self.seed
        for t in range(self.trials):
            trial_seed = base_seed + t

            nsga2 = NSGA2(
                model=model,
                num_workers_max=self.num_workers_max,
                pop_size=self.pop_size,
                generations=self.generations,
                evaluate=evaluate,
                seed=trial_seed,
                cx_method=self.cx_method,
                p_cx=self.p_cx,
                swap_prob=self.swap_prob,
                p_mut_gene=self.p_mut_gene,
                p_activate_from_none=self.p_activate_from_none,
                p_deactivate_to_none=self.p_deactivate_to_none,
                penalize_infeasible=True,
            )

            front0 = nsga2.run()
            front_points = [(ind.objectives[0], ind.objectives[1]) for ind in front0]
            hv = hypervolume_2d_min(front_points, ref=(0.0, 0.0))
            # HV が大きいほど良いが、「中央値」を取るため昇順で並べて中央を取る
            results.append((hv, trial_seed, front0))

        results.sort(key=lambda x: x[0])
        median_idx = len(results) // 2
        median_hv, median_seed, median_front0 = results[median_idx]
        # print(f"NSGA-II config selected median trial by HV(ref=(0,0)): seed={median_seed}, HV={median_hv:.6g}")
        chosen = _select_one_from_pareto_chebyshev(median_front0, weight=self.preference)

        self._best_individual = deepcopy(chosen)

        # ============================
        # 追加: 最適化イベントのログ
        # ============================
        opt_collector = getattr(model, "opt_collector", None)
        if opt_collector is not None:
            try:
                opt_collector.log_optimization(
                    step=int(getattr(model, "steps", 0)),
                    pareto_front=median_front0,        # パレートフロント（このtrialのfront0）
                    chosen=chosen,                      # 選好で選ばれた個体
                    preference=list(self.preference),   # 記録しやすい形に
                )
            except Exception as e:
                # ログ失敗でシミュ本体を止めたくない場合
                print(f"[WARN] opt_collector.log_optimization failed: {e}")

        self._best_individual = deepcopy(chosen)

    # --------------------------------------------------
    # Planner interface
    # --------------------------------------------------
    def build_workers(self, model: Model) -> None:
        cfg: ScenarioConfig = model.cfg
        depot: DepotAgent = model.depot

        # ---- guard ----
        if not getattr(self, "interval", 0):
            return
        if (model.steps - 1) % self.interval != 0:
            return

        last = getattr(self, "_last_update_step", None)
        if last == model.steps:
            return
        self._last_update_step = model.steps

        # ---- NSGA-II plan ----
        self._ensure_plan(model)  # type: ignore[arg-type]
        indiv = self._best_individual
        if indiv is None:
            raise ValueError("GeneticConfigurationPlanner has no plan individual.")

        for i, desired in enumerate(indiv.worker_types):
            existing: Optional[WorkerAgent] = model.workers.get(i)

            # 「データ上いるが robot_type=None なら死んでいる扱い」
            existing_alive = (
                existing is not None and getattr(existing, "robot_type", None) is not None
            )

            # ============================================
            # Case A: alive -> desired != None
            #   -> declared_type を更新するだけ
            # ============================================
            if existing_alive and desired is not None:
                existing.declared_type = desired
                continue

            # ============================================
            # Case B: alive -> desired is None
            #   -> モジュールを返却してワーカーを消す
            # ============================================
            if existing_alive and desired is None:
                # 1) depot に返す（failed は depot.put 側で捨てる想定）
                depot.put(list(existing.modules))

                # 2) space から remove
                try:
                    model.space.remove_agent(existing)
                except Exception:
                    pass
                try:
                    model.agents.remove(existing)  # AgentSet が remove を持つ版
                except Exception:
                    pass
                # 3) workers から remove
                model.workers.pop(i, None)
                continue

            # ============================================
            # Case C: dead -> desired != None
            #   -> depot から取り出してワーカーを作る
            # ============================================
            if (not existing_alive) and desired is not None:
                spec = cfg.robot_types.get(desired)
                if spec is None:
                    continue

                req = dict(spec.required_modules)
                reserved = depot.take(req)  # take() は足りなければ None
                if reserved is None:
                    continue

                # 「死んでる worker object」が残ってる場合は掃除
                if existing is not None:
                    try:
                        model.space.remove_agent(existing)
                    except Exception:
                        pass
                    try:
                        model.agents.remove(existing)  # AgentSet が remove を持つ版
                    except Exception:
                        pass
                    model.workers.pop(i, None)

                w = WorkerAgent(
                    model=model,
                    worker_id=i,
                    modules=list(reserved),
                    declared_type=desired,
                )

                # 最初から稼働可能
                w.mode = "idle"
                w.duration_left = 0.0

                model.workers[i] = w

                x, y = depot.pos
                model.space.place_agent(w, (x, y))
                continue

            # ============================================
            # Case D: dead -> desired is None
            # ============================================
            if (not existing_alive) and desired is None:
                try:
                    model.space.remove_agent(existing)
                except Exception:
                    pass
                try:
                    model.agents.remove(existing)  # AgentSet が remove を持つ版
                except Exception:
                    pass
                model.workers.pop(i, None)
                continue