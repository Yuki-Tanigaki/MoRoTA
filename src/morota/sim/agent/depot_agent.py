# src/morota/sim/agent/depot_agent.py
from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional

from mesa import Agent, Model

from morota.sim.module import Module


class DepotAgent(Agent):
    """
    Super-simple DepotAgent.

    - 在庫は Module.id の一意性だけ保証
    - 操作は「取り出す(take)」「返す(put)」のみ
    - 失敗モジュール(state=="failed")は返却しても捨てる（必要なら変えてOK）
    """

    def __init__(self, model: Model, modules: Iterable[Module]):
        super().__init__(model)
        self._by_type: Dict[str, List[Module]] = {}
        self._ids: set[int] = set()
        self._init_stock(modules)

    # ----------------------------
    # init
    # ----------------------------
    def _init_stock(self, modules: Iterable[Module]) -> None:
        for m in modules:
            mid = int(m.id)
            if mid in self._ids:
                raise RuntimeError(f"[Depot] duplicate Module.id in initial stock: id={mid}")
            self._ids.add(mid)
            self._by_type.setdefault(m.type, []).append(m)

    # ----------------------------
    # read-only helpers (optional)
    # ----------------------------
    def count(self, module_type: str) -> int:
        return len(self._by_type.get(module_type, []))

    def snapshot(self) -> Dict[str, int]:
        return {t: len(lst) for t, lst in self._by_type.items()}

    def can_cover(self, request: Mapping[str, int]) -> bool:
        # request: {type: k}
        for t, k in request.items():
            if k < 0:
                raise ValueError(f"[Depot] negative request: {t}={k}")
            if len(self._by_type.get(t, [])) < int(k):
                return False
        return True

    # ----------------------------
    # withdraw
    # ----------------------------
    def take(self, request: Mapping[str, int]) -> Optional[List[Module]]:
        """
        request を満たせるなら取り出して返す。足りなければ None（在庫は変えない）。
        取り出し順は単純に末尾から pop（= FIFO/LIFOのこだわり無し）。
        """
        # まず可否判定（ここでは在庫を変えない）
        if not self.can_cover(request):
            return None

        got: List[Module] = []
        for t, k in request.items():
            k = int(k)
            if k <= 0:
                continue
            lst = self._by_type.get(t)
            if not lst:
                # can_cover を通っているので本来起きないが保険
                raise RuntimeError(f"[Depot] internal error: list missing for type={t}")

            for _ in range(k):
                m = lst.pop()  # 単純に末尾
                mid = int(m.id)
                if mid not in self._ids:
                    raise RuntimeError(f"[Depot] internal error: id={mid} not in ids while taking")
                self._ids.remove(mid)
                got.append(m)

        return got

    # ----------------------------
    # return
    # ----------------------------
    def put(self, modules: List[Module]) -> None:
        """
        モジュールを在庫へ返却する。
        - state=="failed" は捨てる（戻さない）
        - 二重返却（id重複）は即エラー
        """
        for m in modules:
            if m.state == "failed":
                continue

            mid = int(m.id)
            if mid in self._ids:
                raise RuntimeError(f"[Depot] duplicate return of Module.id={mid}")

            self._ids.add(mid)
            self._by_type.setdefault(m.type, []).append(m)

    def step(self) -> None:
        pass
