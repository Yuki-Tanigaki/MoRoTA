# src/morota/sim/agent/worker_agent.py
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Mapping, TYPE_CHECKING, Literal, Optional, Tuple
import math

from mesa import Agent, Model

from morota.config_loader import RobotTypeSpec
from morota.sim.module import Module

if TYPE_CHECKING:
    from morota.sim.agent.task_agent import TaskAgent


def infer_robot_type_from_modules(
    modules: list[Module],
    robot_types: Mapping[str, RobotTypeSpec],
    type_priority: Mapping[str, int],
    get_type_name=lambda m: m.type,
) -> Optional[str]:
    counts: dict[str, int] = {}
    for m in modules:
        t = get_type_name(m)
        counts[t] = counts.get(t, 0) + 1

    sorted_types = sorted(robot_types.keys(), key=lambda name: type_priority.get(name, 10**9))

    for rtype in sorted_types:
        req = robot_types[rtype].required_modules
        if all(counts.get(mod_type, 0) >= need for mod_type, need in req.items()):
            return rtype
    return None


class WorkerAgent(Agent):
    """
    WorkerAgent (Module.id を永続IDとして扱う版)

    重要な設計:
    - モジュールの同一性は Module.id で管理
    - 再構成では「計画」と「実行」を分離
      * _plan_swaps は depot を触らない（副作用ゼロ）
      * depot.reserve_best による候補確保は _reconstruction の開始フェーズだけで行う
      * depot への返却は _reconstruction 完了時にまとめて 1 回
    """

    def __init__(
        self,
        model: Model,
        worker_id: int,
        modules: list[Module],
        declared_type: Optional[str] = None,
    ):
        super().__init__(model)

        self.worker_id = worker_id
        self.modules: list[Module] = list(modules)
        self.declared_type = declared_type

        self.robot_type: Optional[str] = None
        self.speed: float = 0.0
        self.throughput: float = 0.0

        self.total_move_distance = 0.0
        self.target_task: Optional[TaskAgent] = None
        self.mode: Literal["work", "go_reconstruction", "reconstruction", "idle"] = "idle"
        self.duration_left: float = 0.0

        # デバッグ用：初期状態から保存則チェック
        self._refresh_capability_from_modules()

        self._reconf_deficits: Dict[str, int] = {}
        self._reconf_excess: List[Module] = []

    # ==========================================================
    # Utilities
    # ==========================================================
    def deficits_for_declared_type(self) -> Dict[str, int]:
        spec = self.model.cfg.robot_types.get(self.declared_type)
        if spec is None:
            raise KeyError(f"Unknown declared_type: {self.declared_type}")

        counts: Dict[str, int] = {}
        for m in self.modules:
            counts[m.type] = counts.get(m.type, 0) + 1

        deficits: Dict[str, int] = {}
        for mod_type, need in spec.required_modules.items():
            have = counts.get(mod_type, 0)
            if have < need:
                deficits[mod_type] = int(need) - int(have)

        return deficits

    def _refresh_capability_from_modules(self) -> None:
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
            return

        spec = cfg.robot_types[rtype]
        self.speed = float(spec.speed)
        self.throughput = float(spec.throughput)

    def _get_modules_by_type(self, module_type: str) -> List[Module]:
        return [m for m in self.modules if m.type == module_type]

    # ==========================================================
    # Fatigue / Failure
    # ==========================================================
    def _accumulate_module_fatigue(self, rates: Mapping[str, float], time: float) -> None:
        if time <= 0.0:
            return
        for m in self.modules:
            rate = float(rates.get(m.type, 0.0))
            dH = rate * time
            m.H += dH
            m.delta_H += dH

    def _update_failure(self) -> None:
        alive: list[Module] = []
        for m in self.modules:
            p_fail = self.model.failure_model.failure_prob_step(m.H, m.delta_H)
            if self.model.random.random() < p_fail:
                m.state = "failed"
            else:
                alive.append(m)
        self.modules = alive

    def _reset_module_deltaH(self) -> None:
        for m in self.modules:
            m.delta_H = 0.0

    # ==========================================================
    # Movement
    # ==========================================================
    def _move_towards(self, target_pos: Tuple[float, float], dt: float) -> Tuple[bool, float, float]:
        x, y = self.pos
        tx, ty = target_pos
        dx = tx - x
        dy = ty - y
        dist = math.hypot(dx, dy)

        if dist < 1e-8:
            return True, 0.0, dt

        max_step_dist = self.speed * dt
        rates = self.model.failure_model.fatigue("move")

        if dist <= max_step_dist:
            self.model.space.move_agent(self, (tx, ty))
            self.total_move_distance += dist

            move_time = dist / self.speed if self.speed > 0.0 else 0.0
            remaining_dt = max(dt - move_time, 0.0)
            self._accumulate_module_fatigue(rates, move_time)
            return True, move_time, remaining_dt

        if self.speed <= 0.0:
            return False, 0.0, dt

        ratio = max_step_dist / dist
        new_x = x + dx * ratio
        new_y = y + dy * ratio

        self.model.space.move_agent(self, (new_x, new_y))
        self.total_move_distance += max_step_dist
        self._accumulate_module_fatigue(rates, dt)
        return False, dt, 0.0

    # ==========================================================
    # Step
    # ==========================================================
    def step(self) -> None:
        if self.model.all_tasks_done():
            return

        # 性能更新
        self._refresh_capability_from_modules()

        # 成立してない個体は idle（再構成中を除く）
        if self.robot_type is None and self.mode != "reconstruction":
            self.mode = "idle"
            self._reset_module_deltaH()
            return

        dt = self.model.time_step

        if self.mode == "go_reconstruction":
            dt = self._move_to_depot(dt)

        if self.mode == "reconstruction":
            dt = self._reconstruction(dt)

        if self.mode == "work":
            self._step_work(dt)

        # 再構成中は故障判定しない（あなたの設計踏襲）
        if self.mode != "reconstruction":
            self._update_failure()

        self._reset_module_deltaH()

    # -------------------------------
    # Move to depot
    # -------------------------------
    def _move_to_depot(self, dt: float) -> float:
        rx, ry = self.model.depot.pos
        arrived, _, remaining_dt = self._move_towards((rx, ry), dt)
        if not arrived:
            return 0.0
        self.mode = "reconstruction"
        return remaining_dt

    # ==========================================================
    # Reconstruction execution
    # ==========================================================
    def _plan_reconstruction(self) -> None:
        """再構成開始時に、不足(deficits)と余剰(excess modules)を計算して保持するだけ。"""
        spec = self.model.cfg.robot_types.get(self.declared_type)
        if spec is None:
            raise KeyError(f"Unknown declared_type: {self.declared_type}")

        # 現在の healthy モジュール数
        counts = Counter(m.type for m in self.modules if m.state != "failed")

        # 不足
        deficits: Dict[str, int] = {}
        for t, need in spec.required_modules.items():
            have = int(counts.get(t, 0))
            need = int(need)
            if have < need:
                deficits[t] = need - have

        # 余剰（必要数を超えた分は返す。どれを返すかは単純に H が大きい順などでもOK）
        excess: List[Module] = []
        for t, have in counts.items():
            need = int(spec.required_modules.get(t, 0))
            extra = int(have) - need
            if extra <= 0:
                continue

            cand = [m for m in self.modules if m.type == t and m.state != "failed"]
            # 返すのは「疲労が大きいもの」優先（完全ランダムでもOK）
            cand.sort(key=lambda m: m.H, reverse=True)
            excess.extend(cand[:extra])

        self._reconf_deficits = deficits
        self._reconf_excess = excess


    def _reconstruction(self, dt: float) -> float:
        """
        超単純再構成:
        - 開始時: planだけ作る
        - duration 消費
        - 完了時: excess を put, deficits を take(取れない分は諦める)
        """
        # --- 開始フェーズ（1回だけ）---
        if self.duration_left <= 0.0:
            self._plan_reconstruction()
            self.duration_left = float(self.model.cfg.sim.reconstruct_duration)

        # --- 進行 ---
        used = min(dt, self.duration_left)
        self.duration_left -= used
        remaining_dt = dt - used

        # --- 完了 ---
        if self.duration_left > 0.0:
            return 0.0  # 再構成中は他の行動しない（必要なら remaining_dt を返してもOK）

        self.duration_left = 0.0
        self.mode = "idle"

        # 1) 余剰を worker から外して depot に返す
        if self._reconf_excess:
            out_ids = {m.id for m in self._reconf_excess}
            to_put = [m for m in self.modules if m.id in out_ids]
            self.modules = [m for m in self.modules if m.id not in out_ids]
            if to_put:
                self.model.depot.put(to_put)
            self._reconf_excess = []

        # 2) 不足を depot から取る（取れなければ取れた分だけ）
        if self._reconf_deficits:
            # take() は request を全部満たせないと None の実装だったはず
            got = self.model.depot.take(self._reconf_deficits)

            if got is None:
                # “無ければ無いで良い” → 何も取らず終了
                pass
            else:
                # 念のため重複 id は避ける
                owned = {m.id for m in self.modules}
                add = [m for m in got if m.id not in owned]
                self.modules.extend(add)

            self._reconf_deficits = {}

        self._refresh_capability_from_modules()
        return remaining_dt

    # ==========================================================
    # Work
    # ==========================================================
    def _step_work(self, dt: float) -> None:
        if self.target_task is None:
            self.mode = "idle"
            return

        tx, ty = self.target_task.pos
        arrived, _, remaining_dt = self._move_towards((tx, ty), dt)
        if not arrived:
            return

        if remaining_dt <= 1e-8:
            return

        if self.target_task.status != "done":
            self.target_task.add_work(self.throughput * remaining_dt)

        rates = self.model.failure_model.fatigue("work")
        self._accumulate_module_fatigue(rates, remaining_dt)