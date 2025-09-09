from __future__ import annotations
import argparse, math
from typing import Optional, Tuple, List, Set
import mesa
from mesa.space import ContinuousSpace

from morota.simulator.robot import RobotAgent
from morota.simulator.task import TaskAgent

class World(mesa.Model):
    def __init__(self,
                 width: float = 20.0, height: float = 20.0,
                 robots: List[RobotAgent] = [], tasks: Set[TaskAgent] = set(),
                 task_required_capacity: Tuple[float, float] = (2.0, 4.0),
                 seed: Optional[int] = None):
        super().__init__(seed=seed)
        self.width, self.height = width, height
        self.space = ContinuousSpace(x_max=width, y_max=height, torus=False)
        self.robots = robots
        self.tasks = tasks

        # 時系列収集（Solara 可視化とも親和性の高い名前）
        self.datacollector = mesa.DataCollector(
            model_reporters={
                "TasksRemaining": lambda m: sum(1 for t in m.tasks if not t.completed),
                "TasksCompleted": lambda m: m.initial_tasks - sum(1 for t in m.tasks if not t.completed),
                "AvgTeamSize": self._avg_team_size,
                "Utilization": self._utilization,  # 取り付きロボット割合
            }
        )
        self.initial_tasks = len(self.tasks)
        self.datacollector.collect(self)

    def _avg_team_size(self) -> float:
        teams = [len(t.attached) for t in self.tasks if not t.completed]
        return (sum(teams)/len(teams)) if teams else 0.0

    def _utilization(self) -> float:
        attached = sum(1 for r in self.robots if r.state == "attached")
        return attached / len(self.robots) if self.robots else 0.0

    def step(self) -> None:
        self.agents.shuffle_do("step")  # 旧 RandomActivation 相当
        self.datacollector.collect(self)