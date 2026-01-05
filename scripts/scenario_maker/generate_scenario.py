#!/usr/bin/env python3
from __future__ import annotations

from itertools import product
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple, List

import yaml


# ----------------------------
# Base config (your toy_scenario)
# ----------------------------
def build_base_config() -> Dict[str, Any]:
    return {
        "scenario_name": "toy_scenario",
        "output_dir": "results",
        "space": {"width": 100.0, "height": 100.0},
        "sim": {
            "max_steps": 500,
            "reconstruct_duration": 10,
            "time_step": 1.0,
            "H_limit": 500,
        },
        "module_depot": {"position": [50.0, 50.0]},
        "failure_model": {
            "module": "morota.sim.failure_models",
            "class": "WeibullFailureModel",
            "params": {
                "l": 300,
                "k": 1.2,
                "fatigue_move": {"Body": 0.5, "Limb": 0.5, "Wheel": 1.0},
                "fatigue_work": {"Body": 0.5, "Limb": 1.0, "Wheel": 0.0},
            },
        },
        "configuration_planner": {
            "module": "morota.sim.configuration_planner",
            "class": "GeneticPlanner",
            "params": {
                "interval": 50,
                "num_workers_max": 10,
                "pop_size": 20,
                "generations": 1000,
                "seed": 42,
                "trials": 1,
                "preference": [0.7, 0.3],
            },
        },
        "task_allocator": {
            "module": "morota.sim.task_allocator",
            "class": "GeneticAllocator",
            "params": {
                "interval": 50,
                "pop_size": 20,
                "generations": 1000,
                "elitism_rate": 0.1,
                "L_max": 20,
                "seed": 1234,
                "trials": 1,
            },
        },
        "modules": "datasets/modules_100_244.csv",
        "robot_setup": "datasets/robot_setup_norm.yml",
        "tasks": "datasets/tasks_sobol.csv",
    }


# ----------------------------
# Helpers
# ----------------------------
def deep_copy_yaml(obj: Dict[str, Any]) -> Dict[str, Any]:
    # dependency-free "safe" deep copy for YAML-ish dict
    return yaml.safe_load(yaml.safe_dump(obj, sort_keys=False, allow_unicode=True))


def dump_yaml(cfg: Dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(
        cfg,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    out_path.write_text(text, encoding="utf-8")


def stem_tag(path_str: str) -> str:
    # "datasets/modules_100_244.csv" -> "modules_100_244"
    return Path(path_str).stem


def setup_tag(robot_setup_path: str) -> str:
    # "datasets/robot_setup_norm.yml" -> "norm"
    s = Path(robot_setup_path).stem  # robot_setup_norm
    return s.replace("robot_setup_", "")


def pref_tag(pref: List[float]) -> str:
    # [0.75,0.25] -> "p75_25"
    a = int(round(pref[0] * 100))
    b = int(round(pref[1] * 100))
    return f"p{a:02d}_{b:02d}"


def scenario_name_from_params(
    *,
    lam_l: int,
    planner_interval: int,
    allocator_interval: int,
    preference: List[float],
    modules_path: str,
    robot_setup_path: str,
    tasks_path: str,
) -> str:
    # Example:
    # l300_gp050_ga250_p75_25_modules_100_244_norm_tasks_sobol
    parts = [
        f"l{lam_l}",
        f"gp{planner_interval:03d}",
        f"ga{allocator_interval:03d}",
        pref_tag(preference),
        stem_tag(modules_path),
        setup_tag(robot_setup_path),
        stem_tag(tasks_path),
    ]
    return "_".join(parts)


# ----------------------------
# Main generation
# ----------------------------
def main() -> None:
    # --- Parameters you want to sweep ---
    ls = [150, 300]

    interval_pairs: List[Tuple[int, int]] = [
        (250, 250),
        # (250, 50),
        # (50, 250),
        # (250, 250),
    ]  # (GeneticPlanner interval, GeneticAllocator interval)

    preferences: List[List[float]] = [
        # [0.9, 0.1],
        # [0.75, 0.25],
        [0.5, 0.5],
        # [0.25, 0.75],
        # [0.1, 0.9],
    ]

    modules_list = [
        "../datasets/modules_100_154.csv",
        "../datasets/modules_100_244.csv",
        # "../datasets/modules_200_154.csv",
        # "../datasets/modules_200_244.csv",
    ]

    robot_setups = [
        "../datasets/robot_setup_norm.yml",
        # "../datasets/robot_setup_soft.yml",
        "../datasets/robot_setup_hard.yml",
    ]

    tasks_list = [
        "../datasets/tasks_sobol.csv",
        # "../datasets/tasks_lattice.csv",
        "../datasets/tasks_circle.csv",
    ]

    base = build_base_config()

    out_dir = Path("configs") / "20251229-1"
    count = 0

    for lam_l, (gp_int, ga_int), pref, modules_path, setup_path, tasks_path in product(
        ls, interval_pairs, preferences, modules_list, robot_setups, tasks_list
    ):
        cfg = deep_copy_yaml(base)

        # scenario_name auto
        sname = scenario_name_from_params(
            lam_l=lam_l,
            planner_interval=gp_int,
            allocator_interval=ga_int,
            preference=pref,
            modules_path=modules_path,
            robot_setup_path=setup_path,
            tasks_path=tasks_path,
        )
        cfg["scenario_name"] = sname

        # apply params
        cfg["failure_model"]["params"]["l"] = int(lam_l)

        cfg["configuration_planner"]["params"]["interval"] = int(gp_int)
        cfg["configuration_planner"]["params"]["preference"] = list(pref)

        cfg["task_allocator"]["params"]["interval"] = int(ga_int)

        cfg["modules"] = modules_path
        cfg["robot_setup"] = setup_path
        cfg["tasks"] = tasks_path

        # filename = scenario_name.yml
        dump_yaml(cfg, out_dir / f"{sname}.yml")
        count += 1

    print(f"Generated {count} YAML files under: {out_dir.as_posix()}")


if __name__ == "__main__":
    main()
