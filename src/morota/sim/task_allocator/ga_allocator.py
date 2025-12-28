from __future__ import annotations
from typing import TYPE_CHECKING, List, Optional, Tuple

from morota.opt.task_order.expected_makespan import ExpectedMakespanEvaluator
from morota.opt.task_order.representation import Individual
from morota.sim.agent.task_agent import TaskAgent
from morota.sim.agent.worker_agent import WorkerAgent
from morota.sim.task_allocator.ga_core import SimpleGA
if TYPE_CHECKING:
    from morota.sim.model import ScenarioModel
from morota.sim.task_allocator.base_allocator import TaskAllocator




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

        # 一度 GA を回した結果のベスト個体を保持しておく
        self._best_individual: Optional[Individual] = None

        # 各ワーカーごとに「どの current_work まで repair を発動済みか」を覚えておく
        self._last_repair_index: dict[int, int] = {}

    # --------------------------------------------------
    # GA を実行してベスト個体（計画）を作る
    # --------------------------------------------------
    def _ensure_plan(self, model: ScenarioModel) -> None:
        """
        GA を複数回実行し、目的値（makespan）の中央値となる試行結果を採用する。
        """
        num_workers = len(model.workers)
        num_tasks = len(model.tasks)

        # Evaluator は毎回 new しなくてもよい（evaluate 内で使い回す）
        makespan_evaluator = ExpectedMakespanEvaluator(model)

        def evaluate(ind: Individual) -> list[float]:
            makespan = makespan_evaluator(ind)[0]
            return [float(makespan)]  # 小さいほど良い

        results: List[Tuple[Tuple[float, float], int, Individual]] = []

        base_seed = self.seed
        for t in range(self.trials):
            trial_seed = base_seed + t

            ga = SimpleGA(
                num_workers=num_workers,
                num_tasks=num_tasks,
                L_max=self.L_max,
                pop_size=self.pop_size,
                generations=self.generations,
                elitism_rate=self.elitism_rate,
                evaluate=evaluate,
                seed=trial_seed,
            )

            ind = ga.run()
            obj = tuple(float(x) for x in ind.objectives[:2])  # (makespan, outside)
            results.append((obj, trial_seed, ind))

        # 目的値で辞書順ソートして中央値を取る（makespanとoutsideの和）
        results.sort(key=lambda x: x[0][0])

        median_idx = len(results) // 2
        median_obj, median_seed, median_ind = results[median_idx]

        self._best_individual = median_ind


    # --------------------------------------------------
    # ヘルパ: current_work を計算する
    # --------------------------------------------------
    def _compute_current_work_for_worker(
        self,
        worker: WorkerAgent,
        indiv: Individual,
    ) -> int:
        """
        worker が持つローカル情報 (worker.info_state.tasks) に基づいて、
        indiv.routes[worker_id] の先頭から何個 'done' と認識しているかを返す。
        """
        wid = worker.worker_id
        route = indiv.routes[wid]

        current_work = 0
        for task_id in route:
            tinfo = worker.info_state.tasks.get(task_id)

            # ローカル情報がない / done だと分からない → そこから先は未完了扱い
            if tinfo is None or tinfo.status != "done":
                break

            current_work += 1

        return current_work

    # --------------------------------------------------
    # TaskSelector インタフェース実装
    # --------------------------------------------------
    def assign_tasks(self, model: ScenarioModel) -> None:
        # --- GA 計画を用意 ---
        if (model.steps - 1) % self.interval == 0:
            self._ensure_plan(model)
        indiv = self._best_individual

        if indiv is None:
            msg = "GABasedTaskSelector: No plan available."
            raise ValueError(msg)

        tasks_by_id: dict[int, TaskAgent] = model.tasks

        for w in model.workers.values():
            worker_id = w.worker_id
            # 既に「修理に行く途中」「修理中」ならここでは何もしない
            if getattr(w, "mode", None) in ("go_repair", "repairing"):
                continue

            # このワーカーのルート
            route = indiv.routes[worker_id]

            if not route:
                w.target_task = None
                w.mode = "idle"
                continue

            # current_work を確認
            current_work = self._compute_current_work_for_worker(
                worker=w,
                indiv=indiv,
            )

            # ルートのタスクがすべて完了
            if current_work >= len(route):
                w.target_task = None
                w.mode = "idle"
                continue

            # RepairFlagsを取得
            repair_flags = indiv.repairs[worker_id]
            if not repair_flags:
                msg = "GA individual has empty repair flags for worker_id=%s" % worker_id
                raise ValueError(msg)

            # その worker が「直近で修理を発動した current_work」
            last_triggered = self._last_repair_index.get(worker_id, None)  # None=未発動

            go_repair = (
                0 <= current_work < len(repair_flags)
                and repair_flags[current_work]
                and last_triggered != current_work
            )

            if go_repair:
                w.target_task = None
                w.mode = "go_repair"
                self._last_repair_index[worker_id] = current_work
                continue

            # 次の仕事に向かう
            next_task_id = route[current_work]
            task = tasks_by_id.get(next_task_id)

            if task is None:
                msg = "Task id %s not found for worker_id=%s" % (next_task_id, worker_id)
                raise ValueError(msg)

            w.target_task = task
            w.mode = "work"