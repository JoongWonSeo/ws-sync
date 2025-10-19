import asyncio
import base64
import logging
import warnings
from collections.abc import Awaitable, Callable, Iterable, Mapping
from contextvars import ContextVar, Token
from copy import deepcopy
from inspect import Parameter, signature
from logging import Logger
from time import time
from types import EllipsisType
from typing import Any, Literal, Protocol, Self, cast, get_type_hints

import jsonpatch
from pydantic import (
    AliasGenerator,
    BaseModel,
    ConfigDict,
    PydanticSchemaGenerationError,
    TypeAdapter,
    create_model,
)
from pydantic.alias_generators import to_camel, to_pascal

from ws_sync.decorators import (
    find_remote_actions,
    find_remote_task_cancellers,
    find_remote_tasks,
)
from ws_sync.utils import get_alias_function_for_class, nonblock_call

from .session import session_context

logger = logging.getLogger(__name__)


# Sync Key Prefix Context
_sync_key_prefix_stack: ContextVar[list[str] | None] = ContextVar(
    "_sync_key_prefix_stack", default=None
)
"""Per-task sync key prefix stack. Allows nested prefix scopes."""


class sync_key_scope:  # noqa: N801
    """
    Context manager for scoping sync keys with a prefix.

    All Sync objects created within this context will have their keys prefixed.
    Supports nesting - nested scopes will create hierarchical prefixes with '/' separator.

    Example:
        ```python
        with sync_key_scope("user123"):
            obj1 = MyObject()  # key: "user123/MY_KEY"

            with sync_key_scope("session456"):
                obj2 = MyObject()  # key: "user123/session456/MY_KEY"
        ```

    Args:
        prefix: The prefix to add. Empty strings and None are ignored (no prefix added).
    """

    def __init__(self, prefix: str | None):
        self.prefix = prefix
        self.token: Token[list[str] | None] | None = None

    def __enter__(self) -> Self:
        # Only add non-empty prefixes
        if self.prefix:
            # Get current stack (creates a copy to avoid mutation issues)
            current_stack = _sync_key_prefix_stack.get()
            current_stack = [] if current_stack is None else current_stack.copy()
            current_stack.append(self.prefix)
            self.token = _sync_key_prefix_stack.set(current_stack)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        if self.token is not None:
            _sync_key_prefix_stack.reset(self.token)
            self.token = None


def get_current_sync_key_prefix() -> str | None:
    """
    Get the current sync key prefix from nested scopes.

    Returns:
        The full hierarchical prefix string (e.g., "abc/nested/deep"),
        or None if no prefix scope is active.

    Example:
        ```python
        with sync_key_scope("abc"):
            with sync_key_scope("nested"):
                prefix = get_current_sync_key_prefix()  # "abc/nested"
        ```
    """
    stack = _sync_key_prefix_stack.get()
    if not stack:
        return None
    return "/".join(stack)


def _apply_sync_key_prefix(key: str) -> str:
    """
    Apply the current prefix stack to a sync key.

    Args:
        key: The base sync key.

    Returns:
        The prefixed key (e.g., "abc/nested/MY_KEY"), or the original key if no prefix is active.
    """
    prefix = get_current_sync_key_prefix()
    if prefix:
        return f"{prefix}/{key}"
    return key


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


class SchemaTitleGenerator(Protocol):
    def __call__(self, class_name: str, key: str) -> str: ...


default_action_title_generator: SchemaTitleGenerator = (  # noqa: E731
    lambda class_name, key: f"{class_name}Action{to_pascal(key)}"
)
default_task_title_generator: SchemaTitleGenerator = (  # noqa: E731
    lambda class_name, key: f"{class_name}Task{to_pascal(key)}"
)


