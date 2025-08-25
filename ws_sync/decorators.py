"""
Simple function decorators to mark attributes and methods for syncing with the frontend.

There are two types of decorators:
1. **Decorate `__init__()`**: For declaring attributes to be synced with the frontend:
    - `@sync()`: sync the specified attributes
    - `@sync_all()`: sync all (non-private) attributes by default
    - `@sync_only()`: sync only the attributes specified as keyword arguments
2. **Decorate a method**: For declaring methods to be exposed to the frontend:
    - `@remote_action("MY_ACTION")`: expose a method as an action (blocks the backend logic, non-concurrent, non-cancellable)
    - `@remote_task("MY_TASK")`: expose a method as a long-running task (non-blocking, concurrent, cancellable)
    - `@remote_task_cancel("MY_TASK")`: expose a method as a task-canceller (cancels a running task)

After decorating the `__init__()` method, the object will have a `sync` attribute that can be called to sync the object's state with the frontend, e.g. `await self.sync()`.
As you can see, the `sync` attribute is a coroutine, so you should `await` it.

*Note that private attribute means an attribute that starts with an underscore.*

Example:
```python
class Notepad:
    @sync_all("NOTEPAD")
    def __init__(self):
        self.text = ""  # will be synced
        self._private = "private"  # won't be synced, due to underscore prefix

    @property  # will be synced just like a normal attribute
    def length(self):
        return len(self.text)

    @remote_action("CLEAR")
    async def clear(self):
        self.text = ""
        await self.sync()  # sync the state to update the frontend

    @remote_task("GROW")
    async def grow(self):
        self.growing = True  # since this was not declared in __init__, it isn't registered for syncing
        while self.growing:
            self.text += "a"
            await self.sync()  # sync the state to update the frontend
            await asyncio.sleep(1)

    @grow.cancel  # syntactic sugar for remote_task_cancel("GROW")
    async def stop_grow(self):
        self.growing = False

```

More advanced example:
```python
class Calendar:
    @sync_only(
        "CAL",
        current_day=...,
        length="size",
        _toCamelCase=True,
        _expose_running_tasks=True,
    )
    def __init__(self):
        self.current_day = (
            "monday"  # will be synced as "currentDay", since _toCamelCase=True
        )
        self.length = 0  # will be synced as "size"
        self.private = None  # won't be synced, since not specified

    @remote_action("NEXT_DAY")
    async def next_day(self):
        self.current_day = "tuesday"
        await self.sync()  # sync the state to update the frontend

    @remote_task("FAST_FORWARD")
    async def fast_forward(self):
        for i in range(100):
            self.length += 1
            await self.sync(
                if_since_last=0.1
            )  # sync, but only if 0.1 seconds have passed since the last sync
        await self.sync.toast(
            "Fast forward complete!", type="success"
        )  # send a toast to the frontend

    @remote_action("IMPORT_EVENTS")
    async def import_events(self, data: bytes):  # from `sendBinary` in the frontend
        pickle.loads(data)  # do something with the data
```
"""

from collections.abc import Callable
from logging import Logger
from types import EllipsisType
from typing import overload


@overload  # Usage without parentheses
def sync[F: Callable](func: F, /) -> F: ...


@overload  # Usage with parentheses
def sync[F: Callable](
    *,
    key: str | None = None,
    sync_all: bool = False,
    include: dict[str, str | EllipsisType] | list[str] | None = None,
    exclude: list[str] | None = None,
    toCamelCase: bool | None = None,  # noqa: N803
    send_on_init: bool = True,
    expose_running_tasks: bool = False,
    logger: Logger | None = None,
) -> Callable[[F], F]: ...


