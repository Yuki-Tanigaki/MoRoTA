from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple


Pos = Tuple[float, float]


def _safe_pos(agent_or_pos: Any) -> Pos:
    """Agent(.pos) or (x,y) -> (x,y)"""
    if hasattr(agent_or_pos, "pos"):
        p = getattr(agent_or_pos, "pos")
        return (float(p[0]), float(p[1]))
    return (float(agent_or_pos[0]), float(agent_or_pos[1]))


def _age_sum_from_info_state(info_state: Any, step: int) -> int:
    """
    info_state.workers / info_state.tasks の timestamp から
    sum(step - timestamp) を作る（timestamp が無い/None は無視）
    """
    total = 0

    def _sum_dict(d: Any) -> int:
        s = 0
        if not d:
            return 0
        # d は dict 想定（values() が使えるなら使う）
        values = d.values() if hasattr(d, "values") else d
        for info in values:
            ts = getattr(info, "timestamp", None)
            if ts is None:
                continue
            try:
                tsv = int(ts)
            except Exception:
                continue
            if step >= tsv:
                s += (step - tsv)
        return s

    total += _sum_dict(getattr(info_state, "workers", None))
    total += _sum_dict(getattr(info_state, "tasks", None))
    return total


@dataclass
class StepDataCollector:
    """
    各 step の状態を CSV に追記する軽量コレクタ。
    - workers.csv: 1行/worker/step
    - tasks.csv:   1行/task/step
    - commander.csv: 1行/step
    """
    out_dir: Path
    scenario_name: str
    prefix: str = "run"
    flush_every: int = 1  # 1なら毎step flush（安全寄り）

    # 内部状態
    _prev_pos: Dict[int, Pos] = field(default_factory=dict)
    _cum_dist: Dict[int, float] = field(default_factory=dict)
    _step_count: int = 0

    # writers
    _wf: Optional[Any] = None
    _tf: Optional[Any] = None
    _cf: Optional[Any] = None
    _w_writer: Optional[csv.DictWriter] = None
    _t_writer: Optional[csv.DictWriter] = None
    _c_writer: Optional[csv.DictWriter] = None

    def open(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)

        workers_path = self.out_dir / f"{self.scenario_name}_{self.prefix}_workers.csv"
        tasks_path = self.out_dir / f"{self.scenario_name}_{self.prefix}_tasks.csv"
        commander_path = self.out_dir / f"{self.scenario_name}_{self.prefix}_commander.csv"

        self._wf = workers_path.open("w", newline="", encoding="utf-8")
        self._tf = tasks_path.open("w", newline="", encoding="utf-8")
        self._cf = commander_path.open("w", newline="", encoding="utf-8")

        self._w_writer = csv.DictWriter(
            self._wf,
            fieldnames=[
                "step",
                "worker_id",
                "x",
                "y",
                "H",
                "cum_distance",
                "info_age_sum",
                "state",
                "mode",
                "target_task_id",
            ],
        )
        self._t_writer = csv.DictWriter(
            self._tf,
            fieldnames=[
                "step",
                "task_id",
                "remaining_work",
                "status",
                "finished_step",
            ],
        )
        self._c_writer = csv.DictWriter(
            self._cf,
            fieldnames=[
                "step",
                "info_age_sum",
            ],
        )

        self._w_writer.writeheader()
        self._t_writer.writeheader()
        self._c_writer.writeheader()

    def close(self) -> None:
        for f in (self._wf, self._tf, self._cf):
            if f is not None:
                f.flush()
                f.close()
        self._wf = self._tf = self._cf = None
        self._w_writer = self._t_writer = self._c_writer = None

    def _flush_if_needed(self) -> None:
        self._step_count += 1
        if self.flush_every <= 0:
            return
        if (self._step_count % self.flush_every) == 0:
            if self._wf: self._wf.flush()
            if self._tf: self._tf.flush()
            if self._cf: self._cf.flush()

    def collect(self, model: Any) -> None:
        """
        1 step 分を収集してCSVに追記。
        呼び出し位置は「そのstepの更新が全部終わった後」がおすすめ。
        """
        if self._w_writer is None or self._t_writer is None or self._c_writer is None:
            raise RuntimeError("StepDataCollector is not opened. Call open() first.")

        step = int(getattr(model, "steps", 0))

        # commander info freshness
        commander = getattr(model, "command_center", None)
        c_info_state = getattr(commander, "info_state", None) if commander else None
        c_age_sum = _age_sum_from_info_state(c_info_state, step) if c_info_state else 0
        self._c_writer.writerow({"step": step, "info_age_sum": c_age_sum})

        # tasks
        tasks = getattr(model, "tasks", {})
        t_values: Iterable[Any] = tasks.values() if hasattr(tasks, "values") else tasks
        for t in t_values:
            self._t_writer.writerow(
                {
                    "step": step,
                    "task_id": getattr(t, "task_id", None),
                    "remaining_work": getattr(t, "remaining_work", None),
                    "status": getattr(t, "status", None),
                    "finished_step": getattr(t, "finished_step", None),
                }
            )

        # workers
        workers = getattr(model, "workers", {})
        w_values: Iterable[Any] = workers.values() if hasattr(workers, "values") else workers
        for w in w_values:
            wid = int(getattr(w, "worker_id"))
            pos = _safe_pos(w)

            # cumulative distance
            prev = self._prev_pos.get(wid)
            if prev is None:
                self._prev_pos[wid] = pos
                self._cum_dist.setdefault(wid, 0.0)
            else:
                dx = pos[0] - prev[0]
                dy = pos[1] - prev[1]
                d = (dx * dx + dy * dy) ** 0.5
                self._cum_dist[wid] = float(self._cum_dist.get(wid, 0.0) + d)
                self._prev_pos[wid] = pos

            # fatigue H（属性名が違う可能性があるので候補を見る）
            H = None
            for cand in ("H", "fatigue", "cumulative_fatigue", "accumulated_fatigue"):
                if hasattr(w, cand):
                    H = getattr(w, cand)
                    break

            # worker info freshness
            w_info_state = getattr(w, "info_state", None)
            w_age_sum = _age_sum_from_info_state(w_info_state, step) if w_info_state else 0

            target_task = getattr(w, "target_task", None)
            target_task_id = getattr(target_task, "task_id", None) if target_task is not None else None

            self._w_writer.writerow(
                {
                    "step": step,
                    "worker_id": wid,
                    "x": pos[0],
                    "y": pos[1],
                    "H": H,
                    "cum_distance": self._cum_dist.get(wid, 0.0),
                    "info_age_sum": w_age_sum,
                    "state": getattr(w, "state", None),
                    "mode": getattr(w, "mode", None),
                    "target_task_id": target_task_id,
                }
            )

        self._flush_if_needed()