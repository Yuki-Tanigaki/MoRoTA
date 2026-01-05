from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml


# -----------------------------
# Specs for CSV / YAML payloads
# -----------------------------

@dataclass(frozen=True)
class ModuleSpec:
    module_id: int
    position: Tuple[float, float]
    module_type: str
    h: float


@dataclass(frozen=True)
class TaskSpec:
    task_id: int
    position: Tuple[float, float]
    total_work: float
    remaining_work: float


@dataclass(frozen=True)
class RobotTypeSpec:
    name: str
    required_modules: Dict[str, int]
    speed: float
    throughput: float


@dataclass(frozen=True)
class ComponentConfig:
    """
    configuration_planner / task_allocator など
    module + class + params の構造を持つ要素に使う
    """
    module: str
    class_name: str
    params: Dict[str, Any]


@dataclass(frozen=True)
class SpaceConfig:
    width: float
    height: float


@dataclass(frozen=True)
class SimConfig:
    max_steps: int
    reconstruct_duration: int
    time_step: float
    H_limit: int


@dataclass(frozen=True)
class ScenarioConfig:
    # --- top-level ---
    scenario_name: str
    output_dir: Path

    # --- space / sim ---
    space: SpaceConfig
    sim: SimConfig

    # --- depots ---
    module_depot_pos: Tuple[float, float]

    # --- models / planners ---
    failure_model: ComponentConfig
    configuration_planner: ComponentConfig
    task_allocator: ComponentConfig

    # --- loaded assets ---
    modules: List[ModuleSpec]               # from modules_*.csv
    robot_modules: List[str]                # from robot_setup.yaml -> modules
    robot_types: Dict[str, RobotTypeSpec]   # from robot_setup.yaml -> robot_types
    type_priority: Dict[str, int]          # from robot_setup.yaml -> type_priority
    tasks: List[TaskSpec]                   # from tasks_*.csv

    # --- raw filenames (optional convenience) ---
    modules_csv_path: Path
    robot_setup_yaml_path: Path
    tasks_csv_path: Path


# -----------------------------
# Internal helpers
# -----------------------------

def _as_xy(v: Any, *, key: str) -> Tuple[float, float]:
    if not (isinstance(v, (list, tuple)) and len(v) == 2):
        raise ValueError(f"{key} must be [x, y], got: {v!r}")
    return (float(v[0]), float(v[1]))


def _require(cfg: dict, key: str, *, where: str) -> Any:
    if key not in cfg:
        raise KeyError(f"Missing key '{key}' in {where}")
    return cfg[key]


def _load_modules_from_csv(csv_path: Path) -> List[ModuleSpec]:
    modules: List[ModuleSpec] = []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            modules.append(
                ModuleSpec(
                    module_id=int(row["id"]),
                    position=(float(row["x"]), float(row["y"])),
                    module_type=str(row["type"]),
                    h=float(row.get("h", 0.0)),
                )
            )
    return modules


def _load_tasks_from_csv(csv_path: Path) -> List[TaskSpec]:
    tasks: List[TaskSpec] = []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_work = float(row["total_work"])
            remaining_work = float(row.get("remaining_work", total_work))
            tasks.append(
                TaskSpec(
                    task_id=int(row["id"]),
                    position=(float(row["x"]), float(row["y"])),
                    total_work=total_work,
                    remaining_work=remaining_work,
                )
            )
    return tasks


def _load_robot_setup(yaml_path: Path) -> Tuple[List[str], Dict[str, RobotTypeSpec], Dict[str, int]]:
    with yaml_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    robot_modules = list(_require(cfg, "modules", where=str(yaml_path)))
    robot_types_cfg = _require(cfg, "robot_types", where=str(yaml_path))
    type_priority_cfg = _require(cfg, "type_priority", where=str(yaml_path))

    robot_types: Dict[str, RobotTypeSpec] = {}
    if not isinstance(robot_types_cfg, dict):
        raise TypeError(f"'robot_types' must be a mapping in {yaml_path}")
    if not isinstance(type_priority_cfg, dict):
        raise TypeError(f"'type_priority' must be a mapping in {yaml_path}")
    
    type_priority: Dict[str, int] = {str(k): int(v) for k, v in type_priority_cfg.items()}

    for name, spec in robot_types_cfg.items():
        if not isinstance(spec, dict):
            raise TypeError(f"robot_types.{name} must be a mapping in {yaml_path}")

        required_modules = dict(_require(spec, "required_modules", where=f"{yaml_path}:robot_types.{name}"))
        perf = _require(spec, "performance", where=f"{yaml_path}:robot_types.{name}")
        if not isinstance(perf, dict):
            raise TypeError(f"robot_types.{name}.performance must be a mapping in {yaml_path}")
        if str(name) not in type_priority:
            raise KeyError(f"Missing priority for robot type '{name}' in {yaml_path}:type_priority")

        robot_types[name] = RobotTypeSpec(
            name=str(name),
            required_modules={str(k): int(v) for k, v in required_modules.items()},
            speed=float(_require(perf, "speed", where=f"{yaml_path}:robot_types.{name}.performance")),
            throughput=float(_require(perf, "throughput", where=f"{yaml_path}:robot_types.{name}.performance")),
        )

    extra = set(type_priority.keys()) - set(robot_types.keys())
    if extra:
        raise KeyError(f"type_priority has unknown robot types not in robot_types: {sorted(extra)} in {yaml_path}")

    return robot_modules, robot_types, type_priority


