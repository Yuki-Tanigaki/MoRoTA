from __future__ import annotations
import argparse

from morota.config_loader import load_scenario_config
from morota.sim.model import ScenarioModel


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a single ACTA scenario (no GA).")
    parser.add_argument(
        "--scenario",
        type=str,
        required=True,
        help="Path to scenario YAML file.",
    )

    parser.add_argument(
        "--seed",
        type=int,
        required=True,
        help="Random seed for the simulation.",
    )

    parser.add_argument(
        "--log-file",
        action="store_true",
        help="Save step-wise simulation logs (CSV).",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    cfg = load_scenario_config(args.scenario)
    model = ScenarioModel(cfg, args.seed, args.log_file)

    # シミュレーション実行
    while (not model.all_tasks_done()) and model.steps < cfg.sim.max_steps:
        model.step()
    model.finalize()

    makespan = model.get_makespan()


if __name__ == "__main__":
    main()