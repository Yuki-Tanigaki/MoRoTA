from __future__ import annotations
from dataclasses import dataclass, replace
from typing import Dict, List, Mapping, TYPE_CHECKING, Literal, Optional
import math
from mesa import Agent, Model

from morota.config_loader import RobotTypeSpec
from morota.sim.module import Module

if TYPE_CHECKING:
    from morota.sim.agent.task_agent import TaskAgent

def infer_robot_type_from_modules(
    modules: list,
    robot_types: Mapping[str, RobotTypeSpec],
    type_priority: Mapping[str, int],
    get_type_name=lambda m: m.type,
) -> Optional[str]:
    """
    優先度の高い順に robot_type を検証し、要件を満たした最初のタイプを返す。
    どれも満たさない場合は None を返す。
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


# =========================
# WorkerAgent (aligned to loader-side spec)
# =========================

class WorkerAgent(Agent):
    def __init__(
        self,
        model: Model,
        worker_id: int,
        modules: list[Module],
        declared_type: Optional[str] = None,
    ):
        super().__init__(model)

        self.worker_id = worker_id
        self.modules = modules
        self._reserved_modules: list = []  # 修理で確保した在庫（修理完了までロック）
        self.declared_type = declared_type

        # マッチするタイプがあるか
        self.capability_state: Literal["valid", "unmatched"] = "unmatched"

        self.robot_type: Optional[str] = None
        self.speed: float = 0.0
        self.throughput: float = 0.0

        self._refresh_capability_from_modules()

        self.total_move_distance = 0.0
        self.target_task: Optional[TaskAgent] = None
        self.mode: Literal["work", "go_reconstruction", "reconstruction", "idle"] = "idle"
        self.duration_left: float = 0.0   # 再構成までの残り時間

    # ==========================================================
    # ユーティリティ
    # ==========================================================
    def deficits_for_declared_type(self) -> Dict[str, int]:
        """
        declared_type の required_modules に対して、手持ち modules がどれだけ不足しているかを返す。
        戻り値: {module_type: 不足数}（不足がなければ空 dict）
        """
        
        spec = self.model.cfg.robot_types.get(self.declared_type)
        if spec is None:
            # declared_type 自体が未定義
            raise KeyError(f"Unknown declared_type: {self.declared_type}")

        # 手持ちを数える
        counts: Dict[str, int] = {}
        for m in self.modules:
            t = m.type
            counts[t] = counts.get(t, 0) + 1

        deficits: Dict[str, int] = {}
        for mod_type, need in spec.required_modules.items():
            have = counts.get(mod_type, 0)
            if have < need:
                deficits[mod_type] = need - have

        return deficits

    # ==========================================================
    # ヘルパー
    # ==========================================================
    def _refresh_capability_from_modules(self) -> None:
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

        spec = cfg.robot_types[rtype]
        self.speed = float(spec.speed)
        self.throughput = float(spec.throughput)
        self.capability_state = "valid"

    def _get_modules_by_type(self, module_type: str) -> List:
        """
        指定した module_type のモジュールをすべて返す
        """
        return [m for m in self.modules if m.type == module_type]

    def _accumulate_module_fatigue(self, rates: Mapping[str, float], time: float) -> None:
        """
        rates: module_type -> fatigue rate (per time)
        time : この行動に使った実時間

        - self.modules 内の各 module の h と delta_H を加算
        """
        if time <= 0.0:
            return 0.0

        for m in self.modules:
            rate = rates.get(m.type, 0.0)
            dH = rate * time
            m.H += dH
            m.delta_H += dH

    def _update_failure(self) -> None:
        """ターン開始時の H, delta_H に基づいて故障判定"""
        alive_modules = []
        for m in self.modules:
            p_fail = self.model.failure_model.failure_prob_step(m.H, m.delta_H)
            if self.model.random.random() < p_fail:
                m.state = "failed"
            else:
                alive_modules.append(m)

        self.modules = alive_modules

    def _move_towards(
        self,
        target_pos: tuple[float, float],
        dt: float,
    ) -> tuple[bool, float, float]:
        """
        target_pos に向かって最大 speed * dt だけ移動する共通処理。

        戻り値:
            arrived: 目的地に到達したか（もともと居た場合も True）
            move_time: 実際に移動に使った時間
            remaining_dt: dt - move_time （目的地に着いた後に残る時間）
        total_move_distance と 移動分の疲労度 はここで更新する
        """
        x, y = self.pos
        tx, ty = target_pos
        dx = tx - x
        dy = ty - y
        dist = math.hypot(dx, dy)

        # ほぼ同じ場所にいる → 移動なしで到達扱い
        if dist < 1e-8:
            return True, 0.0, dt

        max_step_dist = self.speed * dt
        rates = self.model.failure_model.fatigue("move")

        # 移動可能距離内なら一気に到達
        if dist <= max_step_dist:
            # 到達
            self.model.space.move_agent(self, (tx, ty))
            self.total_move_distance += dist

            move_time = dist / self.speed if self.speed > 0.0 else 0.0
            remaining_dt = max(dt - move_time, 0.0)

            # 移動による疲労
            self._accumulate_module_fatigue(rates, move_time)

            return True, move_time, remaining_dt

        # まだ到達しない → 向きだけ合わせて一歩進む
        if self.speed <= 0.0:
            # 速度0なら動けない
            return False, 0.0, dt

        ratio = max_step_dist / dist
        new_x = x + dx * ratio
        new_y = y + dy * ratio

        self.model.space.move_agent(self, (new_x, new_y))
        self.total_move_distance += max_step_dist

        # dt 時間フルに移動している
        self._accumulate_module_fatigue(rates, dt)

        return False, dt, 0.0
    
    def _reset_module_deltaH(self) -> None:
        self.modules = [replace(m, delta_H=0.0) for m in self.modules]

    def step(self) -> None:
        # 全タスクが終了済み
        if self.model.all_tasks_done():
            return

        # ロボットタイプを更新
        self._refresh_capability_from_modules()

        # ロボットとして成立してない個体は idle
        if self.capability_state != "valid" and self.mode != "reconstruction":
            self.mode = "idle"
            return

        dt = self.model.time_step
        if self.mode == "go_reconstruction":
            dt = self._move_to_deopt(dt)

        if self.mode == "reconstruction":
            dt = self._reconstruction(dt)

        if self.mode == "work":
            self._step_work(dt)

        # 故障判定
        self._update_failure()

        # delta_Hをリセット
        self._reset_module_deltaH()


    # -------------------------------
    # デポへ移動
    # -------------------------------
    def _move_to_deopt(self, dt: float) -> float:
        rx, ry = self.model.depot.pos

        arrived, move_time, remaining_dt = self._move_towards((rx, ry), dt)

        # まだ到達していないなら、このステップは移動だけ
        if not arrived:
            return 0.0
        
        # 到着していたら修理モードへ
        self.mode = "reconstruction"
        return remaining_dt


    # -------------------------------
    # 再構成
    # -------------------------------
    def _reconstruction(self, dt: float) -> float:
        # 1) まず必要量を計算
        deficits = self.deficits_for_declared_type()

        # 必要がないなら即終了
        if not deficits:
            self.mode = "idle"
            self.duration_left = 0.0
            self._reserved_modules = []
            return dt  # 何もしてないので dt 全部が残り

        # 2) 予約がまだ無いなら「修理開始」なので予約を取りに行く
        if not self._reserved_modules:
            reserved = self.model.depot.try_reserve_all(deficits)
            self.duration_left = self.model.cfg.sim.reconstruct_duration

            # 予約失敗（在庫不足）→ 修理開始できない
            if not reserved:
                self.mode = "idle"
                self.duration_left = 0.0
                self._reserved_modules = []
                return dt  # 何もしてないので dt 全部が残り

            # 予約成功 → 修理中はこの reserved を保持（在庫からは既に引かれている想定）
            self._reserved_modules = list(reserved)

        # 3) 修理時間を進める
        repair_time_used = min(dt, self.duration_left)
        self.duration_left -= repair_time_used
        remaining_dt = dt - repair_time_used

        # 4) 完了したら予約分を modules に付与
        if self.duration_left <= 0.0:
            self.mode = "idle"
            self.duration_left = 0.0

            # 予約分を実際に受け取る
            self.modules += self._reserved_modules
            self._reserved_modules = []

        return remaining_dt


    # -------------------------------
    # 移動＋作業
    # -------------------------------
    def _step_work(self, dt: float) -> None:
        # ターゲットタスクが無ければ何もしない
        if self.target_task is None:
            self.mode = "idle"
            return

        # まずタスク位置に向かって移動
        tx, ty = self.target_task.pos
        arrived, move_time, remaining_dt = self._move_towards((tx, ty), dt)

        # まだ到達していないなら、このステップは移動だけ
        if not arrived:
            return

        # ここからは「タスク地点にいる」場合の処理

        if remaining_dt <= 1e-8:
            # 到着したが作業する時間は残っていないステップ
            return

        if self.target_task.status != "done":
            self.target_task.add_work(self.throughput * remaining_dt)

        # 作業分の疲労
        rates = self.model.failure_model.fatigue("work")
        self._accumulate_module_fatigue(rates, remaining_dt)