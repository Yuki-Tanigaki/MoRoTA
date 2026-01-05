from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Tuple

from morota.domain import inventory
from morota.opt.task_order.evaluator import ExpectedMakespanEvaluator
from morota.opt.task_order.representation import Individual
from morota.opt.task_order.ga_core import SimpleGA

from morota.sim.agent.depot_agent import DepotAgent
from morota.sim.agent.task_agent import TaskAgent
from morota.sim.agent.worker_agent import WorkerAgent
from morota.sim.task_allocator.base_allocator import TaskAllocator

if TYPE_CHECKING:
    from morota.sim.model import ScenarioModel


class GeneticAllocator(TaskAllocator):
    """
    GA によって「ワーカーごとのタスク担当ルート」と
    「タスク何個終了時に修理に行くか（RepairFlags）」を決め、
    その結果に基づいて各ステップで target_task / 修理指示 を更新する TaskAllocator。
    """

    def __init__(
        self,
        interval: int,
        pop_size: int,
        generations: int,
        elitism_rate: float,
        L_max: int,
        seed: int,
        trials: int,
    ) -> None:
        self.interval = interval
        self.pop_size = pop_size
        self.generations = generations
        self.elitism_rate = elitism_rate
        self.L_max = L_max
        self.seed = seed
        self.trials = trials

        self._best_individual: Optional[Individual] = None
        self._last_repair_index: dict[int, int] = {}

    # --------------------------------------------------
    # GA を実行してベスト個体（計画）を作る
    # --------------------------------------------------
    def _ensure_plan(self, model: ScenarioModel) -> None:
        """
        GA を複数回実行し、目的値（makespan）の中央値となる試行結果を採用する。
        """
        # retired を除外した worker_id のリスト（欠番OK）
        worker_ids = sorted(
            w.worker_id for w in model.workers.values()
            if w.mode != "retire"
        )
        num_tasks = len(model.tasks)

        # worker がいない/タスクがない場合のガード
        if not worker_ids or num_tasks <= 0:
            self._best_individual = Individual.empty(
                worker_ids=worker_ids,
                num_tasks=num_tasks,
                L_max=self.L_max,
            )
            return

        makespan_evaluator = ExpectedMakespanEvaluator(model)

        def evaluate(ind: Individual) -> list[float]:
            makespan = makespan_evaluator(ind)[0]
            return [float(makespan)]  # 小さいほど良い

        results: List[Tuple[float, int, Individual]] = []

        base_seed = int(self.seed)
        for t in range(self.trials):
            trial_seed = base_seed + t

            ga = SimpleGA(
                worker_ids=worker_ids,
                num_tasks=num_tasks,
                L_max=self.L_max,
                pop_size=self.pop_size,
                generations=self.generations,
                elitism_rate=self.elitism_rate,
                evaluate=evaluate,
                seed=trial_seed,
            )

            ind = ga.run()
            obj0 = float(ind.objectives[0]) if ind.objectives else float("inf")
            results.append((obj0, trial_seed, ind))

        # makespan 昇順で中央値
        results.sort(key=lambda x: x[0])
        median_idx = len(results) // 2
        _median_obj0, _median_seed, median_ind = results[median_idx]
        # print(f"GA allocator selected median individual from trial seed={_median_seed} with makespan={_median_obj0:.2f}")
        self._best_individual = median_ind
        

    # --------------------------------------------------
    # ヘルパ: current_work を計算する
    # --------------------------------------------------
    def _compute_current_work_for_worker(
        self,
        worker: WorkerAgent,
        indiv: Individual,
        model: ScenarioModel,
    ) -> int:
        """
        indiv.routes[worker_id] のうち、model.tasks で status=="done" となっているタスク数を数える。
        """
        wid = worker.worker_id
        route = indiv.routes.get(wid, [])

        current_work = 0
        for task_id in route:
            t = model.tasks.get(task_id)
            if t is None or t.status != "done":
                break
            current_work += 1

        return current_work

    # --------------------------------------------------
    # TaskAllocator インタフェース実装
    # --------------------------------------------------
    def assign_tasks(self, model: ScenarioModel) -> None:
        # --- GA 計画を用意 ---
        if (model.steps - 1) % self.interval == 0:
            self._ensure_plan(model)

        indiv = self._best_individual
        depot: DepotAgent = model.depot
        stock = depot.snapshot()

        if indiv is None:
            raise ValueError("GA allocator has no individual plan.")

        tasks_by_id: dict[int, TaskAgent] = model.tasks

        for w in model.workers.values():
            worker_id = w.worker_id

            # 既に「修理に行く途中」「修理中」「リタイア」ならここでは何もしない
            if w.mode in ("go_reconstruction", "reconstruction", "retire"):
                continue

            # このワーカーのルート（dictなので get）
            route = indiv.routes.get(worker_id, [])
            if not route:
                w.target_task = None
                w.mode = "idle"
                continue

            # current_work を確認
            current_work = self._compute_current_work_for_worker(
                worker=w,
                indiv=indiv,
                model=model,
            )

            # ルートのタスクがすべて完了
            if current_work >= len(route):
                w.target_task = None
                w.mode = "idle"
                continue

            # RepairFlags（欠けてたら False 埋め）
            repair_flags = indiv.repairs.get(worker_id, [False] * indiv.L_max)

            # その worker が「直近で修理を発動した current_work」
            last_triggered = self._last_repair_index.get(worker_id)  # None=未発動

            go_repair = (
                0 <= current_work < len(repair_flags)
                and bool(repair_flags[current_work])
                and last_triggered != current_work
            )

            deficits = w.deficits_for_declared_type()
            if go_repair and inventory.can_cover(deficits, stock):
                w.target_task = None
                w.mode = "go_reconstruction"
                self._last_repair_index[worker_id] = current_work
                continue

            # 次の仕事に向かう
            next_task_id = route[current_work]
            task = tasks_by_id.get(next_task_id)
            if task is None:
                raise ValueError(f"Task id {next_task_id} not found for worker_id={worker_id}")

            w.target_task = task
            w.mode = "work"