def _load_component_config(cfg: dict, *, where: str) -> ComponentConfig:
    module = str(_require(cfg, "module", where=where))
    class_name = str(_require(cfg, "class", where=where))
    params = cfg.get("params", {}) or {}
    if not isinstance(params, dict):
        raise TypeError(f"{where}.params must be a mapping, got {type(params)}")
    return ComponentConfig(module=module, class_name=class_name, params=dict(params))


def _load_failure_model_config(cfg: dict, *, where: str) -> ComponentConfig:
    module = str(_require(cfg, "module", where=where))
    class_name = str(_require(cfg, "class", where=where))
    params = cfg.get("params", {}) or {}
    if not isinstance(params, dict):
        raise TypeError(f"{where}.params must be a mapping, got {type(params)}")
    return ComponentConfig(module=module, class_name=class_name, params=dict(params))


# -----------------------------
# Public API
# -----------------------------

def load_scenario_config(yaml_path: str | Path) -> ScenarioConfig:
    """
    Load scenario YAML (toy_scenario 形式) and related CSV/YAML assets.

    Expected scenario YAML keys (based on your example):
      - scenario_name, output_dir
      - space: { width, height }
      - sim: { max_steps, interval_task_order, interval_robot_conf, time_step }
      - module_depot: { position: [x, y] }
      - failure_model: { module, class, params }
      - configuration_planner: { module, class, params }
      - task_allocator: { module, class, params }
      - modules: "modules_....csv"
      - robot_setup: "robot_setup_....yaml"
      - tasks: "tasks_....csv"
    """
    yaml_path = Path(yaml_path)
    with yaml_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    base_dir = yaml_path.parent

    # --- top-level ---
    scenario_name = str(_require(cfg, "scenario_name", where=str(yaml_path)))

    output_dir_raw = _require(cfg, "output_dir", where=str(yaml_path))
    # output_dir は相対なら scenario.yaml の場所基準にする
    output_dir = Path(output_dir_raw)
    if not output_dir.is_absolute():
        output_dir = (base_dir / output_dir).resolve()

    # --- space ---
    space_cfg = _require(cfg, "space", where=str(yaml_path))
    space = SpaceConfig(
        width=float(_require(space_cfg, "width", where=f"{yaml_path}:space")),
        height=float(_require(space_cfg, "height", where=f"{yaml_path}:space")),
    )

    # --- sim ---
    sim_cfg = _require(cfg, "sim", where=str(yaml_path))
    sim = SimConfig(
        max_steps=int(_require(sim_cfg, "max_steps", where=f"{yaml_path}:sim")),
        reconstruct_duration=float(_require(sim_cfg, "reconstruct_duration", where=f"{yaml_path}:sim")),
        time_step=float(_require(sim_cfg, "time_step", where=f"{yaml_path}:sim")),
        H_limit=int(_require(sim_cfg, "H_limit", where=f"{yaml_path}:sim")),
    )

    # --- depots ---
    depot_cfg = _require(cfg, "module_depot", where=str(yaml_path))
    module_depot_pos = _as_xy(_require(depot_cfg, "position", where=f"{yaml_path}:module_depot"), key="module_depot.position")

    # --- failure_model / planners ---
    failure_model = _load_failure_model_config(
        _require(cfg, "failure_model", where=str(yaml_path)),
        where=f"{yaml_path}:failure_model",
    )
    configuration_planner = _load_component_config(
        _require(cfg, "configuration_planner", where=str(yaml_path)),
        where=f"{yaml_path}:configuration_planner",
    )
    task_allocator = _load_component_config(
        _require(cfg, "task_allocator", where=str(yaml_path)),
        where=f"{yaml_path}:task_allocator",
    )

    # --- asset paths (relative to scenario yaml) ---
    modules_csv_path = (base_dir / str(_require(cfg, "modules", where=str(yaml_path)))).resolve()
    robot_setup_yaml_path = (base_dir / str(_require(cfg, "robot_setup", where=str(yaml_path)))).resolve()
    tasks_csv_path = (base_dir / str(_require(cfg, "tasks", where=str(yaml_path)))).resolve()

    # --- load assets ---
    modules = _load_modules_from_csv(modules_csv_path)
    robot_modules, robot_types, type_priority = _load_robot_setup(robot_setup_yaml_path)
    tasks = _load_tasks_from_csv(tasks_csv_path)

    return ScenarioConfig(
        scenario_name=scenario_name,
        output_dir=output_dir,
        space=space,
        sim=sim,
        module_depot_pos=module_depot_pos,
        failure_model=failure_model,
        configuration_planner=configuration_planner,
        task_allocator=task_allocator,
        modules=modules,
        robot_modules=robot_modules,
        robot_types=robot_types,
        type_priority=type_priority,
        tasks=tasks,
        modules_csv_path=modules_csv_path,
        robot_setup_yaml_path=robot_setup_yaml_path,
        tasks_csv_path=tasks_csv_path,
    )
