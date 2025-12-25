from __future__ import annotations

from typing import Dict, Iterable, List, Optional
from collections import Counter

from mesa import Agent, Model
from morota.sim.module import Module

# ---- DepotAgent ----
class DepotAgent(Agent):
    """
    モジュール在庫を保持するエージェント（Mesa 3.x）。
    """

    def __init__(self, model: Model, modules: Iterable[Module]):
        super().__init__(model)

        self._stock_by_type: Dict[str, List[Module]] = {}
        self._stock_count: Counter[str] = Counter()

        self._initialize_stock(modules)

    def _initialize_stock(self, modules: Iterable[Module]) -> None:
        for m in modules:
            self._stock_by_type.setdefault(m.type, []).append(m)
            self._stock_count[m.type] += 1

    # --- 在庫参照 ---
    def count(self, module_type: str) -> int:
        return int(self._stock_count[module_type])

    def snapshot(self) -> Dict[str, int]:
        return dict(self._stock_count)

    # --- 在庫払い出し ---
    def request_modules(self, request: Dict[str, int]) -> List[Module]:
        granted: List[Module] = []

        for t, n in request.items():
            available = self._stock_by_type.get(t, [])
            take = min(n, len(available))

            for _ in range(take):
                granted.append(available.pop())

            self._stock_count[t] -= take

        return granted

    def try_reserve_all(self, request: Dict[str, int]) -> Optional[List[Module]]:
        for t, n in request.items():
            if self.count(t) < n:
                return None
        return self.request_modules(request)

    def step(self) -> None:
        pass
