from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal, Mapping, Protocol


class FailureModel(Protocol):
    """WorkerAgentが使う故障モデルのインターフェース."""

    def fatigue(self, action: str) -> float:
        """
        疲労蓄積
        """
        ...

    def failure_prob(self, H: float) -> float:
        """
        累積疲労度 に対する故障確率を返す。

        Parameters
        ----------
        H : float
            累積疲労度
        """
        ...

    def failure_prob_step(self, H: float, delta_H: float) -> float:
        """
        このステップで増加した疲労度 に対する故障確率を返す。

        Parameters
        ----------
        delta_H : float
            このステップで増加した疲労度
        """
        ...

@dataclass
class WeibullFailureModel:
    l: float  # スケール（H単位で直接：H=lamで約63%故障）
    k: float    # 形状
    fatigue_move: Mapping[str, float]
    fatigue_work: Mapping[str, float]
    Action = Literal["move", "work"]

    def fatigue(self, action: Action) -> Mapping[str, float]:
        if action == "move":
            return self.fatigue_move
        if action == "work":
            return self.fatigue_work
        raise ValueError(f"Unknown action: {action!r}")

    def failure_prob(self, H: float) -> float:
        if H <= 0 or self.l <= 0 or self.k <= 0:
            return 0.0
        return 1.0 - math.exp(- (H / self.l) ** self.k)

    def failure_prob_step(self, H: float, delta_H: float) -> float:
        if delta_H <= 0 or self.l <= 0 or self.k <= 0:
            return 0.0

        def F(x: float) -> float:
            return 1.0 - math.exp(- (x / self.l) ** self.k)

        F_old = F(H)
        F_new = F(H + delta_H)

        if F_old >= 1.0:
            return 1.0
        return (F_new - F_old) / (1.0 - F_old)