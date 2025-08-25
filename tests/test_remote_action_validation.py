"""
Tests for remote action validation using TypeAdapters in ws-sync.
"""

from dataclasses import dataclass
from enum import Enum
from unittest.mock import Mock

import pytest
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from typing_extensions import TypedDict

from ws_sync import remote_action, sync_all
from ws_sync.sync import Sync
from ws_sync.synced_model import Synced, SyncedAsCamelCase

from .utils import User


# Test Enums
class Priority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


# Test DataClass
@dataclass
class Settings:
    theme: str = "light"
    notifications: bool = True
    max_items: int = 100


# Test TypedDict
class TaskDict(TypedDict):
    title: str
    description: str | None
    priority: Priority
    status: TaskStatus


# Test Pydantic Model
class Task(BaseModel):
    title: str
    description: str | None = None
    priority: Priority = Priority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    assigned_to: User | None = None


# Test Pydantic Model with camelCase
class TaskCamelCase(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, serialize_by_alias=True)

    title: str
    description: str | None = None
    priority: Priority = Priority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    assigned_to: User | None = None


class TestRemoteActionValidation:
    """Test suite for remote action parameter validation using TypeAdapters"""

    @pytest.mark.asyncio
    async def test_action_with_enum_parameter_decorator(self, mock_session: Mock):
        """Test remote action with enum parameter using decorator"""

        class TaskManager:
            sync: Sync

            @sync_all("TASK_MANAGER")
            def __init__(self):
                self.tasks: list[Task] = []
                self.received_priority: Priority | None = None

            @remote_action("SET_PRIORITY")
            async def set_priority(self, priority: Priority):
                self.received_priority = priority

        manager = TaskManager()

        # Test valid enum value
        action_data = {"type": "SET_PRIORITY", "priority": "high"}
        await manager.sync.actions(action_data)
        assert manager.received_priority == Priority.HIGH

        # Test invalid enum value should fail validation
        invalid_action = {"type": "SET_PRIORITY", "priority": "invalid"}
        with pytest.raises(ValueError):  # noqa: PT011
            await manager.sync.actions(invalid_action)

    @pytest.mark.asyncio
    async def test_action_with_pydantic_model_parameter_decorator(
        self, mock_session: Mock
    ):
        """Test remote action with Pydantic model parameter using decorator"""

        class TaskManager:
            sync: Sync

            @sync_all("TASK_MANAGER")
            def __init__(self):
                self.tasks: list[Task] = []
                self.received_task: Task | None = None

            @remote_action("CREATE_TASK")
            async def create_task(self, task: Task):
                self.received_task = task
                self.tasks.append(task)

        manager = TaskManager()

        # Test valid task data
        task_data = {
            "type": "CREATE_TASK",
            "task": {
                "title": "Test Task",
                "description": "A test task",
                "priority": "high",
                "status": "pending",
            },
        }
        await manager.sync.actions(task_data)

        assert isinstance(manager.received_task, Task)
        assert manager.received_task.title == "Test Task"
        assert manager.received_task.priority == Priority.HIGH
        assert manager.received_task.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_action_with_dataclass_parameter_decorator(self, mock_session: Mock):
        """Test remote action with dataclass parameter using decorator"""

        class AppManager:
            sync: Sync

            @sync_all("APP_MANAGER")
            def __init__(self):
                self.settings: Settings | None = None

            @remote_action("UPDATE_SETTINGS")
            async def update_settings(self, settings: Settings):
                self.settings = settings

        manager = AppManager()

        # Test valid settings data
        settings_data = {
            "type": "UPDATE_SETTINGS",
            "settings": {"theme": "dark", "notifications": False, "max_items": 50},
        }
        await manager.sync.actions(settings_data)

        assert isinstance(manager.settings, Settings)
        assert manager.settings.theme == "dark"
        assert manager.settings.notifications is False
        assert manager.settings.max_items == 50

    @pytest.mark.asyncio
    async def test_action_with_typeddict_parameter_decorator(self, mock_session: Mock):
        """Test remote action with TypedDict parameter using decorator"""

        class TaskProcessor:
            sync: Sync

            @sync_all("TASK_PROCESSOR")
            def __init__(self):
                self.processed_task: TaskDict | None = None

            @remote_action("PROCESS_TASK")
            async def process_task(self, task_data: TaskDict):
                self.processed_task = task_data

        processor = TaskProcessor()

        # Test valid task data
        task_data = {
            "type": "PROCESS_TASK",
            "task_data": {
                "title": "Process This",
                "description": "A task to process",
                "priority": "medium",
                "status": "in_progress",
            },
        }
        await processor.sync.actions(task_data)

        assert isinstance(processor.processed_task, dict)
        assert processor.processed_task["title"] == "Process This"
        assert processor.processed_task["priority"] == Priority.MEDIUM
        assert processor.processed_task["status"] == TaskStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_action_with_list_parameter_decorator(self, mock_session: Mock):
        """Test remote action with List parameter using decorator"""

        class BulkTaskManager:
            sync: Sync

            @sync_all("BULK_TASK_MANAGER")
            def __init__(self):
                self.bulk_tasks: list[Task] | None = None

            @remote_action("CREATE_BULK_TASKS")
            async def create_bulk_tasks(self, tasks: list[Task]):
                self.bulk_tasks = tasks

        manager = BulkTaskManager()

        # Test valid list of tasks
        tasks_data = {
            "type": "CREATE_BULK_TASKS",
            "tasks": [
                {"title": "Task 1", "priority": "high"},
                {"title": "Task 2", "priority": "low", "description": "Second task"},
            ],
        }
        await manager.sync.actions(tasks_data)

        assert isinstance(manager.bulk_tasks, list)
        assert len(manager.bulk_tasks) == 2
        assert all(isinstance(task, Task) for task in manager.bulk_tasks)
        assert manager.bulk_tasks[0].title == "Task 1"
        assert manager.bulk_tasks[0].priority == Priority.HIGH

    @pytest.mark.asyncio
    async def test_action_with_dict_parameter_decorator(self, mock_session: Mock):
        """Test remote action with Dict parameter using decorator"""

        class TaskGroupManager:
            sync: Sync

            @sync_all("TASK_GROUP_MANAGER")
            def __init__(self):
                self.task_groups: dict[str, Task] | None = None

            @remote_action("SET_TASK_GROUPS")
            async def set_task_groups(self, groups: dict[str, Task]):
                self.task_groups = groups

        manager = TaskGroupManager()

        # Test valid dict of tasks
        groups_data = {
            "type": "SET_TASK_GROUPS",
            "groups": {
                "urgent": {"title": "Urgent Task", "priority": "high"},
                "routine": {"title": "Routine Task", "priority": "low"},
            },
        }
        await manager.sync.actions(groups_data)

        assert isinstance(manager.task_groups, dict)
        assert len(manager.task_groups) == 2
        assert all(isinstance(task, Task) for task in manager.task_groups.values())
        assert manager.task_groups["urgent"].priority == Priority.HIGH

    @pytest.mark.asyncio
    async def test_action_with_camelcase_conversion_decorator(self, mock_session: Mock):
        """Test remote action parameter validation with camelCase conversion"""

        class CamelCaseTaskManager:
            sync: Sync

            @sync_all("CAMEL_CASE_TASK_MANAGER", toCamelCase=True)
            def __init__(self):
                self.received_task: TaskCamelCase | None = None

            @remote_action("CREATE_TASK_CAMEL")
            async def create_task(
                self,
                task_data: TaskCamelCase,
                user_name: str = Field(description="The user name"),
            ):
                self.received_task = task_data
                self.user_name = user_name

        manager = CamelCaseTaskManager()

        # Test with camelCase parameters
        action_data = {
            "type": "CREATE_TASK_CAMEL",
            "taskData": {
                "title": "Camel Case Task",
                "assignedTo": {"name": "John", "age": 30},
            },
            "userName": "admin",
        }
        await manager.sync.actions(action_data)

        assert isinstance(manager.received_task, TaskCamelCase)
        assert manager.received_task.title == "Camel Case Task"
        assert manager.user_name == "admin"

    @pytest.mark.asyncio
    async def test_action_with_optional_parameters_decorator(self, mock_session: Mock):
        """Test remote action with optional parameters using decorator"""

        class FlexibleTaskManager:
            sync: Sync

            @sync_all("FLEXIBLE_TASK_MANAGER")
            def __init__(self):
                self.task_title: str | None = None
                self.task_priority: Priority | None = None

            @remote_action("UPDATE_TASK")
            async def update_task(self, title: str, priority: Priority | None = None):
                self.task_title = title
                self.task_priority = priority

        manager = FlexibleTaskManager()

        # Test with optional parameter provided
        action_data = {
            "type": "UPDATE_TASK",
            "title": "Updated Task",
            "priority": "high",
        }
        await manager.sync.actions(action_data)

        assert manager.task_title == "Updated Task"
        assert manager.task_priority == Priority.HIGH

        # Test with optional parameter omitted
        action_data_no_priority = {"type": "UPDATE_TASK", "title": "Task No Priority"}
        await manager.sync.actions(action_data_no_priority)

        assert manager.task_title == "Task No Priority"
        assert manager.task_priority is None

    @pytest.mark.asyncio
    async def test_action_with_raw_actions_dict(self, mock_session: Mock):
        """Test remote action validation with raw actions passed to Sync init"""

        class RawActionManager:
            sync: Sync

            def __init__(self):
                self.received_priority: Priority | None = None
                self.received_task: Task | None = None

            async def set_priority(self, priority: Priority):
                self.received_priority = priority

            async def create_task(self, task: Task):
                self.received_task = task

        manager = RawActionManager()

        # Create Sync with raw actions dict
        actions = {
            "SET_PRIORITY": manager.set_priority,
            "CREATE_TASK": manager.create_task,
        }

        manager.sync = Sync.all(obj=manager, key="RAW_ACTION_MANAGER", actions=actions)

        # Test enum validation
        priority_action = {"type": "SET_PRIORITY", "priority": "medium"}
        await manager.sync.actions(priority_action)
        assert manager.received_priority == Priority.MEDIUM

        # Test Pydantic model validation
        task_action = {
            "type": "CREATE_TASK",
            "task": {"title": "Raw Action Task", "priority": "low"},
        }
        await manager.sync.actions(task_action)
        assert isinstance(manager.received_task, Task)
        assert manager.received_task.title == "Raw Action Task"

    @pytest.mark.asyncio
    async def test_action_validation_errors(self, mock_session: Mock):
        """Test that validation errors are properly raised for invalid action parameters"""

        class ErrorTestManager:
            sync: Sync

            @sync_all("ERROR_TEST")
            def __init__(self):
                pass

            @remote_action("TEST_ENUM")
            async def test_enum(self, priority: Priority):
                pass

            @remote_action("TEST_MODEL")
            async def test_model(self, task: Task):
                pass

        manager = ErrorTestManager()

        # Test invalid enum
        invalid_enum = {"type": "TEST_ENUM", "priority": "invalid_priority"}
        with pytest.raises((ValueError, TypeError)):
            await manager.sync.actions(invalid_enum)

        # Test invalid model (missing required field)
        invalid_model = {"type": "TEST_MODEL", "task": {"description": "No title"}}
        with pytest.raises((ValueError, TypeError)):
            await manager.sync.actions(invalid_model)

    @pytest.mark.asyncio
    async def test_action_with_synced_model_integration(self, mock_session: Mock):
        """Test remote action integration with synced Pydantic models"""

        class TaskModel(Synced, BaseModel):
            title: str = "Default Task"
            priority: Priority = Priority.MEDIUM

            def model_post_init(self, context):
                self.sync = Sync.all(self, key="TASK_MODEL")

            @remote_action("UPDATE_PRIORITY")
            async def update_priority(self, new_priority: Priority):
                self.priority = new_priority
                await self.sync()

        task = TaskModel(title="Integration Test")

        # Test action on synced model
        action_data = {"type": "UPDATE_PRIORITY", "new_priority": "high"}
        await task.sync.actions(action_data)

        assert task.priority == Priority.HIGH

    @pytest.mark.asyncio
    async def test_action_with_synced_camelcase_model(self, mock_session: Mock):
        """Test remote action with SyncedAsCamelCase model"""

        class CamelTaskModel(SyncedAsCamelCase, BaseModel):
            task_title: str = "Default Task"
            task_priority: Priority = Priority.MEDIUM

            def model_post_init(self, context):
                self.sync = Sync.all(self, key="CAMEL_TASK_MODEL")

            @remote_action("UPDATE_TASK_INFO")
            async def update_task_info(self, task_title: str, task_priority: Priority):
                self.task_title = task_title
                self.task_priority = task_priority
                await self.sync()

        task = CamelTaskModel()

        # Test with camelCase parameters (should be converted from snake_case)
        action_data = {
            "type": "UPDATE_TASK_INFO",
            "taskTitle": "Camel Case Test",
            "taskPriority": "high",
        }
        await task.sync.actions(action_data)

        assert task.task_title == "Camel Case Test"
        assert task.task_priority == Priority.HIGH

    @pytest.mark.asyncio
    async def test_complex_nested_action_parameters(self, mock_session: Mock):
        """Test remote action with complex nested parameter structures"""

        class ComplexTaskManager:
            sync: Sync

            @sync_all("COMPLEX_TASK_MANAGER")
            def __init__(self):
                self.batch_result: dict[str, list[Task]] | None = None

            @remote_action("PROCESS_BATCH")
            async def process_batch(self, batch_data: dict[str, list[Task]]):
                self.batch_result = batch_data

        manager = ComplexTaskManager()

        # Test complex nested structure
        batch_action = {
            "type": "PROCESS_BATCH",
            "batch_data": {
                "urgent": [
                    {"title": "Urgent Task 1", "priority": "high"},
                    {"title": "Urgent Task 2", "priority": "high"},
                ],
                "normal": [{"title": "Normal Task", "priority": "medium"}],
            },
        }
        await manager.sync.actions(batch_action)

        assert isinstance(manager.batch_result, dict)
        assert "urgent" in manager.batch_result
        assert "normal" in manager.batch_result
        assert len(manager.batch_result["urgent"]) == 2
        assert all(isinstance(task, Task) for task in manager.batch_result["urgent"])
        assert manager.batch_result["urgent"][0].priority == Priority.HIGH

    @pytest.mark.asyncio
    async def test_remote_action_optional_key_with_parentheses(
        self, mock_session: Mock
    ):
        """Test remote action with optional key using () - should default to method name"""

        class OptionalKeyManager:
            sync: Sync

            @sync_all("OPTIONAL_KEY_MANAGER")
            def __init__(self):
                self.result: str | None = None

            @remote_action()
            async def my_action(self, value: str):
                self.result = value

        manager = OptionalKeyManager()

        # Test that action key defaults to method name "my_action"
        action_data = {"type": "my_action", "value": "test_value"}
        await manager.sync.actions(action_data)
        assert manager.result == "test_value"

    @pytest.mark.asyncio
    async def test_remote_action_optional_key_without_parentheses(
        self, mock_session: Mock
    ):
        """Test remote action with optional key without () - should default to method name"""

        class OptionalKeyManagerNoParens:
            sync: Sync

            @sync_all("OPTIONAL_KEY_MANAGER_NO_PARENS")
            def __init__(self):
                self.result: str | None = None

            @remote_action
            async def another_action(self, value: str):
                self.result = value

        manager = OptionalKeyManagerNoParens()

        # Test that action key defaults to method name "another_action"
        action_data = {"type": "another_action", "value": "test_value"}
        await manager.sync.actions(action_data)
        assert manager.result == "test_value"
