# ---- Module 定義 ----
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Module:
    id: int          # 永続ID（cfg由来）
    type: str
    x: float
    y: float
    h: float = 0.0
    state: Literal["healthy", "failed"] = "healthy"

def build_modules_from_cfg(cfg) -> list[Module]:
    modules = []
    seen = set()

    for m in cfg.modules:
        mm = m if isinstance(m, dict) else m.__dict__
        mid = int(mm["id"])
        if mid in seen:
            raise ValueError(f"Duplicate module id in cfg.modules: {mid}")
        seen.add(mid)

        modules.append(
            Module(
                id=mid,
                type=str(mm["type"]),
                x=float(mm.get("x", 0.0)),
                y=float(mm.get("y", 0.0)),
                h=float(mm.get("h", 0.0)),
            )
        )
    return modules