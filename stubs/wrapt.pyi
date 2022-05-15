from typing import TypeVar, Callable, Any

FuncT = TypeVar('FuncT', bound=Callable[..., Any])


def synchronized(func: FuncT) -> FuncT: ...