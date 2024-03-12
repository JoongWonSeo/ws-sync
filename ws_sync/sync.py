import asyncio
from typing import Callable, Literal
from copy import deepcopy
from logging import Logger
import warnings

import jsonpatch
from .session import Session, get_global_session


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


# TODO: for key-space, global key prefix and context manager function in Sync

ToastType = Literal["default", "message", "info", "success", "warning", "error"]


class Sync:
    """
    Register an object's attributes to this class to sync them with the frontend.
    """

    def __init__(
        self,
        key: str,
        obj: object,
        connection: Session | None = None,
        on_action: Callable | dict[str, Callable] | None = None,
        tasks: dict[str, Callable] | tuple[Callable, Callable] | None = None,
        on_task_cancel: dict[str, Callable] | None = None,
        send_on_init: bool = True,
        expose_running_tasks: bool = False,
        logger: Logger | None = None,
        **sync_attributes: dict[str, Ellipsis],
    ):
        """
        Register the attributes that should be synced with the frontend.

        Args:
            key: unique key for this object
            obj: the object whose attributes should be synced
            connection: the connection to use, if None, use the global connection
            on_action: either an action handler taking a single action dict, or a dict of action handlers for each action type, each taking the data of the action as keyword arguments
            tasks: either a dict of task factories for each task type, each returning a coroutine to be used as a task, or a tuple of (task_start_handler, task_cancel_handler)
            on_task_cancel: a dict of task cancel handlers for each task type
            send_on_init: whether to send the state on connection init
            expose_running_tasks: whether to expose the running tasks to the frontend
            sync_attributes: attribute names to observe, value being either ... or a string of the key of the attribute, leave empty to observe all attributes
        """
        self.key = key
        self.obj = obj
        self.send_on_init = send_on_init
        self.expose_running_tasks = expose_running_tasks
        self.logger = logger

        # connection, usually from the "global provider", i.e. the context manager
        self.connection = connection or get_global_session()
        assert (
            self.connection is not None
        ), "No connection, either pass it as an argument or use the global connection using the context manager!"

        # action handler
        if isinstance(on_action, dict):
            self.on_action = self._create_action_handler(on_action)
        else:
            self.on_action = on_action

        # task handler
        self.running_tasks: dict[str, asyncio.Task] = {}
        if tasks:
            if type(tasks) is dict:
                self.on_task_start, self.on_task_cancel = self._create_task_handlers(
                    tasks, on_task_cancel
                )
            elif type(tasks) is tuple:
                self.on_task_start, self.on_task_cancel = tasks
            else:
                raise Exception("Invalid tasks argument")
        else:
            self.on_task_start, self.on_task_cancel = None, None

        # register attributes to sync
        for attr in sync_attributes:
            assert attr in dir(
                obj
            ), f"Failed to register attribute: Object has no attribute {attr}"

        self.sync_attributes = {
            attr: attr if key is ... else key for attr, key in sync_attributes.items()
        }

        # if no attributes are specified, observe all non-private attributes
        if len(self.sync_attributes) == 0:
            self.sync_attributes = {
                attr: attr
                for attr in dir(obj)
                if not attr.startswith("_")
                and not callable(getattr(obj, attr))
                and not isinstance(getattr(obj, attr), Sync)
            }

        # create reverse-lookup for patching
        self.key_to_attr = {key: attr for attr, key in self.sync_attributes.items()}

        # assertions
        assert (
            len(self.sync_attributes) + expose_running_tasks > 0
        ), "No attributes to sync"
        if self.logger:
            self.logger.info(f"{self.key}: Syncing {self.sync_attributes}")
        for key in self.sync_attributes.values():
            if "_" in key:
                logger(
                    f"[WARNING]: key {key} seems to be in snake_case, did you forget to convert it to CamelCase?"
                )

        # the snapshot is the exact state that the frontend has, so we can calculate the patch
        self.state_snapshot = self._snapshot()

        self._register()

    # ===== Low-Level: State Management =====#
    def _snapshot(self):
        return {
            key: deepcopy(getattr(self.obj, attr))
            for attr, key in self.sync_attributes.items()
        } | (
            {"runningTasks": list(self.running_tasks.keys())}
            if self.expose_running_tasks
            else {}
        )

    def observe(self, obj, **sync_attributes: dict[str, Ellipsis]):
        """
        Observe additional attributes, useful for when you're extending/subclassing an already Synced object, or when you want to observe multiple objects.
        """
        ...
        # TODO: append, deregister, re-register

    # ===== Low-Level: Register Event Callbacks =====#
    def _register(self):
        self.connection.register_event(get_event(self.key), self._send_state)
        self.connection.register_event(set_event(self.key), self._set_state)
        self.connection.register_event(patch_event(self.key), self._patch_state)
        if self.send_on_init:
            self.connection.register_init(self._send_state)
        if self.on_action:
            self.connection.register_event(action_event(self.key), self.on_action)
        if self.on_task_start:
            self.connection.register_event(
                task_start_event(self.key), self.on_task_start
            )
        if self.on_task_cancel:
            self.connection.register_event(
                task_cancel_event(self.key), self.on_task_cancel
            )

    def _deregister(self):
        self.connection.deregister_event(get_event(self.key))
        self.connection.deregister_event(set_event(self.key))
        self.connection.deregister_event(patch_event(self.key))
        if self.send_on_init:
            self.connection.init_handlers.remove(self._send_state)
        if self.on_action:
            self.connection.deregister_event(action_event(self.key))
        if self.on_task_start:
            self.connection.deregister_event(task_start_event(self.key))
        if self.on_task_cancel:
            self.connection.deregister_event(task_cancel_event(self.key))

    async def _send_state(self, _=None):
        self.state_snapshot = self._snapshot()
        await self.connection.send(set_event(self.key), self.state_snapshot)

    async def _set_state(self, new_state):
        for attr, value in new_state.items():
            setattr(self.obj, attr, value)

    async def _patch_state(self, patch):
        self.state_snapshot = jsonpatch.apply_patch(
            self.state_snapshot, patch, in_place=True
        )
        for key, value in self.state_snapshot.items():
            if self.expose_running_tasks and key == "runningTasks":
                continue
            try:
                setattr(self.obj, self.key_to_attr[key], deepcopy(value))
            except AttributeError:
                # attempting to set a property without a setter
                pass

    @staticmethod
    def _create_action_handler(handlers: dict[str, Callable]):
        async def _handle_action(action: dict):
            action_type = action.pop("type")
            if action_type in handlers:
                await handlers[action_type](**action)
            else:
                warnings.warn(f"No handler for action {type}")

        return _handle_action

    def _create_task_handlers(
        self, factories: dict[str, Callable], on_cancel: dict[str, Callable] | None
    ):
        async def _run_and_pop(task, task_type: str):
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
                if self.expose_running_tasks:
                    if self.logger:
                        self.logger.debug(
                            f"syncing running tasks: {list(self.running_tasks.keys())}"
                        )
                    await self.sync()

        async def _create_task(task: dict):
            task_type = task.pop("type")
            if task_type in factories:
                if task_type not in self.running_tasks:
                    todo = factories[task_type](**task)
                    task = asyncio.create_task(_run_and_pop(todo, task_type))
                    self.running_tasks[task_type] = task
                    if self.expose_running_tasks:
                        if self.logger:
                            self.logger.debug(
                                f"syncing running tasks: {list(self.running_tasks.keys())}"
                            )
                        await self.sync()
                else:
                    if self.logger:
                        self.logger.warning(f"Task {task_type} already running")
            else:
                warnings.warn(f"No factory for task {task_type}")

        async def _cancel_task(task: dict):
            task_type = task.pop("type")
            if task_type in self.running_tasks:
                self.running_tasks[task_type].cancel()
            else:
                if self.logger:
                    self.logger.warning(f"Task {task_type} not running")

        return _create_task, _cancel_task

    # ===== High-Level: Sync and Actions =====#
    async def sync(self):
        """
        Sync all registered attributes.
        """
        if not self.connection.is_connected:
            return

        # calculate patch
        prev = self.state_snapshot
        self.state_snapshot = self._snapshot()
        patch = jsonpatch.make_patch(prev, self.state_snapshot).patch

        if len(patch) > 0:
            await self.connection.send(patch_event(self.key), patch)

    async def __call__(self):
        """
        Sync all registered attributes.
        """
        await self.sync()

    async def send_action(self, action: dict[str, any]):
        """
        Send an action to the frontend.
        """
        await self.connection.send(action_event(self.key), action)

    async def toast(
        self, *messages, type: ToastType = "default", logger: Logger | None = None
    ) -> str:
        """
        Send a toast message to the frontend.
        Returns the sent message content, so that you can easily return or print it.
        """

        messages = " ".join(str(message) for message in messages)

        if logger or self.logger:
            logger = logger or self.logger
            match type:
                case "default":
                    logger.debug(messages)
                case "message" | "info" | "success":
                    logger.info(messages)
                case "warning":
                    logger.warning(messages)
                case "error":
                    logger.error(messages)
                case _:
                    logger.debug(messages)

        await self.connection.send("_TOAST", {"type": type, "message": messages})
        return messages
