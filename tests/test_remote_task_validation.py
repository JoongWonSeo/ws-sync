"""
Tests for remote task validation using TypeAdapters in ws-sync.
"""

from enum import Enum
from unittest.mock import Mock

import pytest

from ws_sync import remote_task, sync_all
from ws_sync.sync import Sync


# Test Enum
class TaskPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TestRemoteTaskValidation:
    """Test suite for remote task parameter validation using TypeAdapters"""

    @pytest.mark.asyncio
    async def test_task_with_enum_parameter_decorator(self, mock_session: Mock):
        """Test remote task with enum parameter using decorator"""

        class TaskRunner:
            sync: Sync

            @sync_all("TASK_RUNNER")
            def __init__(self):
                self.last_priority: TaskPriority | None = None

            @remote_task("PROCESS_WITH_PRIORITY")
            async def process_with_priority(self, priority: TaskPriority):
                self.last_priority = priority

        runner = TaskRunner()

        # Test valid enum value via task creation
        task_data = {"type": "PROCESS_WITH_PRIORITY", "priority": "high"}

        # Create the task (this would normally be called by the session)
        await runner.sync.tasks(task_data)

        # Verify the task was created and is running
        assert "PROCESS_WITH_PRIORITY" in runner.sync.running_tasks

        # Wait for task to complete and check the result
        task = runner.sync.running_tasks["PROCESS_WITH_PRIORITY"]
        await task  # Wait for completion

        assert runner.last_priority == TaskPriority.HIGH

    @pytest.mark.asyncio
    async def test_task_with_validation_error(self, mock_session: Mock):
        """Test that validation errors are properly raised for invalid task parameters"""

        class TaskRunner:
            sync: Sync

            @sync_all("TASK_RUNNER")
            def __init__(self):
                pass

            @remote_task("VALIDATE_PRIORITY")
            async def validate_priority(self, priority: TaskPriority):
                pass

        runner = TaskRunner()

        # Test invalid enum
        with pytest.raises((ValueError, TypeError)):
            invalid_task = {"type": "VALIDATE_PRIORITY", "priority": "invalid_priority"}
            await runner.sync.tasks(invalid_task)

    @pytest.mark.asyncio
    async def test_task_with_raw_tasks_dict(self, mock_session: Mock):
        """Test remote task validation with raw tasks passed to Sync init"""

        class RawTaskRunner:
            sync: Sync

            def __init__(self):
                self.received_priority: TaskPriority | None = None

            async def set_priority_task(self, priority: TaskPriority):
                self.received_priority = priority

        runner = RawTaskRunner()

        # Create Sync with raw tasks dict
        tasks = {
            "SET_PRIORITY": runner.set_priority_task,
        }

        runner.sync = Sync.all(obj=runner, key="RAW_TASK_RUNNER", tasks=tasks)

        # Test enum validation
        priority_task = {"type": "SET_PRIORITY", "priority": "medium"}
        await runner.sync.tasks(priority_task)

        # Wait for task completion
        task = runner.sync.running_tasks["SET_PRIORITY"]
        await task

        assert runner.received_priority == TaskPriority.MEDIUM

    @pytest.mark.asyncio
    async def test_remote_task_optional_key_with_parentheses(self, mock_session: Mock):
        """Test remote task with optional key using () - should default to method name"""

        class OptionalKeyTaskRunner:
            sync: Sync

            @sync_all("OPTIONAL_KEY_TASK_RUNNER")
            def __init__(self):
                self.result: str | None = None

            @remote_task()
            async def my_task(self, value: str):
                self.result = value

        runner = OptionalKeyTaskRunner()

        # Test that task key defaults to method name "my_task"
        task_data = {"type": "my_task", "value": "test_value"}
        await runner.sync.tasks(task_data)

        # Wait for task completion
        task = runner.sync.running_tasks["my_task"]
        await task

        assert runner.result == "test_value"

    @pytest.mark.asyncio
    async def test_remote_task_optional_key_without_parentheses(
        self, mock_session: Mock
    ):
        """Test remote task with optional key without () - should default to method name"""

        class OptionalKeyTaskRunnerNoParens:
            sync: Sync

            @sync_all("OPTIONAL_KEY_TASK_RUNNER_NO_PARENS")
            def __init__(self):
                self.result: str | None = None

            @remote_task
            async def another_task(self, value: str):
                self.result = value

        runner = OptionalKeyTaskRunnerNoParens()

        # Test that task key defaults to method name "another_task"
        task_data = {"type": "another_task", "value": "test_value"}
        await runner.sync.tasks(task_data)

        # Wait for task completion
        task = runner.sync.running_tasks["another_task"]
        await task

        assert runner.result == "test_value"
