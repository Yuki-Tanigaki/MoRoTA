import inspect
from typing import Any, Type
import yaml
from morota.core.type import ModuleType
from morota.logging import build_logged_exc

def get_class_init_args(cls: Type[Any], input_data: dict[str, Any], name: str) -> dict[str, Any]:
    """ clsの __init__ 引数にinput_dataを成形 """
    signature = inspect.signature(cls.__init__)
    init_args = [param for param in signature.parameters]
    # 渡すべき引数をフィルタリング
    filtered_args = {
        k: v for k, v in input_data.items() if k in init_args
    }
    filtered_args.update({'name': name})

    return filtered_args


def load_module_types(file_path: str) -> dict[str, ModuleType]:
    """ モジュールタイプを読み込む """
    try:
        with open(file_path, 'r') as f:
            module_type_config = yaml.load(f, Loader=yaml.FullLoader)
    except FileNotFoundError as e:
        raise build_logged_exc(FileNotFoundError, f"'{e}' is not found")

    module_types = {}
    for type_name, type_data in module_type_config.items():
        filtered_args = get_class_init_args(cls=ModuleType, input_data=type_data, name=type_name)
        module_types[type_name] = ModuleType(**filtered_args)
    return module_types