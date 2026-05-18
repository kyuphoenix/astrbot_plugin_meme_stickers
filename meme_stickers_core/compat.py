from contextlib import nullcontext
from typing import Any, Callable, Dict, Generic, Iterable, Iterator, TypeVar

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


def chunks(seq: Iterable[T], size: int) -> Iterator[list[T]]:
    buf: list[T] = []
    for x in seq:
        buf.append(x)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


def deep_merge(a: dict[str, Any], b: dict[str, Any], skip_merge_paths: set[str] | None = None) -> dict[str, Any]:
    out = dict(a)
    skip = skip_merge_paths or set()
    for k, v in b.items():
        if k in skip:
            out[k] = v
            continue
        if isinstance(out.get(k), dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v, skip_merge_paths=None)
        else:
            out[k] = v
    return out


class TypeDecoCollector(Generic[T]):
    def __init__(self):
        self._map: Dict[type, Callable[..., Any]] = {}

    def __call__(self, typ: type):
        def deco(fn: F) -> F:
            self._map[typ] = fn
            return fn
        return deco

    def get_from_type_or_instance(self, inst_or_type: Any, default=None):
        t = inst_or_type if isinstance(inst_or_type, type) else type(inst_or_type)
        if t in self._map:
            return self._map[t]
        for k, v in self._map.items():
            if isinstance(inst_or_type, k):
                return v
        if default is not None:
            return default
        raise KeyError(t)
