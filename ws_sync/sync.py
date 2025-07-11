import asyncio
import base64
import warnings
from collections.abc import Awaitable, Callable
from copy import deepcopy
from logging import Logger
from time import time
from types import EllipsisType
from typing import Any, Literal, get_type_hints

import jsonpatch
from pydantic import AliasGenerator, BaseModel, TypeAdapter

from .session import session_context
from .utils import toCamelCase as toCamelCaseFn


# Event Type Helpers
def set_event(key: str):
    """State has been set"""
    return f"_SET:{key}"


def get_event(key: str):
    """State has been requested"""
    return f"_GET:{key}"


def patch_event(key: str):
    """State has been patched"""
    return f"_PATCH:{key}"


def action_event(key: str):
    """Action has been dispatched"""
    return f"_ACTION:{key}"


def task_start_event(key: str):
    """Task has been started"""
    return f"_TASK_START:{key}"


def task_cancel_event(key: str):
    """Task has been cancelled"""
    return f"_TASK_CANCEL:{key}"


def toast_event():
    """Toast message has been sent"""
    return "_TOAST"


# FIXME: OBSOLETE
def download_event():
    """File has been sent for download"""
    return "_DOWNLOAD"


# TODO: for key-space, global key prefix and context manager function in Sync

ToastType = Literal["default", "message", "info", "success", "warning", "error"]


