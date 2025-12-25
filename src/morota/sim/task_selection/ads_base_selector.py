
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from morota.sim.agent import WorkerAgent, TaskAgent
from morota.sim.task_selection.task_selector import TaskSelector
from morota.utils.logging_utils import get_logger

if TYPE_CHECKING:
    from morota.sim.model import ScenarioModel

logger = get_logger(__name__)

Pos = Tuple[float, float]


def dist(a: Pos, b: Pos) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return (dx * dx + dy * dy) ** 0.5


@dataclass(frozen=True)
class Claim:
    worker_id: int
    task_id: int
    score: float
    timestamp: int  # model.steps を想定


class ADSBaseSelector(TaskSelector):
    """
    自律分散（1-hop 近傍合意）によるタスク選択。

    - トリガ:
        (T1) idle（手が空いた）になった
        (T2) healthy -> failed に遷移した
    - 各トリガで候補タスク集合を作り、score を計算して最良タスクへ claim
    - 近傍内で競合している task は score で勝者決定（同点は先着）
    - 敗者はその task を除外して次点へ（最大 max_rounds ラウンド）
    """

    def __init__(
        self,
        alpha_risk: float,
        max_rounds: int,
    ) -> None:
        self.alpha_risk = alpha_risk    # 故障リスク重み
        self.max_rounds = max_rounds    # ローカル合意の最大ラウンド数

        # 状態保持（トリガ検出用）
        self._prev_worker_state: Dict[int, str] = {}   # "healthy"/"failed"/...
        self._prev_mode: Dict[int, str] = {}           # "work"/"idle"/"go_repair"/...

        # ラウンド内で「このワーカーが除外した task」
        self._excluded: Dict[int, Set[int]] = {}

    # -------------------------
    # (T1)(T2) トリガ判定
    # -------------------------
    def _trigger(self, w: WorkerAgent) -> Tuple[bool, bool]:
        wid = w.worker_id
        state = w.state
        mode = w.mode
        
        prev_state = self._prev_worker_state.get(wid, state)
        prev_mode = self._prev_mode.get(wid, mode)

        # (T2) healthy->failed
        t2 = (prev_state == "healthy" and state == "failed")

        # (T1) 手が空いた（mode が idle になった）

        t1 = mode == "idle"
        # t1 = (prev_mode != "idle" and mode == "idle")

        # 更新
        self._prev_worker_state[wid] = state
        self._prev_mode[wid] = mode

        return t1, t2

    # -------------------------
    # 候補集合 J_i(t)
    # -------------------------
    def _build_candidates(self, w: WorkerAgent) -> List[int]:
        """
        ローカル info_state から「未完了」なタスク ID を候補にする。
        """
        cand: List[int] = []
        for tid, tinfo in w.info_state.tasks.items():
            if getattr(tinfo, "status", None) != "done":
                cand.append(tid)

        # 除外済みを落とす
        excluded = self._excluded.get(w.worker_id, set())
        cand = [tid for tid in cand if tid not in excluded]
        return cand

    # -------------------------
    # score S_{i,j}(t) = T_hat + R_hat
    # -------------------------
    def _estimate_completion_time(self, model: ACTAScenarioModel,w: WorkerAgent, task: TaskAgent) -> float:
        """
        T_hat: 移動時間 + 処理時間
        """
        speed = w.speed
        throughput = w.throughput
        speed_eta = w.speed_eta
        throughput_eta = w.throughput_eta
        fatigue_move = w.fatigue_move

        H = w.H
        p_fail = model.failure_model.failure_prob(H)
        speed_eff = (1.0 - p_fail) * speed + p_fail * (speed * speed_eta)
        move_time = dist(w.pos, task.pos) / speed_eff

        # タスク残作業量（ローカル info から取れるならそれを優先）
        tinfo = w.info_state.tasks.get(task.task_id)
        if tinfo is None:
            msg = f"ADSBaseSelector: task {task.task_id} info not found in worker {w.worker_id}'s info_state."
            logger.error(msg)
            raise ValueError(msg)
        remaining = tinfo.remaining_work

        H += fatigue_move * move_time
        p_fail = model.failure_model.failure_prob(H)
        throughput_eff = (1.0 - p_fail) * throughput + p_fail * (throughput * throughput_eta)
        work_time = remaining / throughput_eff
        return move_time + work_time

    def _estimate_risk(self, model: ACTAScenarioModel, w: WorkerAgent, task: TaskAgent) -> float:
        """
        R_hat: 情報不確実性（鮮度）
        """
        # ---- 情報鮮度 ----
        # TaskInfo.timestamp と steps との差を「古さ」とする
        freshness_pen = 0.0
        tinfo = w.info_state.tasks.get(task.task_id)
        if tinfo is None:
            msg = f"ADSBaseSelector: task {task.task_id} info not found in worker {w.worker_id}'s info_state."
            logger.error(msg)
            raise ValueError(msg)
        ts = int(tinfo.timestamp)
        freshness_pen = float(max(model.steps - ts, 0))

        return freshness_pen

    def _score(self, model: ACTAScenarioModel, w: WorkerAgent, tid: int) -> float:
        task = model.tasks.get(tid)
        if task is None:
            msg = (f"ADSBaseSelector: task {tid} not found in model.tasks "
                   f"(requested by worker {w.worker_id})."
                   )
            logger.error(msg)
            raise ValueError(msg)
        t_hat = self._estimate_completion_time(model, w, task)
        r_hat = self._estimate_risk(model, w, task)
        return float(t_hat + self.alpha_risk * r_hat)

    # -------------------------
    # 近傍構築
    # -------------------------
    def _neighbors(self, model: ACTAScenarioModel, wid: int) -> List[int]:
        w = model.workers[wid]
        res: List[int] = []
        for other in model.workers.values():
            if other.worker_id == wid:
                continue
            if dist(w.pos, other.pos) <= model.communication_range:
                res.append(other.worker_id)
        return res

    # -------------------------
    # main: assign_tasks
    # -------------------------
    def assign_tasks(self, model: ACTAScenarioModel) -> None:
        # 「除外集合」はこのステップのラウンド処理内だけで使いたいので初期化
        self._excluded = {w.worker_id: set() for w in model.workers.values()}

        # トリガが来た worker を集める
        triggered: List[int] = []
        for w in model.workers.values():
            wid = w.worker_id
            state = w.state
            mode = w.mode
            prev_state = self._prev_worker_state.get(wid, state)
            self._prev_worker_state[wid] = state
            # 既に「修理に行く途中」「修理中」ならここでは何もしない
            if getattr(w, "mode", None) in ("go_repair", "repairing"):
                continue

            # 修理
            if (prev_state == "healthy" and state == "failed"):
                w.target_task = None
                w.mode = "go_repair"
                continue
            
            # 手の空いたワーカー
            if mode == "idle":
                w.target_task = None
                triggered.append(w.worker_id)
                continue
            
            if w.target_task is None:
                msg = (
                    f"ADSBaseSelector: worker {w.worker_id} has no target_task "
                )
                logger.error(msg)
                raise ValueError(msg)
            tinfo = w.info_state.tasks.get(w.target_task.task_id)
            # 割り当てられた仕事が終わったワーカー
            if getattr(tinfo, "status", None) == "done":
                w.target_task = None
                triggered.append(w.worker_id)


        # 各ワーカーごとに近傍で競合解決を繰り返し行う
        undecided: Set[int] = set(triggered)  # 「未割当で再挑戦が必要」なワーカー集合
        for _round in range(self.max_rounds):
            if not undecided:
                break
            # ---- undecided ワーカーが「今ラウンドで欲しいタスク」を 1 つだけ提案 ----
            proposals: Dict[int, Tuple[int, float]] = {}
            for wid in list(undecided):
                w = model.workers[wid]
                cands = self._build_candidates(w)
                # 既知の未完了タスクがすべて割り当て済み
                if not cands:
                    w.target_task = None
                    w.mode = "idle"
                    undecided.discard(wid)
                    continue

                best_tid: int = cands[0]
                best_score: float = float("inf")
                for tid in cands:
                    s = self._score(model, w, tid)
                    if s < best_score:
                        best_score = s
                        best_tid = tid

                proposals[wid] = (best_tid, best_score)
            
            # proposal を順番に解決していく
            for wid, (tid, best_score) in proposals.items():
                winner_id: int = wid
                winner_score: float = best_score
                losers_this_round: List[int] = []

                # 近傍を確認：
                # 「すでに同じ tid を target_task にしている近傍」がいれば勝負
                for nb in self._neighbors(model, wid):
                    nb_w = model.workers[nb]

                    # 近傍がすでに別の tid を持っている / idle の場合は関係なし
                    if nb_w.target_task is None:
                        continue
                    if nb_w.target_task.task_id != tid:
                        continue

                    # nb が同じ tid を握っている → score 比較で勝者更新
                    nb_score = self._score(model, nb_w, tid)

                    if nb_score < winner_score:
                        # nb の方が強い：今の winner は負け側へ
                        losers_this_round.append(winner_id)
                        winner_id = nb
                        winner_score = nb_score
                    else:
                        # wid 側が強い：nb が負け側へ
                        losers_this_round.append(nb)

                # ---- 勝者を確定（ただし、すでに別の人が tid を確定させている場合に注意） ----
                winner_w = model.workers[winner_id]
                task = model.tasks.get(tid)
                if task is None:
                    msg = f"ADSBaseSelector: task {tid} not found in model.tasks."
                    logger.error(msg)
                    raise ValueError(msg)

                # winner のタスクを確定
                winner_w.target_task = task
                winner_w.mode = "work"

                # winner はこのラウンドで決着済み
                if winner_id in undecided:
                    undecided.discard(winner_id)

                # ---- 敗者処理：tid を除外して次ラウンドへ ----
                for lid in losers_this_round:
                    lw = model.workers[lid]

                    # loser が tid を握っていたなら解除（winner に負けたので）
                    lw.target_task = None
                    lw.mode = "idle"

                    # この tid は次の候補から除外（次点に行く）
                    self._excluded.setdefault(lid, set()).add(tid)

                    # 次ラウンドで再挑戦
                    undecided.add(lid)

            
