from __future__ import annotations

import csv
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence


@dataclass
class StepDataCollector:
    """
    ACTA向け: 各 step の各タスク進捗（残り仕事量）だけを CSV に追記する。
    - tasks.csv: 1行 / task / step
    """
    out_dir: Path
    scenario_name: str
    prefix: str = "run"
    flush_every: int = 1  # 1なら毎step flush（安全寄り）

    _tf: Optional[Any] = None
    _t_writer: Optional[csv.DictWriter] = None
    _row_count: int = 0

    def open(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)

        tasks_path = self.out_dir / f"{self.scenario_name}_{self.prefix}_tasks.csv"
        self._tf = tasks_path.open("w", newline="", encoding="utf-8")

        self._t_writer = csv.DictWriter(
            self._tf,
            fieldnames=[
                "step",
                "task_id",
                "remaining_work",
                "total_work",
                "progress",
                "status",
                "finished_step",
            ],
        )
        self._t_writer.writeheader()

    def close(self) -> None:
        if self._tf is not None:
            self._tf.flush()
            self._tf.close()
        self._tf = None
        self._t_writer = None

    def _flush_if_needed(self) -> None:
        self._row_count += 1
        if self.flush_every <= 0:
            return
        if (self._row_count % self.flush_every) == 0:
            if self._tf:
                self._tf.flush()

    def collect(self, model: Any) -> None:
        """
        1 step 分の tasks の残り仕事量を追記。
        呼び出し位置は「そのstepの更新が全部終わった後」がおすすめ。
        """
        if self._t_writer is None:
            raise RuntimeError("StepDataCollector is not opened. Call open() first.")

        step = int(getattr(model, "steps", 0))

        tasks = getattr(model, "tasks", {})
        t_values: Iterable[Any] = tasks.values() if hasattr(tasks, "values") else tasks

        for t in t_values:
            task_id = getattr(t, "task_id", None)

            remaining = getattr(t, "remaining_work", None)
            total = getattr(t, "total_work", None)

            # progress = (total - remaining) / total
            progress = None
            try:
                if total is not None and remaining is not None:
                    total_f = float(total)
                    if total_f > 0:
                        progress = (total_f - float(remaining)) / total_f
            except Exception:
                progress = None

            self._t_writer.writerow(
                {
                    "step": step,
                    "task_id": task_id,
                    "remaining_work": remaining,
                    "total_work": total,
                    "progress": progress,
                    "status": getattr(t, "status", None),
                    "finished_step": getattr(t, "finished_step", None),
                }
            )
            self._flush_if_needed()

@dataclass
class OptDataCollector:
    out_dir: Path
    scenario_name: str
    prefix: str = "run"

    _pf: Optional[Any] = None
    _cf: Optional[Any] = None
    _p_writer: Optional[csv.DictWriter] = None
    _c_writer: Optional[csv.DictWriter] = None
    _event_id: int = 0

    def open(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)

        pareto_path = self.out_dir / f"{self.scenario_name}_{self.prefix}_pareto.csv"
        chosen_path = self.out_dir / f"{self.scenario_name}_{self.prefix}_chosen.csv"

        self._pf = pareto_path.open("w", newline="", encoding="utf-8")
        self._cf = chosen_path.open("w", newline="", encoding="utf-8")

        self._p_writer = csv.DictWriter(self._pf, fieldnames=[
            "event_id","step","rank",
            "objectives_json","violation",
            "worker_types_json","routes_json","repairs_json",
        ])
        self._c_writer = csv.DictWriter(self._cf, fieldnames=[
            "event_id","step",
            "preference_json",
            "objectives_json","violation",
            "worker_types_json","routes_json","repairs_json",
        ])

        self._p_writer.writeheader()
        self._c_writer.writeheader()

    def close(self) -> None:
        for f in (self._pf, self._cf):
            if f is not None:
                f.flush()
                f.close()
        self._pf = self._cf = None
        self._p_writer = self._c_writer = None

    def _dumps(self, x: Any) -> str:
        return json.dumps(x, ensure_ascii=False, separators=(",", ":"))

    def log_optimization(
        self,
        *,
        step: int,
        pareto_front: Sequence[Any],   # Individual の列
        chosen: Any,                  # Individual
        preference: Any,              # ベクトルなど
    ) -> None:
        if self._p_writer is None or self._c_writer is None:
            raise RuntimeError("OptDataCollector is not opened. Call open() first.")

        self._event_id += 1
        eid = self._event_id

        # pareto
        for r, indiv in enumerate(pareto_front):
            self._p_writer.writerow({
                "event_id": eid,
                "step": step,
                "rank": r,
                "objectives_json": self._dumps(getattr(indiv, "objectives", None)),
                "violation": getattr(indiv, "violation", None),
                "worker_types_json": self._dumps(getattr(indiv, "worker_types", None)),
            })

        # chosen
        self._c_writer.writerow({
            "event_id": eid,
            "step": step,
            "preference_json": self._dumps(preference),
            "objectives_json": self._dumps(getattr(chosen, "objectives", None)),
            "violation": getattr(chosen, "violation", None),
            "worker_types_json": self._dumps(getattr(chosen, "worker_types", None)),
        })

        if self._pf: self._pf.flush()
        if self._cf: self._cf.flush()
