from __future__ import annotations
from typing import TYPE_CHECKING, Protocol, Optional

from morota.domain import inventory
from morota.sim.agent import WorkerAgent, TaskAgent
from morota.sim.agent.depot_agent import DepotAgent

if TYPE_CHECKING:
    from morota.sim.model import ScenarioModel


class TaskSelector(Protocol):
    """
    タスク選択ポリシーのインタフェース。
    """

    def assign_tasks(self, model: ScenarioModel) -> None:
        """
        モデル内の全ワーカーに対して target_task を更新する。
        """
        ...


class NearestIncompleteTaskSelector(TaskSelector):
    """
    - 各ワーカーについて
      - まだ終わっていないタスクの中から
      - 「現在位置から最も近いタスク」を 1 つ選ぶ
      モジュールがひとつでも故障した場合は取りに戻る
    """

    def assign_tasks(self, model: ScenarioModel) -> None:
        incomplete_tasks = [t for t in model.tasks.values() if t.status != "done"]
        depot: DepotAgent = model.depot
        stock = depot.snapshot()

        for w in model.workers.values():
            if w.mode in ("go_reconstruction", "reconstruction"):
                continue
            
            deficits = w.deficits_for_declared_type()
            if len(deficits) != 0:
                if inventory.can_cover(deficits, stock):
                    w.mode = "go_reconstruction"
                    w.target_task = None
                    continue

            if not incomplete_tasks:
                w.target_task = None
                w.mode = "idle"
                continue

            best_task = min(
                incomplete_tasks,
                key=lambda t: model.distance(w.pos, t.pos),
            )

            w.target_task = best_task
            w.mode = "work"