class Sync:
    """
    Register an object's attributes to this class to sync them with the frontend.
    """

    @classmethod
    def all(
        cls,
        obj: object,
        key: str,
        include: dict[str, str | EllipsisType] | list[str] | None = None,
        exclude: list[str] | None = None,
        toCamelCase: bool | None = None,
        send_on_init: bool = True,
        expose_running_tasks: bool = False,
        logger: Logger | None = None,
        actions: dict[str, Callable[..., Any]] | None = None,
        tasks: dict[str, Callable[..., Awaitable[Any]]] | None = None,
        task_cancels: dict[str, Callable[..., Awaitable[Any]]] | None = None,
    ) -> "Sync":
        return cls(
            obj=obj,
            key=key,
            sync_all=True,
            include=include,
            exclude=exclude or [],
            toCamelCase=toCamelCase,
            send_on_init=send_on_init,
            expose_running_tasks=expose_running_tasks,
            logger=logger,
            actions=actions,
            tasks=tasks,
            task_cancels=task_cancels,
        )

    @classmethod
    def only(
        cls,
        _obj: object,
        _key: str,
        _toCamelCase: bool | None = None,
        _send_on_init: bool = True,
        _expose_running_tasks: bool = False,
        _logger: Logger | None = None,
        _actions: dict[str, Callable[..., Any]] | None = None,
        _tasks: dict[str, Callable[..., Awaitable[Any]]] | None = None,
        _task_cancels: dict[str, Callable[..., Awaitable[Any]]] | None = None,
        **sync_attributes: str | EllipsisType,
    ) -> "Sync":
        return cls(
            obj=_obj,
            key=_key,
            sync_all=False,
            include=sync_attributes,
            exclude=[],
            toCamelCase=_toCamelCase,
            send_on_init=_send_on_init,
            expose_running_tasks=_expose_running_tasks,
            logger=_logger,
            actions=_actions,
            tasks=_tasks,
            task_cancels=_task_cancels,
        )

    def __init__(
        self,
        obj: object,
        key: str,
        sync_all: bool = False,
        include: dict[str, str | EllipsisType] | list[str] | None = None,
        exclude: list[str] | None = None,
        toCamelCase: bool | None = None,
        send_on_init: bool = True,
        expose_running_tasks: bool = False,
        logger: Logger | None = None,
        actions: dict[str, Callable[..., Any]] | None = None,
        tasks: dict[str, Callable[..., Awaitable[Any]]] | None = None,
        task_cancels: dict[str, Callable[..., Awaitable[Any]]] | None = None,
    ):
        """
        Register the attributes that should be synced with the frontend.

        Args:
            obj: the object whose attributes should be synced
            key: unique key for this object

            sync_all: whether to sync all non-private attributes
            include: attribute names to sync, value being either ... or a string of the key of the attribute
            exclude: list of attributes to exclude from syncing

            toCamelCase: convert attribute names to camelCase. Must be ``None`` for
                Pydantic models, which should configure ``alias_generator``
            send_on_init: whether to send the state on connection init
            expose_running_tasks: whether to expose the running tasks to the frontend
            logger: logger to use for logging

            actions: action handlers for each action type, each taking the data of the action as keyword arguments
            tasks: either a dict of task factories for each task type, each returning a coroutine to be used as a task, or a tuple of (task_start_handler, task_cancel_handler)
            task_cancels: a dict of task cancel handlers for each task type


        """
        self.obj = obj
        self.key = key
        self.send_on_init = send_on_init
        self.casing_func: Callable[[str], str]
        if isinstance(obj, BaseModel):
            assert toCamelCase is None, (
                "Use model_config.alias_generator for Pydantic models"
            )
            alias_gen = type(obj).model_config.get("alias_generator")
            if isinstance(alias_gen, AliasGenerator):
                self.casing_func = (
                    alias_gen.serialization_alias or alias_gen.alias or (lambda x: x)
                )
            else:
                self.casing_func = alias_gen or (lambda x: x)
        else:
            self.casing_func = toCamelCaseFn if toCamelCase else (lambda x: x)
        self.task_exposure = (
            self.casing("running_tasks") if expose_running_tasks else None
        )
        self.logger = logger

        # Convert list[str] include to dict format
        if isinstance(include, list):
            include = {attr: ... for attr in include}
        include = include or {}
        exclude = exclude or []

        # Validate that BaseModel objects don't use custom sync keys
        if isinstance(obj, BaseModel) and include:
            for attr_name, sync_key in include.items():
                if sync_key is not ...:
                    raise AssertionError(
                        f"Custom sync key '{sync_key}' for attribute '{attr_name}' is not allowed for Pydantic models. "
                        "Use pydantic's alias_generator in model_config instead."
                    )

        self.session = session_context.get()
        assert self.session, "No session set, use the session.session_context variable!"

        # ========== Find action handlers ========== #
        actions = actions or {}

        # find decorated actions
        for attr in dir(type(obj)):
            if isinstance(
                getattr(type(obj), attr), property
            ):  # ignore properties to prevent infinite recursion
                continue
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=DeprecationWarning)
                    action = getattr(obj, attr)
                if callable(action) and hasattr(action, "remote_action"):
                    actions[action.remote_action] = action  # type: ignore[attr-defined]
            except AttributeError:
                pass

        self.actions = self._create_action_handler(actions)

        # ========== Find task handlers ========== #
        tasks = tasks or {}
        task_cancels = task_cancels or {}

        # find decorated tasks and cancel tasks
        for attr in dir(type(obj)):
            if isinstance(
                getattr(type(obj), attr), property
            ):  # ignore properties to prevent infinite recursion
                continue
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=DeprecationWarning)
                    task = getattr(obj, attr)
                if callable(task):
                    if hasattr(task, "remote_task"):
                        tasks[task.remote_task] = task  # type: ignore[attr-defined]
                    if hasattr(task, "remote_task_cancel"):
                        task_cancels[task.remote_task_cancel] = task  # type: ignore[attr-defined]
            except AttributeError:
                pass

        if tasks:
            self.tasks, self.task_cancels = self._create_task_handlers(
                tasks, task_cancels
            )
        else:
            self.tasks, self.task_cancels = None, None

        # store running tasks
        self.running_tasks: dict[str, asyncio.Task[Any]] = {}

        # ========== Find attributes to sync ========== #
        self.sync_attributes = {}

        # observe all non-private attributes
        if sync_all:
            if isinstance(obj, BaseModel):
                # Include regular fields
                for field in type(obj).model_fields:
                    if field in exclude:
                        continue
                    self.sync_attributes[field] = self.casing(field)

                # Include computed fields
                for field in type(obj).model_computed_fields:
                    if field in exclude:
                        continue
                    self.sync_attributes[field] = self.casing(field)
            else:
                for attr_name in dir(obj):
                    try:
                        attr = getattr(obj, attr_name)
                    except AttributeError:
                        continue
                    if (
                        attr_name in exclude
                        or attr_name.startswith("_")
                        or callable(attr)
                        or isinstance(attr, Sync)
                    ):
                        continue

                    self.sync_attributes[attr_name] = self.casing(attr_name)

        # observe specific attributes
        for attr_name, sync_key in include.items():
            self.sync_attributes[attr_name] = (
                self.casing(attr_name) if sync_key is ... else sync_key
            )

        # create reverse-lookup for patching
        self.key_to_attr: dict[str, str] = {
            key: attr for attr, key in self.sync_attributes.items()
        }

        # ========== Debugging ========== #
        if self.logger:
            self.logger.debug(f"{self.key}: Syncing {self.sync_attributes}")
            self.logger.debug(f"{self.key}: Actions {actions}")
            self.logger.debug(f"{self.key}: Tasks {tasks}")
            self.logger.debug(f"{self.key}: Task Cancels {task_cancels}")

        assert include.keys().isdisjoint(exclude), "Attribute in both include & exclude"
        assert all(a in dir(obj) for a in self.sync_attributes), "Attribute not found"
        assert all(e in dir(obj) for e in exclude), "Excluded attribute not found"
        # assert (
        #     len(self.sync_attributes) + expose_running_tasks > 0
        # ), "No attributes to sync"
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            for attr in dir(obj):
                try:
                    if hasattr(getattr(obj, attr), "forgot_to_call"):
                        raise Exception(
                            f'You did @remote_action instead of @remote_action(...) for attribute "{attr}"'
                        )
                except AttributeError:
                    pass

        # ========== Type Adapters ========== #
        # Create TypeAdapters once for each synced attribute with type hints
        self.type_adapters: dict[str, TypeAdapter[Any]] = {}
        try:
            type_hints = get_type_hints(type(obj))
            for attr_name in self.sync_attributes:
                if attr_name in type_hints:
                    try:
                        self.type_adapters[attr_name] = TypeAdapter(
                            type_hints[attr_name]
                        )
                    except (TypeError, ValueError) as e:
                        if self.logger:
                            self.logger.warning(
                                f"Failed to create TypeAdapter for {attr_name}: {e}"
                            )
        except (TypeError, NameError) as e:
            if self.logger:
                self.logger.warning(f"Failed to get type hints: {e}")

        # ========== State Management ========== #
        # the snapshot is the exact state that the frontend has, for patching
        self.state_snapshot: dict[str, Any] = self._snapshot()
        self._last_sync: float | None = None  # timestamp of last sync
        self._register_event_handlers()

    # ========== High-Level: Sync and Actions ========== #
    async def sync(self, if_since_last: float | None = None):
        """
        Sync all registered attributes.

        Args:
            if_since_last: only sync if the last sync was before this many seconds
        """
        if not self.session.is_connected:
            return
        t = time()
        if if_since_last and self._last_sync and t - self._last_sync < if_since_last:
            return

        # calculate patch
        prev = self.state_snapshot
        self.state_snapshot = self._snapshot()
        patch = jsonpatch.make_patch(prev, self.state_snapshot).patch

        if len(patch) > 0:
            await self.session.send(patch_event(self.key), patch)
            self._last_sync = t

    async def __call__(
        self,
        if_since_last: float | None = None,
        toast: str | None = None,
        type: ToastType = "default",
    ):
        """@public
        Sync all registered attributes.

        Args:
            if_since_last: only sync if the last sync was before this many seconds
            toast: toast message to send after syncing
            type: toast type
        """
        await self.sync(if_since_last=if_since_last)
        if toast:
            await self.toast(toast, type=type)

    async def send_action(self, action: dict[str, Any]):
        """
        Send an action to the frontend.
        """
        await self.session.send(action_event(self.key), action)

    async def send_binary(self, metadata: dict[str, Any], data: bytes):
        """
        Send binary data to the frontend, along with metadata.
        This is a subset of an action, but with bytes data always included.
        """
        await self.session.send_binary(action_event(self.key), metadata, data)

    async def toast(
        self, *messages, type: ToastType = "default", logger: Logger | None = None
    ) -> str:
        """
        Send a toast message to the frontend.
        Returns the sent message content, so that you can easily return or print it.
        """

        messages = " ".join(str(message) for message in messages)

        if lg := (logger or self.logger):
            match type:
                case "default":
                    lg.debug(messages)
                case "message" | "info" | "success":
                    lg.info(messages)
                case "warning":
                    lg.warning(messages)
                case "error":
                    lg.error(messages)
                case _:
                    lg.debug(messages)

        await self.session.send(toast_event(), {"type": type, "message": messages})
        return messages

    async def download(self, filename: str, binary: bytes):
        """
        Send a file to the frontend for download.
        """
        data = base64.b64encode(binary).decode("utf-8")
        await self.session.send(download_event(), {"filename": filename, "data": data})

    def observe(self, obj: object, **sync_attributes: str | EllipsisType):
        """
        Observe additional attributes, useful for when you're extending/subclassing an already Synced object, or when you want to observe multiple objects.
        """
        ...
        # TODO: append, deregister, re-register

    # ========== Low-Level: State Management ========== #
    def _snapshot(self) -> dict[str, Any]:
        result = {}

        if isinstance(self.obj, BaseModel):
            result = self.obj.model_dump(
                mode="json",
                include=set(self.sync_attributes.keys()),
                warnings=False,
            )
        else:
            for attr, key in self.sync_attributes.items():
                value = getattr(self.obj, attr)
                if attr in self.type_adapters:
                    # Use TypeAdapter to serialize with warnings disabled
                    result[key] = self.type_adapters[attr].dump_python(
                        value, mode="json", warnings=False
                    )
                else:
                    result[key] = deepcopy(value)

        if self.task_exposure:
            result[self.task_exposure] = list(self.running_tasks.keys())

        return result

    # ========== Low-Level: Register Event Callbacks ========== #
    def _register_event_handlers(self):
        self.session.register_event(get_event(self.key), self._send_state)
        self.session.register_event(set_event(self.key), self._set_state)
        self.session.register_event(patch_event(self.key), self._patch_state)
        if self.send_on_init:
            self.session.register_init(self._send_state)
        if self.actions:
            self.session.register_event(action_event(self.key), self.actions)
        if self.tasks:
            self.session.register_event(task_start_event(self.key), self.tasks)
        if self.task_cancels:
            self.session.register_event(task_cancel_event(self.key), self.task_cancels)

    def _deregister(self):
        self.session.deregister_event(get_event(self.key))
        self.session.deregister_event(set_event(self.key))
        self.session.deregister_event(patch_event(self.key))
        if self.send_on_init:
            self.session.init_handlers.remove(self._send_state)
        if self.actions:
            self.session.deregister_event(action_event(self.key))
        if self.tasks:
            self.session.deregister_event(task_start_event(self.key))
        if self.task_cancels:
            self.session.deregister_event(task_cancel_event(self.key))

    async def _send_state(self, _: Any = None):
        self.state_snapshot = self._snapshot()
        await self.session.send(set_event(self.key), self.state_snapshot)

    async def _set_state(self, new_state: dict[str, Any]):
        for key, value in new_state.items():
            if key == self.task_exposure:
                continue

            attr_name = self.key_to_attr[key]
            value = deepcopy(value)

            if attr_name in self.type_adapters:
                value = self.type_adapters[attr_name].validate_python(value)
            try:
                setattr(self.obj, attr_name, value)
            except AttributeError:
                # trying to set a property without setter (readonly), don't set
                assert getattr(self.obj, attr_name) == value, (
                    "Trying to set a readonly attribute"
                )

        self.state_snapshot = new_state  # update latest snapshot

    async def _patch_state(self, patch: list[dict[str, Any]]):
        # Apply patch to the snapshot first
        self.state_snapshot = jsonpatch.apply_patch(
            self.state_snapshot, patch, in_place=True
        )

        for key, value in self.state_snapshot.items():
            if key == self.task_exposure:
                continue

            attr_name = self.key_to_attr[key]
            value = deepcopy(value)

            if attr_name in self.type_adapters:
                value = self.type_adapters[attr_name].validate_python(value)

            try:
                setattr(self.obj, attr_name, value)
            except AttributeError:
                # trying to set a property without setter (readonly), don't set
                assert getattr(self.obj, attr_name) == value, (
                    "Trying to set a readonly attribute"
                )

    @staticmethod
    def _create_action_handler(
        handlers: dict[str, Callable[..., Any]],
    ) -> Callable[[dict[str, Any]], Awaitable[None]]:
        async def _handle_action(action: dict):
            action_type = action.pop("type")
            if action_type in handlers:
                await handlers[action_type](**action)
            else:
                warnings.warn(f"No handler for action {action_type}")

        return _handle_action

    def _create_task_handlers(
        self,
        factories: dict[str, Callable[..., Awaitable[Any]]],
        on_cancel: dict[str, Callable[..., Awaitable[Any]]] | None,
    ) -> tuple[
        Callable[[dict[str, Any]], Awaitable[None]],
        Callable[[dict[str, Any]], Awaitable[None]],
    ]:
        async def _run_and_pop(task: Awaitable, task_type: str):
            try:
                await task
            except asyncio.CancelledError:
                if self.logger:
                    self.logger.info(f"Task {task_type} cancelled")
                if on_cancel and task_type in on_cancel:
                    await on_cancel[task_type]()
                raise
            finally:
                self.running_tasks.pop(task_type, None)
                if self.task_exposure:
                    await self.sync()

        async def _create_task(task_args: dict):
            task_type = task_args.pop("type")
            if task_type in factories:
                if task_type not in self.running_tasks:
                    todo = factories[task_type](**task_args)
                    task = asyncio.create_task(_run_and_pop(todo, task_type))
                    self.running_tasks[task_type] = task
                    if self.task_exposure:
                        await self.sync()
                else:
                    if self.logger:
                        self.logger.warning(f"Task {task_type} already running")
            else:
                warnings.warn(f"No factory for task {task_type}")

        async def _cancel_task(task_args: dict):
            task_type = task_args.pop("type")
            if task_type in self.running_tasks:
                self.running_tasks[task_type].cancel()
            else:
                if self.logger:
                    self.logger.warning(f"Task {task_type} not running")

        return _create_task, _cancel_task

    # ========== Utils ========== #
    def casing(self, attr: str) -> str:
        return self.casing_func(attr)
