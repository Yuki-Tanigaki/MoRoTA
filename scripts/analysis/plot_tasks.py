#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plot tasks as a 2D scatter colored by remaining_work.")
    p.add_argument("--width", type=float, required=True, help="Plot width (x range: 0..width)")
    p.add_argument("--height", type=float, required=True, help="Plot height (y range: 0..height)")
    p.add_argument("--file", type=Path, required=True, help="Input CSV file path")
    p.add_argument("--out", type=Path, required=True, help="Output figure path (.eps, .png, etc.)")
    p.add_argument("--title", type=str, default=None, help="Optional title")
    p.add_argument("--size", type=float, default=40.0, help="Marker size")
    p.add_argument("--alpha", type=float, default=0.9, help="Marker alpha (0..1)")
    p.add_argument("--annotate", action="store_true", help="Annotate points with task id")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    df = pd.read_csv(args.file)
    required_cols = {"id", "x", "y", "total_work", "remaining_work"}
    missing = required_cols - set(df.columns)
    if missing:
        raise SystemExit(f"Missing required columns: {sorted(missing)}")

    # numeric safety
    for col in ["x", "y", "total_work", "remaining_work"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if df[["x", "y", "remaining_work"]].isna().any().any():
        bad = df[df[["x", "y", "remaining_work"]].isna().any(axis=1)]
        raise SystemExit(f"Found non-numeric/NaN rows in x/y/remaining_work:\n{bad}")

    fig, ax = plt.subplots(figsize=(6.5, 6.5), dpi=150)

    sc = ax.scatter(
        df["x"],
        df["y"],
        s=args.size,
        c=df["remaining_work"],
        alpha=args.alpha,
    )

    cbar = plt.colorbar(sc, ax=ax)
    cbar.set_label("remaining_work")

    ax.set_xlim(0, args.width)
    ax.set_ylim(0, args.height)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linewidth=0.5)

    if args.title is not None:
        ax.set_title(args.title)
    else:
        ax.set_title(f"Tasks (colored by remaining_work): {args.file.name}")

    if args.annotate:
        # 小さめ文字で ID を付与
        for _, r in df.iterrows():
            ax.annotate(
                str(int(r["id"])),
                (r["x"], r["y"]),
                textcoords="offset points",
                xytext=(3, 3),
                fontsize=7,
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(args.out, format=args.out.suffix.lstrip("."), bbox_inches="tight")
    plt.close(fig)

    print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()