def sync[F: Callable](
    func: F | None = None,
    /,
    *,
    key: str | None = None,
    sync_all: bool = False,
    include: dict[str, str | EllipsisType] | list[str] | None = None,
    exclude: list[str] | None = None,
    toCamelCase: bool | None = None,  # noqa: N803
    send_on_init: bool = True,
    expose_running_tasks: bool = False,
    logger: Logger | None = None,
) -> F | Callable[[F], F]:
    """
    Decorator for `__init__()`: Register the attributes that should be synced with the frontend.

    Args:
        func: implicitly passed when used as a decorator
        key: unique key (matching the frontend key) to identify the object.
             If None, defaults to the class name.
        sync_all: sync all non-private attributes
        include: attribute names to sync, value being either ... or a string of the key of the attribute
        exclude: list of attributes to exclude from syncing
        toCamelCase: convert attribute names to camelCase
        send_on_init: send the state on connection init
        expose_running_tasks: expose the list in the synced state as `running_tasks` or `runningTasks`
        logger: logger to use for logging
    """
    from .sync import Sync  # noqa: PLC0415

    def decorator(init_func: F) -> F:
        def wrapper(self, *args, **kwargs):  # noqa: ANN001
            init_func(self, *args, **kwargs)

            sync_key = key if isinstance(key, str) else type(self).__name__

            self.sync = Sync(
                obj=self,
                key=sync_key,
                sync_all=sync_all,
                include=include,
                exclude=exclude or [],
                toCamelCase=toCamelCase,
                send_on_init=send_on_init,
                expose_running_tasks=expose_running_tasks,
                logger=logger,
            )

        return wrapper  # type: ignore

    if func is None:  # @sync without parentheses
        return decorator
    # @sync(...) was used
    return decorator(func)


def sync_all(
    key: str | None = None,
    *,
    include: dict[str, str | EllipsisType] | list[str] | None = None,
    exclude: list[str] | None = None,
    toCamelCase: bool | None = None,  # noqa: N803
    send_on_init: bool = True,
    expose_running_tasks: bool = False,
    logger: Logger | None = None,
):
    """
    Decorator for `__init__()`: Register all non-private attributes to be synced with the frontend.

    Args:
        key: unique key (matching the frontend key) to identify the object.
             If None, defaults to the class name.
        include: attribute names to sync, value being either ... or a string of the key of the attribute
        exclude: list of attributes to exclude from syncing
        toCamelCase: convert attribute names to camelCase
        send_on_init: send the state on connection init
        expose_running_tasks: expose the list in the synced state as `running_tasks` or `runningTasks`
        logger: logger to use for logging
    """
    return sync(
        key=key,
        sync_all=True,
        include=include,
        exclude=exclude or [],
        toCamelCase=toCamelCase,
        send_on_init=send_on_init,
        expose_running_tasks=expose_running_tasks,
        logger=logger,
    )


def sync_only(
    _key: str | None = None,
    *,
    _toCamelCase: bool | None = None,  # noqa: N803
    _send_on_init: bool = True,
    _expose_running_tasks: bool = False,
    _logger: Logger | None = None,
    **sync_attributes: str | EllipsisType,
):
    """
    Decorator for `__init__()`: Register only the keyword-specified attributes to be synced with the frontend.

    Args:
        _key: unique key (matching the frontend key) to identify the object.
              If None, defaults to the class name.
        _toCamelCase: convert attribute names to camelCase
        _send_on_init: send the state on connection init
        _expose_running_tasks: expose the list in the synced state as `running_tasks` or `runningTasks`
        _logger: logger to use for logging
        **sync_attributes: attribute names to sync, value being the key of the attribute
    """
    return sync(
        key=_key,
        sync_all=False,
        include=sync_attributes,
        exclude=[],
        toCamelCase=_toCamelCase,
        send_on_init=_send_on_init,
        expose_running_tasks=_expose_running_tasks,
        logger=_logger,
    )


@overload  # Usage without parentheses
def remote_action[F: Callable](key: F) -> F: ...


@overload  # Usage with parentheses
def remote_action[F: Callable](key: str | None = None) -> Callable[[F], F]: ...


