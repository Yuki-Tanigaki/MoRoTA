from __future__ import annotations
from typing import TYPE_CHECKING, Protocol, Optional

from morota.sim.agent import WorkerAgent, TaskAgent

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
    """

    def assign_tasks(self, model: ScenarioModel) -> None:
        # 未完了タスクだけを対象にする
        incomplete_tasks = [t for t in model.tasks.values() if t.status != "done"]

        for w in model.workers.values():
            # すでに修理中 or 修理に向かっているならポリシー側では何もしない
            if w.mode in ("go_repair", "repairing"):
                continue

            # 故障しているなら修理に行かせる
            if w.state == "failed":
                w.mode = "go_repair"
                w.target_task = None
                continue

            # w が「未完了」と信じているタスクから最近傍を探す
            candidates = []
            for tid, tinfo in w.info_state.tasks.items():
                if tinfo.status == "done":
                    continue
                candidates.append((tid, tinfo))

            if not candidates:
                w.target_task = None
                w.mode = "idle"
                continue

            # 最近傍（推定座標ベース）
            best_tid, _ = min(
                candidates,
                key=lambda pair: model.distance(w.pos, model.tasks[pair[0]].pos),
            )

            w.target_task = model.tasks[best_tid]
            w.mode = "work"