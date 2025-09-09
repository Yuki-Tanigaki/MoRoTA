from __future__ import annotations

import inspect
import logging
from typing import Optional, Type


def _caller_logger(default: Optional[logging.Logger] = None) -> logging.Logger:
    """
    呼び出し元モジュール（= __name__）のロガーを返す。
    取れない場合は default または utils.errors のロガー。
    """
    if default is not None:
        return default

    frame = inspect.currentframe()
    try:
        caller = frame.f_back if frame else None
        module_name = caller.f_globals.get("__name__", __name__) if caller else __name__
        return logging.getLogger(module_name)
    finally:
        # フレーム参照が循環参照になり得るので解放
        del frame

def build_logged_exc(
    exc_type: Type[BaseException],
    message: str,
    *msg_args,
    logger: Optional[logging.Logger] = None,
    level: int = logging.ERROR,
    extra: Optional[dict] = None,
    stacklevel: int = 2,
) -> BaseException:
    """
    ログを出してから例外オブジェクトを返す（raise は呼び出し側で行う）。

    - logger を省略すると呼び出し元モジュールのロガーを自動選択
    - message は % フォーマット（logging と同じ流儀）
    - stacklevel は「ログ上の発生位置」を呼び出し側に寄せるためのもの

    例:
        raise build_logged_exc(ValueError, "Battery exceeds: %s", name)
    """
    lg = _caller_logger(logger)

    # logging の規約に合わせて遅延フォーマット
    lg.log(level, message, *msg_args, extra=extra, stacklevel=stacklevel)

    # 例外メッセージは実際の文字列にしておく（デバッガ等で見やすい）
    try:
        rendered = message % msg_args if msg_args else message
    except Exception:
        # フォーマット失敗時でも落ちないようフォールバック
        rendered = f"{message} | args={msg_args!r}"

    return exc_type(rendered)