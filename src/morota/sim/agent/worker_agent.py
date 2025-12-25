from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping, TYPE_CHECKING, Literal, Optional
import math
from mesa import Agent, Model

if TYPE_CHECKING:
    from morota.sim.agent.task_agent import TaskAgent

@dataclass(frozen=True)
class RobotPerformance:
    speed: float
    throughput: float

@dataclass(frozen=True)
class RobotTypeSpec:
    required_modules: Mapping[str, int]
    performance: RobotPerformance

def infer_robot_type_from_modules(
    modules: list,
    robot_types: Mapping[str, RobotTypeSpec],
    type_priority: Mapping[str, int],
    *,
    get_type_name=lambda m: m.type,
) -> Optional[str]:
    """
    優先度の高い順に robot_type を検証し、要件を満たした最初のタイプを返す。
    どれも満たさない場合は None を返す（performance を 0 に落とす用途）。
    """
    counts: dict[str, int] = {}
    for m in modules:
        t = get_type_name(m)
        counts[t] = counts.get(t, 0) + 1

    sorted_types = sorted(
        robot_types.keys(),
        key=lambda name: type_priority.get(name, 10**9),
    )

    for rtype in sorted_types:
        req = robot_types[rtype].required_modules
        if all(counts.get(mod_type, 0) >= need for mod_type, need in req.items()):
            return rtype

    return None

class WorkerAgent(Agent):
    def __init__(
        self,
        model: Model,
        worker_id: int,
        modules: list,
        *,
        declared_type: Optional[str] = None,
    ):
        super().__init__(model)

        self.worker_id = worker_id
        self.modules = modules
        self.declared_type = declared_type

        # マッチするタイプがあるか
        self.capability_state: Literal["valid", "unmatched"] = "unmatched"

        self.robot_type: Optional[str] = None
        self.speed: float = 0.0
        self.throughput: float = 0.0

        self.refresh_capability_from_modules()

        self.total_move_distance = 0.0
        self.target_task: Optional[TaskAgent] = None
        self.mode: Literal["work", "go_repair", "repairing", "idle"] = "idle"

    def refresh_capability_from_modules(self) -> None:
        """
        modules から “実際のタイプ” を推定し、performance を反映。
        当てはまらなければ speed/throughput を 0 にし、state を unmatched にする。
        """
        cfg = self.model.cfg

        rtype = infer_robot_type_from_modules(
            modules=self.modules,
            robot_types=cfg.robot_types,
            type_priority=cfg.type_priority,
            get_type_name=lambda m: m.type,
        )

        self.robot_type = rtype

        if rtype is None:
            self.speed = 0.0
            self.throughput = 0.0
            self.capability_state = "unmatched"
            return

        perf = cfg.robot_types[rtype].performance
        self.speed = perf.speed
        self.throughput = perf.throughput
        self.capability_state = "valid"

    def step(self) -> None:
        # 例：能力が成立してない個体を即 idle に落とすなら
        if self.capability_state != "valid":
            self.mode = "idle"
            return

        # ...通常処理...
        pass