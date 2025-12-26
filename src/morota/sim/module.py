# ---- Module 定義 ----
from dataclasses import dataclass
from typing import Literal


@dataclass
class Module:
    id: int          # 永続ID（cfg由来）
    type: str
    x: float
    y: float
    H: float = 0.0
    delta_H: float = 0.0    # 1ステップの増分
    state: Literal["healthy", "failed"] = "healthy"

def build_modules_from_cfg(cfg) -> list[Module]:
    modules = []
    seen = set()

    for m in cfg.modules:
        # dict / dataclass / 任意obj を "属性アクセス" で統一
        if isinstance(m, dict):
            module_id = m["module_id"]
            position = m["position"]
            module_type = m["module_type"]
            h = m.get("h", 0.0)
        else:
            module_id = getattr(m, "module_id")
            position = getattr(m, "position")
            module_type = getattr(m, "module_type")
            h = getattr(m, "h", 0.0)

        mid = int(module_id)
        if mid in seen:
            raise ValueError(f"Duplicate module_id in cfg.modules: {mid}")
        seen.add(mid)

        if not (isinstance(position, (tuple, list)) and len(position) == 2):
            raise ValueError(f"Invalid position for module_id={mid}: {position!r}")

        x, y = float(position[0]), float(position[1])

        modules.append(
            Module(
                id=mid,
                type=str(module_type),
                x=x,
                y=y,
                H=float(h),
            )
        )

    return modules