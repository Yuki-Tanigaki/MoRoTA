#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Any, Optional

import pandas as pd


# 例:
# configs/20251229-1/results/l150_gp250_ga250_p50_50_modules_100_154_hard_tasks_circle_seed0000_tasks.csv
FNAME_RE = re.compile(
    r"""
    ^
    (?P<scenario>.+?)          # scenario_name 部分（可変）
    _seed(?P<seed>\d+)
    _tasks\.csv
    $
    """,
    re.VERBOSE,
)

# scenario_name から主要パラメータを雑に抜く（足りなければここを拡張）
SCENARIO_RE = re.compile(
    r"""
    l(?P<l>\d+)
    _gp(?P<gp>\d+)
    _ga(?P<ga>\d+)
    _p(?P<p1>\d+)_(?P<p2>\d+)
    _(?P<modules>modules_[^_]+)
    _(?P<setup>norm|soft|hard)
    _(?P<tasks>tasks_[^_]+)
    """,
    re.VERBOSE,
)


def parse_from_filename(path: Path) -> Dict[str, Any]:
    m = FNAME_RE.match(path.name)
    if not m:
        return {"scenario_name": path.stem, "seed": None}

    scenario = m.group("scenario")
    seed = int(m.group("seed"))

    out: Dict[str, Any] = {"scenario_name": scenario, "seed": seed}

    sm = SCENARIO_RE.search(scenario)
    if sm:
        out.update(
            {
                "l": int(sm.group("l")),
                "gp": int(sm.group("gp")),
                "ga": int(sm.group("ga")),
                "pref": f'{sm.group("p1")}_{sm.group("p2")}',
                "modules": sm.group("modules"),
                "setup": sm.group("setup"),
                "tasks": sm.group("tasks"),
            }
        )
    return out


def compute_makespan_from_tasks_csv(csv_path: Path) -> Dict[str, Any]:
    df = pd.read_csv(csv_path)

    # finished_step は空欄があり得るので数値化
    if "finished_step" not in df.columns:
        return {
            "completed": False,
            "makespan_step": None,
            "makespan_time": None,
            "num_tasks": df["task_id"].nunique() if "task_id" in df.columns else None,
            "num_done": None,
        }

    df["finished_step"] = pd.to_numeric(df["finished_step"], errors="coerce")

    if "task_id" in df.columns:
        fin = df.groupby("task_id", as_index=True)["finished_step"].max()
        num_tasks = int(fin.shape[0])
        num_done = int(fin.notna().sum())
        completed = (num_done == num_tasks)
        makespan_step: Optional[int] = int(fin.max()) if completed else None
    else:
        # task_id が無いケースへの保険（基本は無いはず）
        num_tasks = None
        num_done = int(df["finished_step"].notna().sum())
        completed = False
        makespan_step = None

    return {
        "completed": completed,
        "makespan_step": makespan_step,
        "num_tasks": num_tasks,
        "num_done": num_done,
    }


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--root",
        type=str,
        default="configs/20251229-1/results",
        help="results root (will search **/*_tasks.csv)",
    )
    ap.add_argument(
        "--time-step",
        type=float,
        default=1.0,
        help="simulation time_step (makespan_time = makespan_step * time_step)",
    )
    ap.add_argument(
        "--out",
        type=str,
        default="configs/20251229-1/summary_makespan.csv",
        help="output csv path",
    )
    ap.add_argument(
        "--xlsx",
        type=str,
        default="",
        help="optional output xlsx path (if set)",
    )
    args = ap.parse_args()

    root = Path(args.root)
    files = sorted(root.glob("**/*_tasks.csv"))

    rows = []
    for f in files:
        meta = parse_from_filename(f)
        stat = compute_makespan_from_tasks_csv(f)

        makespan_time = (
            (stat["makespan_step"] * args.time_step)
            if stat["makespan_step"] is not None
            else None
        )

        rows.append(
            {
                **meta,
                "path": f.as_posix(),
                **stat,
                "makespan_time": makespan_time,
            }
        )

    out_df = pd.DataFrame(rows)

    # 見やすい順に並べ替え（列が無い場合もあるので存在チェック）
    sort_cols = [c for c in ["completed", "makespan_step", "scenario_name", "seed"] if c in out_df.columns]
    if sort_cols:
        out_df = out_df.sort_values(sort_cols, ascending=[False, True, True, True], kind="mergesort")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False, encoding="utf-8")

    if args.xlsx:
        xlsx_path = Path(args.xlsx)
        xlsx_path.parent.mkdir(parents=True, exist_ok=True)
        out_df.to_excel(xlsx_path, index=False)

    print(f"found: {len(files)} files")
    print(f"wrote: {out_path.as_posix()}")
    if args.xlsx:
        print(f"wrote: {Path(args.xlsx).as_posix()}")


if __name__ == "__main__":
    main()
