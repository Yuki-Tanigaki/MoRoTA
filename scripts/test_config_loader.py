# scripts/test_config_loader.py
from __future__ import annotations

import argparse
from pathlib import Path

from morota.config_loader import load_scenario_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Test config_loader.load_scenario_config()")
    parser.add_argument(
        "scenario_yaml",
        type=str,
        help="Path to scenario YAML (e.g., configs/toy_scenario.yaml)",
    )
    args = parser.parse_args()

    cfg = load_scenario_config(args.scenario_yaml)

    print("=== Scenario ===")
    print(f"scenario_name     : {cfg.scenario_name}")
    print(f"output_dir        : {cfg.output_dir}")
    print()
    print("=== Space / Sim ===")
    print(f"space (w,h)       : ({cfg.space.width}, {cfg.space.height})")
    print(f"max_steps         : {cfg.sim.max_steps}")
    print(f"time_step         : {cfg.sim.time_step}")
    print(f"interval_task_order: {cfg.sim.interval_task_order}")
    print(f"interval_robot_conf: {cfg.sim.interval_robot_conf}")
    print()
    print("=== Depot ===")
    print(f"module_depot_pos  : {cfg.module_depot_pos}")
    print()
    print("=== Failure Model ===")
    print(f"module            : {cfg.failure_model.module}")
    print(f"class             : {cfg.failure_model.class_name}")
    print(f"params            : {cfg.failure_model.params}")
    print()
    print("=== Configuration Planner ===")
    print(f"module            : {cfg.configuration_planner.module}")
    print(f"class             : {cfg.configuration_planner.class_name}")
    print(f"params            : {cfg.configuration_planner.params}")
    print()
    print("=== Task Allocator ===")
    print(f"module            : {cfg.task_allocator.module}")
    print(f"class             : {cfg.task_allocator.class_name}")
    print(f"params            : {cfg.task_allocator.params}")
    print()
    print("=== Asset Paths ===")
    print(f"modules_csv       : {cfg.modules_csv_path}")
    print(f"robot_setup_yaml  : {cfg.robot_setup_yaml_path}")
    print(f"tasks_csv         : {cfg.tasks_csv_path}")
    print()

    print("=== Loaded CSV/YAML Summary ===")
    print(f"modules count     : {len(cfg.modules)}")
    if cfg.modules:
        print(f"  first module    : {cfg.modules[0]}")
        type_counts = {}
        for m in cfg.modules:
            type_counts[m.module_type] = type_counts.get(m.module_type, 0) + 1
        print(f"  module types    : {type_counts}")

    print(f"tasks count       : {len(cfg.tasks)}")
    if cfg.tasks:
        print(f"  first task      : {cfg.tasks[0]}")
        total_work_sum = sum(t.total_work for t in cfg.tasks)
        remaining_sum = sum(t.remaining_work for t in cfg.tasks)
        print(f"  total_work sum  : {total_work_sum}")
        print(f"  remaining sum   : {remaining_sum}")

    print(f"robot modules     : {cfg.robot_modules}")
    print(f"robot_types count : {len(cfg.robot_types)}")
    if cfg.robot_types:
        print("  robot types:")
        for name, spec in cfg.robot_types.items():
            print(f"    - {name}: req={spec.required_modules}, perf=(speed={spec.speed}, throughput={spec.throughput})")

    print("\nOK: load_scenario_config() worked.")


if __name__ == "__main__":
    main()
