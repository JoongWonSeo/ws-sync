import logging
import asyncio
from typing import Callable, Any

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


def toCamelCase(snake_case: str) -> str:
    """
    Example:
    hello_world -> helloWorld
    user_id -> userId
    text -> text
    """
    return uncapitalize(snake_case.title().replace("_", ""))


def uncapitalize(s: str) -> str:
    return s[:1].lower() + s[1:]


def ensure_jsonable(obj: Any) -> Any:
    """
    Recursively traverse an object and convert Pydantic models to JSON-serializable dicts.
    """
    if hasattr(obj, "model_dump") and callable(obj.model_dump):
        # Likely a Pydantic model
        return ensure_jsonable(obj.model_dump(mode="json"))
    elif isinstance(obj, dict):
        return {key: ensure_jsonable(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        # Convert sequences to lists to ensure JSON compatibility
        return [ensure_jsonable(item) for item in obj]
    else:
        # Assume other types are JSON serializable
        return obj
