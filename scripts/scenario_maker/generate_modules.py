#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path
from typing import List


def allocate_counts(n: int, ratios: List[int]) -> List[int]:
    """
    Allocate integer counts that sum to n and are as close as possible to ratio proportions.
    Method: Largest remainder (Hamilton method).
    """
    if n < 0:
        raise ValueError("--n must be >= 0")
    if len(ratios) == 0:
        raise ValueError("--ratio must have at least one element")
    if any(r <= 0 for r in ratios):
        raise ValueError("--ratio elements must be positive integers")

    total = sum(ratios)
    # Ideal (float) allocations
    ideals = [n * r / total for r in ratios]
    floors = [int(x) for x in ideals]
    remainder = n - sum(floors)

    # Distribute remaining by largest fractional part
    fracs = [(ideals[i] - floors[i], i) for i in range(len(ratios))]
    fracs.sort(reverse=True)  # descending by fractional part
    counts = floors[:]
    for k in range(remainder):
        counts[fracs[k][1]] += 1

    return counts


def main() -> None:
    p = argparse.ArgumentParser(description="Generate configs/modules.csv")
    p.add_argument("--n", type=int, required=True, help="Total number of modules")
    p.add_argument("--width", type=float, required=True, help="Map width")
    p.add_argument("--height", type=float, required=True, help="Map height")
    p.add_argument("--out", type=Path, required=True, help="Output CSV path, e.g. configs/modules.csv")
    p.add_argument("--seed", type=int, default=0, help="Random seed (used for shuffling rows)")
    p.add_argument("--type", dest="types", nargs="+", required=True, help='Module types, e.g. Body Limb Wheel')
    p.add_argument("--ratio", nargs="+", type=int, required=True, help="Ratios aligned with --type")

    args = p.parse_args()

    if len(args.types) != len(args.ratio):
        raise SystemExit(f"--type length ({len(args.types)}) must match --ratio length ({len(args.ratio)})")

    counts = allocate_counts(args.n, args.ratio)

    # fixed center
    cx = args.width / 2.0
    cy = args.height / 2.0

    # build rows
    rows = []
    module_id = 0
    for t, c in zip(args.types, counts):
        for _ in range(c):
            rows.append({"id": module_id, "x": cx, "y": cy, "type": t, "h": 0})
            module_id += 1

    # optional: shuffle order for nicer mixing (deterministic by seed)
    rng = random.Random(args.seed)
    rng.shuffle(rows)

    # ensure parent dir exists
    args.out.parent.mkdir(parents=True, exist_ok=True)

    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "x", "y", "type", "h"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # Print summary to stdout (optional)
    summary = {t: c for t, c in zip(args.types, counts)}
    print(f"Saved: {args.out}")
    print(f"Counts: {summary} (sum={sum(counts)})")
    print(f"Center: x={cx}, y={cy}, h=0")


if __name__ == "__main__":
    main()
