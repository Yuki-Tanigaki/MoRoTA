#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

# PyYAML が無い環境もあり得るので、エラーメッセージを明確にする
try:
    import yaml
except ImportError as e:
    raise SystemExit("PyYAML が必要です: pip install pyyaml") from e

# scipy があれば NNLS を使う。無ければ簡易フォールバック（クリップ付き最小二乗）
try:
    from scipy.optimize import nnls
except Exception:
    nnls = None


@dataclass
class FitResult:
    coef: Dict[str, float]        # Body/Limb/Wheel の係数（単位モジュールあたりの寄与）
    intercept: float              # 切片（モデルで説明できない/相互作用などの吸収）
    y_pred: np.ndarray            # 各ロボットの予測値


def load_config(path: str) -> Tuple[List[str], Dict[str, dict]]:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    modules = cfg.get("modules")
    robot_types = cfg.get("robot_types")
    if not isinstance(modules, list) or not isinstance(robot_types, dict):
        raise ValueError("YAML 形式が想定と違います: modules(list), robot_types(dict) が必要です。")

    # modules は ['Body','Limb','Wheel'] のような想定
    for m in modules:
        if not isinstance(m, str):
            raise ValueError("modules は文字列の配列である必要があります。")

    return modules, robot_types


def build_design_matrix(
    modules: List[str],
    robot_types: Dict[str, dict],
) -> Tuple[List[str], np.ndarray, np.ndarray, np.ndarray]:
    """
    X: [n_robots, 1 + n_modules]  (先頭列は切片=1)
    y_speed, y_throughput: [n_robots]
    """
    names: List[str] = []
    X_rows: List[List[float]] = []
    y_speed: List[float] = []
    y_throughput: List[float] = []

    for rname, rdef in robot_types.items():
        req = rdef.get("required_modules", {})
        perf = rdef.get("performance", {})

        if "speed" not in perf or "throughput" not in perf:
            raise ValueError(f"{rname} に performance.speed / performance.throughput がありません。")

        row = [1.0]  # intercept
        for m in modules:
            row.append(float(req.get(m, 0)))

        names.append(rname)
        X_rows.append(row)
        y_speed.append(float(perf["speed"]))
        y_throughput.append(float(perf["throughput"]))

    X = np.array(X_rows, dtype=float)
    ys = np.array(y_speed, dtype=float)
    yt = np.array(y_throughput, dtype=float)
    return names, X, ys, yt


def fit_nnls_with_intercept(X: np.ndarray, y: np.ndarray) -> FitResult:
    """
    非負制約付き最小二乗で、[intercept, Body, Limb, Wheel] を推定する。
    - scipy があれば nnls を利用
    - 無ければ最小二乗→非負クリップの簡易近似（粗いが「尤もらしい」寄与には使える）
    """
    if nnls is not None:
        w, _ = nnls(X, y)
    else:
        # fallback: 通常の最小二乗 → 非負にクリップ（厳密NNLSではない）
        w, *_ = np.linalg.lstsq(X, y, rcond=None)
        w = np.clip(w, 0.0, None)

    y_pred = X @ w
    return FitResult(
        coef={"Body": float(w[1]), "Limb": float(w[2]), "Wheel": float(w[3])},
        intercept=float(w[0]),
        y_pred=y_pred,
    )


def contribution_rates_per_robot(
    modules: List[str],
    robot_names: List[str],
    X: np.ndarray,
    fit: FitResult,
) -> Dict[str, Dict[str, float]]:
    """
    各ロボットに対して、Body/Limb/Wheel の寄与率を計算。
    寄与額 = count * coef
    寄与率 = 寄与額 / (Body+Limb+Wheel の寄与額の合計)
    ※切片は「説明できない分」として除外し、3モジュール内で正規化する
    """
    rates: Dict[str, Dict[str, float]] = {}
    # X: [intercept, Body, Limb, Wheel]
    for i, rname in enumerate(robot_names):
        counts = {"Body": X[i, 1], "Limb": X[i, 2], "Wheel": X[i, 3]}
        contrib = {m: counts[m] * fit.coef[m] for m in modules}
        total = sum(contrib.values())

        if total <= 1e-12:
            # モジュール寄与がゼロ（ありえにくいが保険）
            rates[rname] = {m: 0.0 for m in modules}
        else:
            rates[rname] = {m: float(contrib[m] / total) for m in modules}

    return rates


