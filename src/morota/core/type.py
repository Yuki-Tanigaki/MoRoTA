from dataclasses import dataclass
from typing import ClassVar, Set
import logging
from mesa.visualization.components import AgentPortrayalStyle

from morota.logging import build_logged_exc

logger = logging.getLogger(__name__)
    
@dataclass(frozen=True, slots=True)
class ModuleType:
    name: str  # モジュールタイプ名
    max_battery: float  # 最大バッテリー容量
    portrayal: AgentPortrayalStyle  # 可視化スタイル

    _names: ClassVar[Set[str]] = set()  # クラス全体で共有する登録済み名

    def __post_init__(self):
            cls = self.__class__
            if not hasattr(cls, "_names"):
                cls._names = set()
            if self.name in cls._names:
                raise build_logged_exc(ValueError, f"'{self.name}' already exists")
            cls._names.add(self.name)

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ModuleType):
            return NotImplemented
        return self.name == other.name

@dataclass(frozen=True, slots=True)
class RobotType:
    """ ロボットの種類 """
    name: str  # ロボット名
    required_modules: dict[ModuleType, int]  # 構成に必要なモジュール数
    power_consumption: float  # ロボットの消費電力
    recharge_trigger: float  # 充電に戻るバッテリー量の基準
    portrayal: AgentPortrayalStyle  # 可視化スタイル

    _names: ClassVar[Set[str]] = set()  # クラス全体で共有する登録済み名

    def __post_init__(self):
            cls = self.__class__
            if not hasattr(cls, "_names"):
                cls._names = set()
            if self.name in cls._names:
                raise build_logged_exc(ValueError, f"'{self.name}' already exists")
            cls._names.add(self.name)

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RobotType):
            return NotImplemented
        return self.name == other.name

@dataclass(frozen=True, slots=True)
class TaskType:
    """ タスクの種類 """
    name: str  # タスク名
    total_workload: float  # 総作業量
    portrayal: AgentPortrayalStyle  # 可視化スタイル

    _names: ClassVar[Set[str]] = set()  # クラス全体で共有する登録済み名

    def __post_init__(self):
            cls = self.__class__
            if not hasattr(cls, "_names"):
                cls._names = set()
            if self.name in cls._names:
                raise build_logged_exc(ValueError, f"'{self.name}' already exists")
            cls._names.add(self.name)

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TaskType):
            return NotImplemented
        return self.name == other.name