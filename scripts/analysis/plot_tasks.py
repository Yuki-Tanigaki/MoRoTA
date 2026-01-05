#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Plot tasks as a 2D scatter colored by remaining_work, with a central module depot marker."
    )
    p.add_argument("--width", type=float, required=True)
    p.add_argument("--height", type=float, required=True)
    p.add_argument("--file", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--title", type=str, default=None)

    p.add_argument("--size", type=float, default=40.0)
    p.add_argument("--alpha", type=float, default=0.9)
    p.add_argument("--annotate", action="store_true")

    # depot options
    p.add_argument("--depot", action="store_true", default=True)
    p.add_argument("--depot-x", type=float, default=None)
    p.add_argument("--depot-y", type=float, default=None)
    p.add_argument("--depot-size", type=float, default=600.0)
    p.add_argument("--depot-alpha", type=float, default=0.5)
    p.add_argument("--depot-label", type=str, default="DEPOT")
    p.add_argument("--depot-label-fontsize", type=float, default=10.0)

    return p.parse_args()


def main() -> None:
    args = parse_args()

    df = pd.read_csv(args.file)
    required_cols = {"id", "x", "y", "total_work", "remaining_work"}
    missing = required_cols - set(df.columns)
    if missing:
        raise SystemExit(f"Missing required columns: {sorted(missing)}")

    for col in ["x", "y", "total_work", "remaining_work"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if df[["x", "y", "remaining_work"]].isna().any().any():
        bad = df[df[["x", "y", "remaining_work"]].isna().any(axis=1)]
        raise SystemExit(f"Found non-numeric/NaN rows:\n{bad}")

    fig, ax = plt.subplots(figsize=(6.5, 6.5), dpi=150)

    # ==========================
    # Depot (behind tasks)
    # ==========================
    if args.depot:
        depot_x = args.width / 2 if args.depot_x is None else args.depot_x
        depot_y = args.height / 2 if args.depot_y is None else args.depot_y

        ax.scatter(
            [depot_x],
            [depot_y],
            s=args.depot_size,
            marker="D",     # diamond
            c="red",
            alpha=args.depot_alpha,
            edgecolors="none",
            zorder=0,
        )

        if args.depot_label:
            ax.annotate(
                args.depot_label,
                (depot_x, depot_y),
                textcoords="offset points",
                xytext=(8, -8),     # 右下にオフセット
                ha="left",
                va="top",
                fontsize=args.depot_label_fontsize,
                color="black",
                zorder=1,
                clip_on=False,      # ★ 見切れ防止
            )

    # ==========================
    # Tasks (front)
    # ==========================
    sc = ax.scatter(
        df["x"],
        df["y"],
        s=args.size,
        c=df["remaining_work"],
        alpha=args.alpha,
        zorder=3,
    )

    cbar = plt.colorbar(sc, ax=ax)
    cbar.set_label("workload (remaining)")

    ax.set_xlim(0, args.width)
    ax.set_ylim(0, args.height)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linewidth=0.5, zorder=2)

    if args.title:
        ax.set_title(args.title)
    else:
        ax.set_title(f"Tasks (colored by remaining_work): {args.file.name}")

    if args.annotate:
        for _, r in df.iterrows():
            ax.annotate(
                str(int(r["id"])),
                (r["x"], r["y"]),
                textcoords="offset points",
                xytext=(3, 3),
                fontsize=7,
                zorder=4,
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(args.out, bbox_inches="tight")
    plt.close(fig)

    print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()
