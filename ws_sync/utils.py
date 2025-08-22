import asyncio
import logging
from collections.abc import Callable
from typing import cast

from pydantic import AliasGenerator, BaseModel

logger = logging.getLogger(__name__)


async def nonblock_call(func: Callable, *args, **kwargs):
    """
    Call a function without blocking the current thread.
    """
    if asyncio.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    else:
        logger.warning("function is not async.")
        return await asyncio.to_thread(func, *args, **kwargs)


def get_alias_function_for_class(
    target_cls: type,
) -> Callable[[str], str] | None:
    """
    Get the alias function for a pydantic BaseModel subclass. Returns None if the class is not a subclass of BaseModel.
    """
    if issubclass(target_cls, BaseModel):
        alias_gen = getattr(target_cls, "model_config", {}).get("alias_generator")
        if isinstance(alias_gen, AliasGenerator):
            fn = alias_gen.serialization_alias or alias_gen.alias
            return cast(Callable[[str], str] | None, fn)
        if callable(alias_gen):
            return cast(Callable[[str], str], alias_gen)
    return None
