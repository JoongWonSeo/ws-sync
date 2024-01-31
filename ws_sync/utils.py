import asyncio
from typing import Callable


async def nonblock_call(func: Callable, *args, **kwargs):
    """
    Call a function without blocking the current thread.
    """
    if asyncio.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    else:
        print("Warning: function is not async.")
        return await asyncio.to_thread(func, *args, **kwargs)
