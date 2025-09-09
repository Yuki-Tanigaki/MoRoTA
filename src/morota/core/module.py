from types import ModuleType
from typing import Any, Union
from numpy.typing import NDArray
import copy
import numpy as np


class Module:
    def __init__(self, module_type: ModuleType, name: str, coordinate: Union[tuple[float, float], NDArray[np.float64], list[float]], 
                 battery: float, operating_time: float, state: ModuleState):
        self._type = module_type  # モジュールの種類
        self._name = name  # モジュール名
        self._coordinate = make_coodinate_to_tuple(coordinate)  # モジュールの座標
        self._battery = battery  # 現在のバッテリー残量
        self._operating_time = operating_time  # モジュールの稼働時間
        self._state = state  # モジュールの状態
        
        if battery > module_type.max_battery:
            raise build_logged_exc(ValueError, f"Battery exceeds the maximum capacity: {name}.")
        if battery < 0.0:
            raise build_logged_exc(ValueError, f"Battery must be positive: {name}.")
        if operating_time < 0.0:
            raise build_logged_exc(ValueError, f"Operating_time must be positive: {name}.")

    @property
    def type(self) -> ModuleType:
        return self._type
    
    @type.setter
    def type(self, module_type: ModuleType) -> None:
        raise build_logged_exc(AttributeError, "Cannot modify the type of a module after initialization.")

    @property
    def name(self) -> str:
        return self._name
    
    @name.setter
    def name(self, name: str) -> None:
        raise build_logged_exc(AttributeError, "Cannot modify the name of a module after initialization.")

    @property
    def coordinate(self) -> tuple[float, float]:
        return self._coordinate

    @coordinate.setter
    def coordinate(self, coordinate: Union[tuple[float, float], NDArray[np.float64], list[float]]) -> None:
        """ モジュールの座標を更新 """
        self._coordinate = make_coodinate_to_tuple(coordinate)

    @property
    def battery(self) -> float:
        return self._battery
    
    @battery.setter
    def battery(self, battery: float) -> None:
        """ モジュールのバッテリーを更新 """
        if self.state == ModuleState.ERROR:
            raise build_logged_exc(RuntimeError, f"Try update battery of malfunctioning module: {self.name}.")
        if battery > self.type.max_battery:
            raise build_logged_exc(ValueError, f"Battery exceeds the maximum capacity: {self.name}.")
        if battery < 0.0:
            raise build_logged_exc(ValueError, f"Battery must be positive: {self.name}.")

        self._battery = battery

    @property
    def operating_time(self) -> float:
        return self._operating_time

    @operating_time.setter
    def operating_time(self, operating_time: float) -> None:
        """ モジュールの稼働量を更新 """
        if self.state == ModuleState.ERROR:
            raise build_logged_exc(RuntimeError, f"Try update operating_time of malfunctioning module: {self.name}.")
        if operating_time < 0.0:
            raise build_logged_exc(ValueError, f"Operating_time must be positive: {self.name}.")
        if operating_time < self.operating_time:
            raise build_logged_exc(ValueError, f"Operating_time less than the current operating_time: {self.name}.")

        self._operating_time = operating_time

    @property
    def state(self) -> ModuleState:
        return self._state
    
    @state.setter
    def state(self, state: ModuleState) -> None:
        """ モジュール状態の更新 """
        if self._state == ModuleState.ERROR and state != ModuleState.ERROR:
            raise build_logged_exc(RuntimeError, f"Cannot recover module from ERROR to {state.name}.")

        self._state = state
    
    def is_active(self) -> bool:
        """ モジュールが使用可能か """
        return self.state == ModuleState.ACTIVE

    def __str__(self) -> str:
        """ モジュールの簡単な情報を文字列として表示 """
        return f"Module({self.name}, {self.state.name}, Battery: {self.battery}/{self.type.max_battery})"

    def __repr__(self) -> str:
        """ デバッグ用の詳細な表現 """
        return f"Module(name={self.name}, type={self.type.name}, state={self.state.name}, battery={self.battery})"
    
    def __deepcopy__(self, memo: dict[int, Any]) -> "Module":
        if (obj := memo.get(id(self))) is not None:
            return obj

        dup = type(self)(
            self._type,
            self._name,
            copy.deepcopy(self._coordinate, memo),
            self._battery,
            self._operating_time,
            self._state
        )
        memo[id(self)] = dup
        return dup