#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import random
from pathlib import Path
from typing import Literal

try:
    from scipy.stats import qmc
except ImportError:
    qmc = None  # sobol を使う時だけ必須にする

Method = Literal["sobol", "lattice", "circle", "fib"]

WORK_CHOICES = [5, 10, 15]


def _radius_max(width: float, height: float) -> float:
    # 中心から「短辺の半分」を基準に、その 80% を使う
    return 0.8 * min(width, height) / 2.0


def generate_tasks_sobol(n: int, width: float, height: float, seed: int | None = None) -> list[dict[str, float]]:
    if qmc is None:
        raise SystemExit("Sobol を使うには SciPy が必要です: pip install scipy")

    rng = random.Random(seed)

    m = (n - 1).bit_length()  # ceil(log2(n))
    engine = qmc.Sobol(d=2, scramble=True, seed=seed)
    points01 = engine.random_base2(m=m)[:n]

    tasks: list[dict[str, float]] = []
    for i, (u, v) in enumerate(points01):
        x = float(u) * width
        y = float(v) * height
        total_work = float(rng.choice(WORK_CHOICES))
        tasks.append({"id": i, "x": x, "y": y, "total_work": total_work, "remaining_work": total_work})
    return tasks


def generate_tasks_lattice(n: int, width: float, height: float, seed: int | None = None) -> list[dict[str, float]]:
    rng = random.Random(seed)

    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    dx = width / cols
    dy = height / rows

    tasks: list[dict[str, float]] = []
    i = 0
    for r in range(rows):
        for c in range(cols):
            if i >= n:
                break
            x = (c + 0.5) * dx
            y = (r + 0.5) * dy
            total_work = float(rng.choice(WORK_CHOICES))
            tasks.append({"id": i, "x": x, "y": y, "total_work": total_work, "remaining_work": total_work})
            i += 1
        if i >= n:
            break
    return tasks


def generate_tasks_circle(n: int, width: float, height: float, seed: int | None = None) -> list[dict[str, float]]:
    rng = random.Random(seed)

    cx, cy = width / 2.0, height / 2.0
    R = _radius_max(width, height)

    # 開始角を seed に応じて回転させる（見た目の偏り防止）
    theta0 = rng.random() * 2.0 * math.pi

    tasks: list[dict[str, float]] = []
    for i in range(n):
        theta = theta0 + 2.0 * math.pi * (i / n)
        x = cx + R * math.cos(theta)
        y = cy + R * math.sin(theta)
        total_work = float(rng.choice(WORK_CHOICES))
        tasks.append({"id": i, "x": x, "y": y, "total_work": total_work, "remaining_work": total_work})
    return tasks


def generate_tasks_fib(n: int, width: float, height: float, seed: int | None = None) -> list[dict[str, float]]:
    rng = random.Random(seed)

    cx, cy = width / 2.0, height / 2.0
    Rmax = _radius_max(width, height)

    # 黄金角（rad）
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))  # ≈ 2.399963...
    # 全体を回転させるオフセット
    theta0 = rng.random() * 2.0 * math.pi

    tasks: list[dict[str, float]] = []
    if n == 1:
        total_work = float(rng.choice(WORK_CHOICES))
        return [{"id": 0, "x": cx, "y": cy, "total_work": total_work, "remaining_work": total_work}]

    # 半径は sqrt(i/(n-1)) で面積一様っぽく広がる → 最外周が Rmax
    for i in range(n):
        r = Rmax * math.sqrt(i / (n - 1))
        theta = theta0 + i * golden_angle
        x = cx + r * math.cos(theta)
        y = cy + r * math.sin(theta)
        total_work = float(rng.choice(WORK_CHOICES))
        tasks.append({"id": i, "x": x, "y": y, "total_work": total_work, "remaining_work": total_work})
    return tasks


def write_csv(tasks: list[dict[str, float]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["id", "x", "y", "total_work", "remaining_work"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in tasks:
            w.writerow(row)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, required=True, help="タスク数")
    ap.add_argument("--width", type=float, required=True, help="領域幅")
    ap.add_argument("--height", type=float, required=True, help="領域高さ")
    ap.add_argument("--out", type=str, required=True, help="出力CSVパス")
    ap.add_argument("--seed", type=int, default=None, help="乱数シード（再現性用）")
    ap.add_argument(
        "--method",
        type=str,
        choices=["sobol", "lattice", "circle", "fib"],
        default="sobol",
        help="配置方法 (sobol / lattice / circle / fib)",
    )
    args = ap.parse_args()

    if args.n <= 0:
        raise SystemExit("n must be > 0")
    if args.width <= 0 or args.height <= 0:
        raise SystemExit("width/height must be > 0")

    if args.method == "sobol":
        tasks = generate_tasks_sobol(args.n, args.width, args.height, seed=args.seed)
    elif args.method == "lattice":
        tasks = generate_tasks_lattice(args.n, args.width, args.height, seed=args.seed)
    elif args.method == "circle":
        tasks = generate_tasks_circle(args.n, args.width, args.height, seed=args.seed)
    elif args.method == "fib":
        tasks = generate_tasks_fib(args.n, args.width, args.height, seed=args.seed)
    else:
        raise SystemExit(f"Unknown method: {args.method}")

    write_csv(tasks, Path(args.out))


if __name__ == "__main__":
    main()