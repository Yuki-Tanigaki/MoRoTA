from __future__ import annotations
from typing import Optional
import math
import mesa
from mesa import Agent, Model
from mesa.space import ContinuousSpace

EPS = 1e-9
def clip_pos(x, y, W, H):
    return (min(max(x, 0.0), W - EPS), min(max(y, 0.0), H - EPS))

def count_type(model: "FoodWorld", cls: type) -> int:
    return sum(1 for a in model.agents if isinstance(a, cls))


def mean_energy(model: "FoodWorld") -> float:
    vals = [a.energy for a in model.agents if isinstance(a, Walker)]
    return sum(vals) / len(vals) if vals else 0.0


class Food(Agent):
    """その場に存在するだけの“エサ”（連続空間版）"""
    def __init__(self, model: "FoodWorld", pos: tuple[float, float]):
        super().__init__(model)
        self.pos = pos

    def step(self) -> None:
        pass


class Walker(Agent):
    """ランダム歩行し、近傍の Food を食べて回復（連続空間版）"""
    def __init__(self, model: "FoodWorld", pos: tuple[float, float], energy: int = 5):
        super().__init__(model)
        self.pos = pos
        self.energy = energy

    def step(self) -> None:
        m: FoodWorld = self.model

        # ランダム移動（連続平面）
        dx, dy = m.random.uniform(-1, 1), m.random.uniform(-1, 1)
        nx = self.pos[0] + dx
        ny = self.pos[1] + dy
        self.pos = clip_pos(nx, ny, m.width, m.height)
        m.space.move_agent(self, self.pos)

        # 近傍の Food を探索して 0.5 以内なら食べる
        neighbors = m.space.get_neighbors(self.pos, radius=0.5, include_center=True)
        foods = [a for a in neighbors if isinstance(a, Food)]
        if foods:
            snack = m.random.choice(foods)
            # 先に空間から除去してからモデルから除去（順序はどちらでも動くがこちらが安全）
            m.space.remove_agent(snack)
            snack.remove()
            self.energy += m.food_energy

        # 消費＆死亡
        self.energy -= 1
        if self.energy <= 0:
            m.space.remove_agent(self)
            self.remove()


class FoodWorld(Model):
    """Mesa 3：AgentSet + DataCollector + ContinuousSpace"""
    def __init__(
        self,
        width: int = 20,
        height: int = 20,
        n_walkers: int = 10,
        n_food: int = 40,
        food_energy: int = 3,
        food_spawn: int = 0,
        seed: Optional[int] = None,
    ):
        super().__init__(seed=seed)
        self.width, self.height = float(width), float(height)
        self.space = ContinuousSpace(self.width, self.height, torus=False)
        self.food_energy = food_energy
        self.food_spawn = food_spawn

        # Walker 配置（インスタンス化 → place_agent。self.agents への手動追加は不要）
        for _ in range(n_walkers):
            x = self.random.random() * self.width
            y = self.random.random() * self.height
            pos = clip_pos(x, y, self.width, self.height)
            a = Walker(self, pos, energy=5)
            self.space.place_agent(a, pos)

        # Food 配置
        for _ in range(n_food):
            pos = (self.random.uniform(0, self.width), self.random.uniform(0, self.height))
            f = Food(self, pos)
            self.space.place_agent(f, pos)

        # 統計の収集（AgentSet をそのまま使う）
        self.datacollector = mesa.DataCollector(
            model_reporters={
                "Walkers": lambda m: count_type(m, Walker),
                "Food": lambda m: count_type(m, Food),
                "MeanEnergy": mean_energy,
            }
        )
        self.datacollector.collect(self)

    def step(self) -> None:
        # 毎ステップ Food を補充（オプション）
        for _ in range(self.food_spawn):
            pos = (self.random.uniform(0, self.width), self.random.uniform(0, self.height))
            f = Food(self, pos)
            self.space.place_agent(f, pos)

        # Mesa 3 の AgentSet スケジューラ
        self.agents.shuffle_do("step")
        self.datacollector.collect(self)
