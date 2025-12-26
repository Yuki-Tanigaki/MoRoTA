from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional
from collections import Counter

from mesa import Agent, Model
from morota.domain import inventory
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

    # --- 判定 ---
    def can_cover(self, deficits: Mapping[str, int]) -> bool:
        # snapshot を使う（生在庫は見ない）
        return inventory.can_cover(deficits, self.snapshot())

    # --- 払い出し ---
    def request_modules(self, request: Dict[str, int]) -> List[Module]:
        return inventory.request_modules(
            request=request,
            stock_by_type=self._stock_by_type,
            stock_count=self._stock_count,
        )

    def try_reserve_all(self, request: Dict[str, int]) -> Optional[List[Module]]:
        return inventory.try_reserve_all(
            request=request,
            stock_by_type=self._stock_by_type,
            stock_count=self._stock_count,
        )

    def step(self) -> None:
        pass