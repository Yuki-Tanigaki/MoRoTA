from __future__ import annotations
from typing import Dict, List, Mapping, MutableMapping, Optional, TypeVar

T = TypeVar("T")  # Module 型などを想定


def can_cover(
    deficits: Mapping[str, int],
    stock_count: Mapping[str, int],
) -> bool:
    """
    在庫 stock_count で deficits（不足分）をすべて補えるか（純粋判定）
    """
    return all(stock_count.get(t, 0) >= n for t, n in deficits.items())


def request_modules(
    request: Mapping[str, int],
    stock_by_type: MutableMapping[str, List[T]],
    stock_count: MutableMapping[str, int],
) -> List[T]:
    """
    request に従って在庫からモジュールを払い出す（破壊的）

    前提:
    - request の妥当性チェックは呼び出し側で行う
    """
    granted: List[T] = []

    for t, n in request.items():
        available = stock_by_type.get(t, [])
        take = min(n, len(available))

        for _ in range(take):
            granted.append(available.pop())

        stock_count[t] = stock_count.get(t, 0) - take

    return granted


def try_reserve_all(
    request: Mapping[str, int],
    stock_by_type: MutableMapping[str, List[T]],
    stock_count: MutableMapping[str, int],
) -> Optional[List[T]]:
    """
    request をすべて満たせる場合のみ払い出す。
    満たせない場合は None を返す。
    """
    if not can_cover(request, stock_count):
        return None

    return request_modules(
        request=request,
        stock_by_type=stock_by_type,
        stock_count=stock_count,
    )
