#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict

import yaml


def compute_metric(
    req: Dict[str, float],
    coef: Dict[str, float],
    intercept: float,
) -> float:
    # req: required_modules の辞書
    # coef: {"Body":..., "Limb":..., "Wheel":...}
    return float(
        intercept
        + req.get("Body", 0) * coef.get("Body", 0.0)
        + req.get("Limb", 0) * coef.get("Limb", 0.0)
        + req.get("Wheel", 0) * coef.get("Wheel", 0.0)
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate robot performance from per-module contributions.")
    ap.add_argument("config", help="Input YAML path")
    ap.add_argument("--out", default="", help="Output YAML path (default: print to stdout)")

    # speed: metric = s0 + sB*B + sL*L + sW*W
    ap.add_argument("--s0", type=float, default=0.0, help="speed intercept")
    ap.add_argument("--sB", type=float, default=0.5, help="speed coef for Body")
    ap.add_argument("--sL", type=float, default=0.3, help="speed coef for Limb")
    ap.add_argument("--sW", type=float, default=0.6, help="speed coef for Wheel")

    # throughput: metric = t0 + tB*B + tL*L + tW*W
    ap.add_argument("--t0", type=float, default=0.0, help="throughput intercept")
    ap.add_argument("--tB", type=float, default=1.0, help="throughput coef for Body")
    ap.add_argument("--tL", type=float, default=0.8, help="throughput coef for Limb")
    ap.add_argument("--tW", type=float, default=0.2, help="throughput coef for Wheel")

    # 0未満を丸める/小数桁
    ap.add_argument("--clamp_min", type=float, default=0.0, help="Clamp metric to be >= this value")
    ap.add_argument("--digits", type=int, default=2, help="Round digits in output")

    args = ap.parse_args()

    cfg_path = Path(args.config)
    cfg: Dict[str, Any] = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    robot_types = cfg.get("robot_types", {})
    if not isinstance(robot_types, dict):
        raise SystemExit("robot_types が見つかりません。")

    speed_coef = {"Body": args.sB, "Limb": args.sL, "Wheel": args.sW}
    thr_coef = {"Body": args.tB, "Limb": args.tL, "Wheel": args.tW}

    for rname, rdef in robot_types.items():
        req = rdef.get("required_modules", {})
        if not isinstance(req, dict):
            raise SystemExit(f"{rname}: required_modules が不正です。")

        s = compute_metric(req, speed_coef, args.s0)
        t = compute_metric(req, thr_coef, args.t0)

        # clamp
        s = max(args.clamp_min, s)
        t = max(args.clamp_min, t)

        # round
        s = round(s, args.digits)
        t = round(t, args.digits)

        rdef["performance"] = {"speed": s, "throughput": t}

    out_text = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)

    if args.out:
        Path(args.out).write_text(out_text, encoding="utf-8")
    else:
        print(out_text)


if __name__ == "__main__":
    main()