def remote_action[F: Callable](key: str | None | F = None) -> F | Callable[[F], F]:
    """
    Decorator for methods: Expose the method as an action to the frontend.

    An action is a "synchronous" method that blocks the backend logic until it completes.
    Of course, the method should be `async` to allow for non-blocking concurrency with other parallel sessions of the server.

    Args:
        key: unique key (matching the frontend key) to identify the action.
             If None, defaults to the method name.
    """

    def decorator(func: F) -> F:
        action_key = key if isinstance(key, str) else func.__name__
        func.remote_action = action_key  # type: ignore
        return func

    if callable(key):  # @remote_action without parentheses
        func = key  # key is actually the function
        return decorator(func)
    # @remote_action(...) was used
    decorator.forgot_to_call = True  # type: ignore[reportFunctionMemberAccess]
    return decorator


def find_remote_actions(cls: type) -> dict[str, Callable]:
    """
    Find all remote actions in a class.

    Returns a dictionary of action keys to the function.
    """
    actions: dict[str, Callable] = {}
    for attr_name in dir(cls):
        try:
            attr = getattr(cls, attr_name)
        except AttributeError:
            continue
        if isinstance(attr, property):
            continue
        if callable(attr) and hasattr(attr, "remote_action"):
            actions[attr.remote_action] = attr  # type: ignore[reportFunctionMemberAccess]
    return actions


@overload  # Usage without parentheses
def remote_task[F: Callable](key: F) -> F: ...


@overload  # Usage with parentheses
def remote_task[F: Callable](key: str | None = None) -> Callable[[F], F]: ...


def remote_task[F: Callable](key: str | None | F = None) -> F | Callable[[F], F]:
    """
    Decorator for methods: Expose the method as a long-running task to the frontend.

    A task is a "non-blocking" method that runs concurrently with the backend logic.
    The frontend can cancel the task at any time, so you should also implement a `@remote_task_cancel` method to cancel the task.

    Args:
        key: unique key (matching the frontend key) to identify the task.
             If None, defaults to the method name.
    """

    def decorator(func: F) -> F:
        task_key = key if isinstance(key, str) else func.__name__
        func.remote_task = task_key  # type: ignore
        func.cancel = remote_task_cancel(task_key)  # type: ignore # syntactic sugar
        return func

    if callable(key):  # @remote_task without parentheses
        func = key  # key is actually the function
        return decorator(func)
    # @remote_task(...) was used
    decorator.forgot_to_call = True  # type: ignore[reportFunctionMemberAccess]
    return decorator


def find_remote_tasks(cls: type) -> dict[str, Callable]:
    """
    Find all remote tasks in a class.

    Returns a dictionary of task keys to the function.
    """
    tasks: dict[str, Callable] = {}
    for attr_name in dir(cls):
        try:
            attr = getattr(cls, attr_name)
        except AttributeError:
            continue
        if isinstance(attr, property):
            continue
        if callable(attr) and hasattr(attr, "remote_task"):
            tasks[attr.remote_task] = attr  # type: ignore[reportFunctionMemberAccess]
    return tasks


def remote_task_cancel[F: Callable](key: str) -> Callable[[F], F]:
    """
    Decorator for methods: Expose the method as a task-canceller to the frontend.

    A task-canceller is a method that cancels a running task.
    The method `f` decorated with `@remote_task` has a corresponding cancel decorator `@f.cancel`:
    ```python
    @remote_task("MY_TASK")
    async def my_task(self): ...

    @my_task.cancel
    async def cancel_my_task(self): ...
    ```

    Args:
        key: unique key (matching the frontend key) to identify the task
    """

    def decorator(func: F) -> F:
        func.remote_task_cancel = key  # type: ignore
        return func

    decorator.forgot_to_call = True  # type: ignore[reportFunctionMemberAccess]
    return decorator


def find_remote_task_cancellers(cls: type) -> dict[str, Callable]:
    """
    Find all remote task-cancellers in a class.

    Returns a dictionary of task-canceller keys to the function.
    """
    cancellers: dict[str, Callable] = {}
    for attr_name in dir(cls):
        try:
            attr = getattr(cls, attr_name)
        except AttributeError:
            continue
        if isinstance(attr, property):
            continue
        if callable(attr) and hasattr(attr, "remote_task_cancel"):
            cancellers[attr.remote_task_cancel] = attr  # type: ignore[reportFunctionMemberAccess]
    return cancellers
