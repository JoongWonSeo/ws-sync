from logging import Logger
from functools import wraps

from .sync import Sync


def sync(
    key: str,
    sync_all: bool = False,
    include: dict[str, Ellipsis] = {},
    exclude: list[str] = [],
    toCamelCase: bool = False,
    send_on_init: bool = True,
    expose_running_tasks: bool = False,
    logger: Logger | None = None,
):
    """
    Register the attributes that should be synced with the frontend.

    Args:
        obj: the object whose attributes should be synced
        key: unique key for this object

        sync_all: whether to sync all non-private attributes
        include: attribute names to sync, value being either ... or a string of the key of the attribute
        exclude: list of attributes to exclude from syncing

        toCamelCase: whether to convert attribute names to camelCase
        send_on_init: whether to send the state on connection init
        expose_running_tasks: whether to expose the running tasks to the frontend
        logger: logger to use for logging
    """

    def decorator(init_func):
        def wrapper(self, *args, **kwargs):
            init_func(self, *args, **kwargs)
            self.sync = Sync(
                obj=self,
                key=key,
                sync_all=sync_all,
                include=include,
                exclude=exclude,
                toCamelCase=toCamelCase,
                send_on_init=send_on_init,
                expose_running_tasks=expose_running_tasks,
                logger=logger,
            )

        return wrapper

    return decorator


def sync_all(
    key: str,
    include: dict[str, Ellipsis] = {},
    exclude: list[str] = [],
    toCamelCase: bool = False,
    send_on_init: bool = True,
    expose_running_tasks: bool = False,
    logger: Logger | None = None,
):
    return sync(
        key=key,
        sync_all=True,
        include=include,
        exclude=exclude,
        toCamelCase=toCamelCase,
        send_on_init=send_on_init,
        expose_running_tasks=expose_running_tasks,
        logger=logger,
    )


def sync_only(
    _key: str,
    _toCamelCase: bool = False,
    _send_on_init: bool = True,
    _expose_running_tasks: bool = False,
    _logger: Logger | None = None,
    **sync_attributes: dict[str, str],
):
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


def remote_action(key: str):
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            return func(self, *args, **kwargs)

        wrapper.remote_action = key
        return wrapper

    decorator.forgot_to_call = True
    return decorator


def remote_task(key: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            return await func(self, *args, **kwargs)

        wrapper.remote_task = key
        wrapper.cancel = remote_task_cancel(key)  # syntactic sugar
        return wrapper

    decorator.forgot_to_call = True
    return decorator


def remote_task_cancel(key: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            return await func(self, *args, **kwargs)

        wrapper.remote_task_cancel = key
        return wrapper

    decorator.forgot_to_call = True
    return decorator
