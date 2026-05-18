from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

def format_error(e: BaseException):
    return f"{type(e).__name__}: {e}"

T = TypeVar("T")


@dataclass
class OpIt(Generic[T]):
    value: T
    info: str | None = None
    exc: BaseException | None = None


@dataclass
class OpInfo(Generic[T]):
    succeed: list[OpIt[T]] = field(default_factory=list)
    failed: list[OpIt[T]] = field(default_factory=list)
    skipped: list[OpIt[T]] = field(default_factory=list)

    def format(self) -> str:
        return format_op(self)


_formatters: dict[type, Callable[[Any], str]] = {str: lambda it: it}


def op_val_formatter(tp: type[T]):
    def deco(fn: Callable[[T], str]):
        _formatters[tp] = fn
        return fn
    return deco


def _get_formatter(v: Any) -> Callable[[Any], str]:
    t = type(v)
    if t in _formatters:
        return _formatters[t]
    for k, f in _formatters.items():
        if isinstance(v, k):
            return f
    return str


def format_op_it(it: OpIt[Any]) -> str:
    val_formatter = _get_formatter(it.value)
    txt = [val_formatter(it.value)]
    if it.info:
        txt.append(it.info)
    if it.exc:
        txt.append(format_error(it.exc))
    return ": ".join(txt)


def format_op(op: OpInfo[Any]):
    txt: list[str] = []
    if op.succeed:
        txt.append(f"成功 ({len(op.succeed)} 个)：")
        txt.extend(f"  - {format_op_it(it)}" for it in op.succeed)
    if op.skipped:
        txt.append(f"跳过 ({len(op.skipped)} 个)：")
        txt.extend(f"  - {format_op_it(it)}" for it in op.skipped)
    if op.failed:
        txt.append(f"失败 ({len(op.failed)} 个)：")
        txt.extend(f"  - {format_op_it(it)}" for it in op.failed)
    return "\n".join(txt) if txt else "没有执行任何操作"