def overall_contribution_rate(
    modules: List[str],
    X: np.ndarray,
    fit: FitResult,
    weight: np.ndarray | None = None,
) -> Dict[str, float]:
    """
    全体の寄与率（ロボット平均）。
    weight を指定すると重み付き（例: 予測性能で重み付け）になる。
    """
    if weight is None:
        weight = np.ones(X.shape[0], dtype=float)

    # 各ロボットの寄与額(count*coef)を積み上げて正規化
    totals = {m: 0.0 for m in modules}
    for i in range(X.shape[0]):
        w = float(weight[i])
        totals["Body"] += w * (X[i, 1] * fit.coef["Body"])
        totals["Limb"] += w * (X[i, 2] * fit.coef["Limb"])
        totals["Wheel"] += w * (X[i, 3] * fit.coef["Wheel"])

    s = sum(totals.values())
    if s <= 1e-12:
        return {m: 0.0 for m in modules}
    return {m: float(totals[m] / s) for m in modules}


def print_report(
    modules: List[str],
    robot_names: List[str],
    ys: np.ndarray,
    yt: np.ndarray,
    fit_speed: FitResult,
    fit_throughput: FitResult,
    X: np.ndarray,
) -> None:
    def fmt(d: Dict[str, float]) -> str:
        return ", ".join([f"{k}={v:.4f}" for k, v in d.items()])

    print("=== Fitted coefficients (non-negative additive model) ===")
    print("[speed]")
    print(f"  intercept={fit_speed.intercept:.4f}")
    print(f"  per-module: {fmt(fit_speed.coef)}")
    print("[throughput]")
    print(f"  intercept={fit_throughput.intercept:.4f}")
    print(f"  per-module: {fmt(fit_throughput.coef)}")
    print()

    # 各ロボットの実測 vs 予測
    print("=== Actual vs Predicted ===")
    print("robot\tactual_speed\tpred_speed\tactual_thr\tpred_thr")
    for i, r in enumerate(robot_names):
        print(
            f"{r}\t{ys[i]:.3f}\t\t{fit_speed.y_pred[i]:.3f}\t\t{yt[i]:.3f}\t\t{fit_throughput.y_pred[i]:.3f}"
        )
    print()

    # 寄与率（ロボット別）
    rs = contribution_rates_per_robot(modules, robot_names, X, fit_speed)
    rt = contribution_rates_per_robot(modules, robot_names, X, fit_throughput)

    print("=== Contribution rates per robot (normalized within modules; intercept excluded) ===")
    print("[speed]")
    for r in robot_names:
        print(f"  {r}: " + ", ".join([f"{m}={rs[r][m]*100:.1f}%" for m in modules]))
    print("[throughput]")
    for r in robot_names:
        print(f"  {r}: " + ", ".join([f"{m}={rt[r][m]*100:.1f}%" for m in modules]))
    print()

    # 全体寄与率（予測値で重み付け：性能が大きい機体の影響を強める）
    overall_s = overall_contribution_rate(modules, X, fit_speed, weight=fit_speed.y_pred)
    overall_t = overall_contribution_rate(modules, X, fit_throughput, weight=fit_throughput.y_pred)

    print("=== Overall contribution rates (weighted by predicted metric; intercept excluded) ===")
    print("[speed]      " + ", ".join([f"{m}={overall_s[m]*100:.1f}%" for m in modules]))
    print("[throughput] " + ", ".join([f"{m}={overall_t[m]*100:.1f}%" for m in modules]))


def main() -> None:
    ap = argparse.ArgumentParser(description="Estimate module contribution rates from a robot config YAML.")
    ap.add_argument("config", help="Path to YAML config (modules + robot_types)")
    args = ap.parse_args()

    modules, robot_types = load_config(args.config)
    # このツールは Body/Limb/Wheel を想定しているが、modules の順序に追従する
    if len(modules) != 3:
        raise SystemExit("このサンプル実装は modules が3種（例: Body,Limb,Wheel）であることを想定しています。")

    robot_names, X, ys, yt = build_design_matrix(modules, robot_types)

    # モジュール名が Body/Limb/Wheel でなくても動くが、出力はそのままになる
    # 係数推定（speed と throughput は別に推定）
    fit_s = fit_nnls_with_intercept(X, ys)
    fit_t = fit_nnls_with_intercept(X, yt)

    print_report(modules, robot_names, ys, yt, fit_s, fit_t, X)


if __name__ == "__main__":
    main()
