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