class Sync:
    """
    Register an object's attributes to this class to sync them with the frontend.
    """

    @classmethod
    def all(
        cls,
        obj: object,
        key: str,
        *,
        include: dict[str, str | EllipsisType] | list[str] | None = None,
        exclude: list[str] | None = None,
        toCamelCase: bool | None = None,  # noqa: N803
        send_on_init: bool = True,
        expose_running_tasks: bool = False,
        logger: Logger | None = None,
        actions: Mapping[str, Callable[..., Any]] | None = None,
        tasks: Mapping[str, Callable[..., Awaitable[Any]]] | None = None,
        task_cancels: Mapping[str, Callable[..., Awaitable[Any]]] | None = None,
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
        *,
        _toCamelCase: bool | None = None,  # noqa: N803
        _send_on_init: bool = True,
        _expose_running_tasks: bool = False,
        _logger: Logger | None = None,
        _actions: Mapping[str, Callable[..., Any]] | None = None,
        _tasks: Mapping[str, Callable[..., Awaitable[Any]]] | None = None,
        _task_cancels: Mapping[str, Callable[..., Awaitable[Any]]] | None = None,
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
        *,
        sync_all: bool = False,
        include: dict[str, str | EllipsisType] | list[str] | None = None,
        exclude: list[str] | None = None,
        toCamelCase: bool | None = None,  # noqa: N803
        send_on_init: bool = True,
        expose_running_tasks: bool = False,
        logger: Logger | None = None,
        actions: Mapping[str, Callable[..., Any]] | None = None,
        tasks: Mapping[str, Callable[..., Awaitable[Any]]] | None = None,
        task_cancels: Mapping[str, Callable[..., Awaitable[Any]]] | None = None,
    ):
        """
        Register the attributes that should be synced with the frontend.

        Args:
            obj: the object whose attributes should be synced
            key: unique key for this object

            sync_all: whether to sync all non-private attributes
            include: attribute names to sync, value being either ...
                or a string of the key of the attribute
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
        self.key = _apply_sync_key_prefix(key)
        self.send_on_init = send_on_init
        self.casing_func = (
            get_alias_function_for_class(type(self.obj))
            if isinstance(self.obj, BaseModel)
            else (to_camel if toCamelCase else None)
        )
        self.task_exposure = (
            self.casing("running_tasks") if expose_running_tasks else None
        )
        self.logger = logger

        # Convert list[str] include to dict format
        if isinstance(include, list):
            include = dict.fromkeys(include, ...)
        include = include or {}
        exclude = exclude or []

        # Validate that BaseModel objects don't use custom sync keys
        if isinstance(obj, BaseModel) and include:
            for attr_name, sync_key in include.items():
                assert sync_key is ..., (
                    f"Custom sync key '{sync_key}' for attribute '{attr_name}' is not allowed for Pydantic models. Use pydantic's alias_generator in model_config instead."
                )

        self.session = session_context.get()
        assert self.session, "No session set, use the session.session_context variable!"

        # ========== Create Action Validators (cached) ========== #
        actions = dict(actions or {}) | find_remote_actions(type(self.obj))
        self.action_validators: dict[str, TypeAdapter[Any]] = (
            self.build_action_validators(
                target_cls=type(self.obj),
                actions=actions,
                param_alias_generator=self.casing_func,
            )
        )
        # Create action handler after validators are ready
        self.actions = self._create_action_handler(obj, actions)

        # ========== Create Task Validators (cached) ========== #
        tasks = dict(tasks or {}) | find_remote_tasks(type(self.obj))
        task_cancels = dict(task_cancels or {}) | find_remote_task_cancellers(
            type(self.obj)
        )
        self.task_validators: dict[str, TypeAdapter[Any]] = self.build_task_validators(
            target_cls=type(self.obj),
            tasks=tasks,
            param_alias_generator=self.casing_func,
        )
        self.tasks, self.task_cancels = self._create_task_handlers(
            obj, tasks, task_cancels
        )

        # store running tasks
        self.running_tasks: dict[str, asyncio.Task[Any]] = {}

        # ========== Find attributes to sync ========== #
        self.sync_attributes: dict[str, str] = {}

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
            self.logger.debug("%s: Syncing %s", self.key, self.sync_attributes)
            self.logger.debug("%s: Actions %s", self.key, actions)
            self.logger.debug("%s: Tasks %s", self.key, tasks)
            self.logger.debug("%s: Task Cancels %s", self.key, task_cancels)

        assert include.keys().isdisjoint(exclude), "Attribute in both include & exclude"
        assert all(a in dir(obj) for a in self.sync_attributes), "Attribute not found"
        assert all(e in dir(obj) for e in exclude), "Excluded attribute not found"
        # assert (
        #     len(self.sync_attributes) + expose_running_tasks > 0
        # ), "No attributes to sync"

        # ========== Field Type Adapters (cached) ========== #
        self.type_adapters: dict[str, TypeAdapter[Any]] = self.build_field_validators(
            type(obj), field_whitelist=self.sync_attributes.keys()
        )

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
        type: ToastType = "default",  # noqa: A002
    ):
        """
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
        self,
        *messages,
        type: ToastType = "default",  # noqa: A002
        logger: Logger | None = None,
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

    async def download(self, filename: str, binary: bytes) -> None:
        """
        Send a file to the frontend for download.
        """
        data = base64.b64encode(binary).decode("utf-8")
        await self.session.send(download_event(), {"filename": filename, "data": data})

    def observe(self, obj: object, **sync_attributes: str | EllipsisType) -> None:
        """
        Observe additional attributes, useful for when you're extending/subclassing an already Synced object, or when you want to observe multiple objects.
        """
        # TODO: append, deregister, re-register

    # ========== Low-Level: State Management ========== #
    def _snapshot(self) -> dict[str, Any]:
        result = {}

        if isinstance(self.obj, BaseModel):
            # TODO: maybe always explicitly serialize using TypeAdapters like below, since the model maybe be configured for other serialization use cases?
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
        for key, val in new_state.items():
            if key == self.task_exposure:
                continue

            attr_name = self.key_to_attr[key]
            value = deepcopy(val)

            # if isinstance(self.obj, BaseModel):
            #     value = validate_model_field(type(self.obj), attr_name, value)
            if attr_name in self.type_adapters:
                value = self.type_adapters[attr_name].validate_python(value)

            try:
                setattr(self.obj, attr_name, value)
            except AttributeError:
                # Check if this is a computed field without setter - if so, skip silently
                if (
                    isinstance(self.obj, BaseModel)
                    and attr_name in type(self.obj).model_computed_fields
                ):
                    computed_field = type(self.obj).model_computed_fields[attr_name]
                    if computed_field.wrapped_property.fset is None:
                        # Read-only computed field - skip setting, it will be recalculated
                        continue

                # For other readonly attributes, skip setting
                # Don't assert value equality because dependent properties may have changed
                # when other attributes were set earlier in this loop

        self.state_snapshot = new_state  # update latest snapshot

    async def _patch_state(self, patch: list[dict[str, Any]]):
        # Apply patch to the snapshot first to update state tracking
        self.state_snapshot = jsonpatch.apply_patch(
            self.state_snapshot, patch, in_place=True
        )

        # Extract the keys that were actually modified by the patch
        modified_keys = set()
        for patch_op in patch:
            path = patch_op["path"]
            if path.startswith("/"):
                # Extract the top-level key from the path
                key = path.split("/")[1]
                if key in self.key_to_attr:
                    modified_keys.add(key)

        # Only set attributes that were actually modified by the patch
        for key in modified_keys:
            if key == self.task_exposure:
                continue

            attr_name = self.key_to_attr[key]
            value = deepcopy(self.state_snapshot[key])

            # if isinstance(self.obj, BaseModel):
            #     value = validate_model_field(type(self.obj), attr_name, value)
            if attr_name in self.type_adapters:
                value = self.type_adapters[attr_name].validate_python(value)

            try:
                setattr(self.obj, attr_name, value)
            except AttributeError:
                # Check if this is a computed field without setter - if so, skip silently
                if (
                    isinstance(self.obj, BaseModel)
                    and attr_name in type(self.obj).model_computed_fields
                ):
                    computed_field = type(self.obj).model_computed_fields[attr_name]
                    if computed_field.wrapped_property.fset is None:
                        # Read-only computed field - skip setting, it will be recalculated
                        continue

                # For other readonly attributes, skip setting
                # Don't assert value equality because dependent properties may have changed
                # when other attributes were set earlier in this loop

    def _create_action_handler(
        self,
        obj: object,
        handlers: Mapping[str, Callable[..., Any]],
    ) -> Callable[[dict[str, Any]], Awaitable[None]]:
        async def _handle_action(action: dict):
            action_type = action.pop("type")
            if handler := handlers.get(action_type):
                # Validate action parameters, including converting to python
                if validator := self.action_validators.get(action_type):
                    validated = validator.validate_python(action)
                    if isinstance(validated, BaseModel):
                        # Extract native Python objects (BaseModel/dataclass/etc.)
                        kwargs = {
                            name: getattr(validated, name)
                            for name in type(validated).model_fields
                        }
                    else:
                        kwargs = validated  # already a dict-like structure
                else:
                    kwargs = action

                # Call the underlying action handler
                if getattr(handler, "__self__", None) is None:
                    await nonblock_call(
                        handler, obj, **kwargs
                    )  # handler is unbound to an instance
                else:
                    await nonblock_call(
                        handler, **kwargs
                    )  # handler is bound to an instance
            else:
                warnings.warn(f"No handler for action {action_type}", stacklevel=1)

        return _handle_action

    def _create_task_handlers(
        self,
        obj: object,
        factories: Mapping[str, Callable[..., Awaitable[Any]]],
        on_cancel: Mapping[str, Callable[..., Awaitable[Any]]] | None,
    ) -> tuple[
        Callable[[dict[str, Any]], Awaitable[None]],
        Callable[[dict[str, Any]], Awaitable[None]],
    ]:
        async def _run_and_pop(task: Awaitable, task_type: str):
            try:
                await task
            except asyncio.CancelledError:
                if self.logger:
                    self.logger.info("Task %s cancelled", task_type)
                if on_cancel and task_type in on_cancel:
                    await on_cancel[task_type]()
                raise
            finally:
                self.running_tasks.pop(task_type, None)
                if self.task_exposure:
                    await self.sync()

        async def _create_task(task_args: dict):
            task_type = task_args.pop("type")
            if factory := factories.get(task_type):
                if task_type in self.running_tasks:
                    if self.logger:
                        self.logger.warning("Task %s already running", task_type)
                    return

                if validator := self.task_validators.get(task_type):
                    validated = validator.validate_python(task_args)
                    if isinstance(validated, BaseModel):
                        # Extract native Python objects (BaseModel/dataclass/etc.)
                        kwargs = {
                            name: getattr(validated, name)
                            for name in type(validated).model_fields
                        }
                    else:
                        kwargs = validated  # already a dict-like structure
                else:
                    kwargs = task_args

                # Create the task
                if getattr(factory, "__self__", None) is None:
                    todo = nonblock_call(
                        factory, obj, **kwargs
                    )  # factory is unbound to an instance
                else:
                    todo = nonblock_call(
                        factory, **kwargs
                    )  # factory is bound to an instance

                task = asyncio.create_task(_run_and_pop(todo, task_type))
                self.running_tasks[task_type] = task
                if self.task_exposure:
                    await self.sync()
            else:
                warnings.warn(f"No factory for task {task_type}", stacklevel=1)

        async def _cancel_task(task_args: dict):
            task_type = task_args.pop("type")
            if running_task := self.running_tasks.get(task_type):
                running_task.cancel()
            elif self.logger:
                self.logger.warning("Task %s not running", task_type)

        return _create_task, _cancel_task

    # ========== Utils ========== #
    def casing(self, attr: str) -> str:
        return self.casing_func(attr) if self.casing_func else attr

    # ========== Static validator builders with caching ========== #
    _field_validators_cache: dict[type, dict[str, TypeAdapter[Any]]] = {}
    """{class: {field: TypeAdapter}}; Dynamically registered fields may be added at runtime"""
    _action_validators_cache: dict[type, dict[str, TypeAdapter[Any]]] = {}
    """{class: {action_key: TypeAdapter}}; Dynamically registered actions may be added at runtime"""
    _task_validators_cache: dict[type, dict[str, TypeAdapter[Any]]] = {}
    """{class: {task_key: TypeAdapter}}; Dynamically registered tasks may be added at runtime"""

    @staticmethod
    def build_kwargs_model(
        target_cls: type,
        model_name: str,
        func: Callable[..., Any],
        alias_generator: Callable[[str], str] | AliasGenerator | None,
    ) -> type[BaseModel]:
        """
        Build a Pydantic model to validate the kwargs of a function.
        """
        sig = signature(func)
        fields: dict[str, tuple[Any, Any]] = {}
        for idx, (param_name, param) in enumerate(sig.parameters.items()):
            if idx == 0 and param_name == "self":
                continue
            if param.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
                continue
            annotation = (
                param.annotation if param.annotation is not Parameter.empty else Any
            )
            default = param.default if param.default is not Parameter.empty else ...
            fields[param_name] = (annotation, default)

        cfg = ConfigDict(
            alias_generator=alias_generator,
            validate_by_name=True,  # Python -> Python (TODO: when?)
            validate_by_alias=True,  # JSON -> Python
        )
        model = create_model(
            model_name,
            __config__=cfg,
            __module__=target_cls.__module__,
            **cast("dict[str, Any]", fields),
        )
        return model

    @staticmethod
    def build_field_validators(
        target_cls: type,
        *,
        field_whitelist: Iterable[str] | None = None,
        use_cache: bool = True,
    ) -> dict[str, TypeAdapter[Any]]:
        """
        Build a dictionary of field validators for a given class.

        Args:
            target_cls: The class to build validators for.
            field_whitelist: A list of field names to include in the validators. If None, all fields are included.
            use_cache: Whether to use the cache.
        """
        if use_cache and target_cls in Sync._field_validators_cache:
            return Sync._field_validators_cache[target_cls]

        validators: dict[str, TypeAdapter[Any]] = {}
        if issubclass(target_cls, BaseModel):
            for name, field in target_cls.model_fields.items():
                validators[name] = TypeAdapter(field.annotation)
            for name, field in target_cls.model_computed_fields.items():
                validators[name] = TypeAdapter(field.return_type)

        else:
            type_hints = get_type_hints(target_cls)
            if field_whitelist is not None:
                type_hints = {
                    field: annotation
                    for field in field_whitelist
                    if (annotation := type_hints.get(field))
                }
            for name, annotation in type_hints.items():
                try:
                    validators[name] = TypeAdapter(annotation)
                except PydanticSchemaGenerationError:
                    logger.exception("Error building validator for %s", name)

        if use_cache:
            Sync._field_validators_cache[target_cls] = validators
        return validators

    @staticmethod
    def build_action_validators(
        target_cls: type,
        *,
        actions: dict[str, Callable[..., Any]] | None = None,
        schema_title_generator: SchemaTitleGenerator = default_action_title_generator,
        param_alias_generator: Callable[[str], str] | AliasGenerator | None = None,
        use_cache: bool = True,
    ) -> dict[str, TypeAdapter[Any]]:
        """
        Build a dictionary of action validators for a given class.

        Args:
            target_cls: The class whose actions to build validators for.
            actions: A dictionary of action names to functions. If None, all actions are included.
            schema_title_generator: A function to set the JSON schema title for each action.
            param_alias_generator: A function to set the JSON schema alias for the action *parameter names*.
            use_cache: Whether to use the cache for the validator objects.
        """
        if param_alias_generator is None:
            param_alias_generator = get_alias_function_for_class(target_cls)

        validators: dict[str, TypeAdapter[Any]] = {}

        cache_key = target_cls
        if use_cache and cache_key in Sync._action_validators_cache:
            validators = Sync._action_validators_cache[cache_key]

        actions = actions or find_remote_actions(target_cls)
        for key, func in actions.items():
            if key in validators:
                continue

            model = Sync.build_kwargs_model(
                target_cls=target_cls,
                model_name=schema_title_generator(
                    class_name=target_cls.__name__, key=key
                ),
                func=func,
                alias_generator=param_alias_generator,
            )
            validators[key] = TypeAdapter(model)

        if use_cache:
            Sync._action_validators_cache[cache_key] = validators
        return validators

    @staticmethod
    def build_task_validators(
        target_cls: type,
        *,
        tasks: dict[str, Callable[..., Any]] | None = None,
        schema_title_generator: SchemaTitleGenerator = default_task_title_generator,
        param_alias_generator: Callable[[str], str] | AliasGenerator | None = None,
        use_cache: bool = True,
    ) -> dict[str, TypeAdapter[Any]]:
        """
        Build a dictionary of task validators for a given class.

        Args:
            target_cls: The class whose tasks to build validators for.
            tasks: A dictionary of task names to functions. If None, all tasks are included.
            schema_title_generator: A function to set the JSON schema title for each task.
            param_alias_generator: A function to set the JSON schema alias for the task *parameter names*.
            use_cache: Whether to use the cache for the validator objects.
        """
        if param_alias_generator is None:
            param_alias_generator = get_alias_function_for_class(target_cls)

        validators: dict[str, TypeAdapter[Any]] = {}

        cache_key = target_cls
        if use_cache and cache_key in Sync._task_validators_cache:
            validators = Sync._task_validators_cache[cache_key]

        tasks = tasks or find_remote_tasks(target_cls)
        for key, func in tasks.items():
            if key in validators:
                continue

            model = Sync.build_kwargs_model(
                target_cls=target_cls,
                model_name=schema_title_generator(
                    class_name=target_cls.__name__, key=key
                ),
                func=func,
                alias_generator=param_alias_generator,
            )
            validators[key] = TypeAdapter(model)

        if use_cache:
            Sync._task_validators_cache[cache_key] = validators
        return validators
