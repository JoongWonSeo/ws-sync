"""
Tests for Pydantic object syncing feature in ws-sync.
"""

from unittest.mock import Mock

import pytest

from ws_sync import sync_all, sync_only
from ws_sync.sync import Sync

from .utils import Company, Team, User, UserWithComputedField

# Test models are imported from .utils


class TestPydanticSync:
    """Test suite for Pydantic object synchronization"""

    # Fixtures are imported from .utils

    def test_simple_pydantic_model_sync(self, mock_session: Mock, sample_user: User):
        """Test syncing a simple Pydantic model"""

        class UserContainer:
            sync: Sync
            user: User  # Class-level annotation

            @sync_all("USER_CONTAINER")
            def __init__(self, user: User):
                self.user = user

        container = UserContainer(sample_user)

        # Check that the user model is serialized correctly
        snapshot = container.sync._snapshot()
        assert "user" in snapshot
        assert snapshot["user"]["name"] == "John Doe"
        assert snapshot["user"]["age"] == 30
        assert snapshot["user"]["email"] == "john@example.com"

    def test_list_of_pydantic_models_sync(self, mock_session: Mock, sample_user: User):
        """Test syncing a list of Pydantic models"""

        class UserListContainer:
            sync: Sync
            users: list[User]  # Class-level annotation

            @sync_all("USER_LIST")
            def __init__(self):
                self.users: list[User] = [
                    sample_user,
                    User(name="Jane Smith", age=25, email="jane@example.com"),
                ]

        container = UserListContainer()

        snapshot = container.sync._snapshot()
        assert "users" in snapshot
        assert len(snapshot["users"]) == 2
        assert snapshot["users"][0]["name"] == "John Doe"
        assert snapshot["users"][1]["name"] == "Jane Smith"

    def test_dict_of_pydantic_models_sync(self, mock_session: Mock, sample_user: User):
        """Test syncing a dict of Pydantic models"""

        class UserDictContainer:
            sync: Sync
            users: dict[str, User]  # Class-level annotation

            @sync_all("USER_DICT")
            def __init__(self):
                self.users: dict[str, User] = {
                    "john": sample_user,
                    "jane": User(name="Jane Smith", age=25),
                }

        container = UserDictContainer()

        snapshot = container.sync._snapshot()
        assert "users" in snapshot
        assert "john" in snapshot["users"]
        assert "jane" in snapshot["users"]
        assert snapshot["users"]["john"]["name"] == "John Doe"
        assert snapshot["users"]["jane"]["name"] == "Jane Smith"

    def test_nested_pydantic_models_sync(self, mock_session: Mock, sample_team: Team):
        """Test syncing nested Pydantic models"""

        class TeamContainer:
            sync: Sync
            team: Team  # Class-level annotation

            @sync_all("TEAM_CONTAINER")
            def __init__(self, team: Team):
                self.team = team

        container = TeamContainer(sample_team)

        snapshot = container.sync._snapshot()
        assert "team" in snapshot
        assert snapshot["team"]["name"] == "Engineering"
        assert len(snapshot["team"]["members"]) == 2
        assert snapshot["team"]["members"][0]["name"] == "John Doe"
        assert snapshot["team"]["leader"]["name"] == "John Doe"

    def test_complex_nested_structures_sync(
        self, mock_session: Mock, sample_company: Company
    ):
        """Test syncing complex nested structures"""

        class CompanyContainer:
            sync: Sync
            company: Company  # Class-level annotation

            @sync_all("COMPANY")
            def __init__(self, company: Company):
                self.company = company

        container = CompanyContainer(sample_company)

        snapshot = container.sync._snapshot()
        assert "company" in snapshot
        assert snapshot["company"]["name"] == "Tech Corp"
        assert len(snapshot["company"]["teams"]) == 1
        assert len(snapshot["company"]["employees"]) == 2
        assert snapshot["company"]["employees"]["john"]["name"] == "John Doe"

    @pytest.mark.asyncio
    async def test_pydantic_model_deserialization(self, mock_session: Mock):
        """Test deserializing dict back to Pydantic model"""

        class UserContainer:
            sync: Sync
            user: User

            @sync_all("USER_CONTAINER")
            def __init__(self):
                self.user: User = User(name="Initial", age=0)

        container = UserContainer()

        # Simulate receiving state from frontend
        new_state = {
            "user": {"name": "Updated User", "age": 35, "email": "updated@example.com"}
        }

        # This should convert the dict back to a User model
        await container.sync._set_state(new_state)

        assert isinstance(container.user, User)
        assert container.user.name == "Updated User"
        assert container.user.age == 35
        assert container.user.email == "updated@example.com"

    @pytest.mark.asyncio
    async def test_pydantic_list_deserialization(self, mock_session: Mock):
        """Test deserializing list of dicts back to Pydantic models"""

        class UserListContainer:
            sync: Sync
            users: list[User]

            @sync_all("USER_LIST")
            def __init__(self):
                self.users: list[User] = []

        container = UserListContainer()

        new_state = {
            "users": [
                {"name": "User 1", "age": 25},
                {"name": "User 2", "age": 30, "email": "user2@example.com"},
            ]
        }

        await container.sync._set_state(new_state)

        assert len(container.users) == 2
        assert all(isinstance(user, User) for user in container.users)
        assert container.users[0].name == "User 1"
        assert container.users[1].email == "user2@example.com"

    @pytest.mark.asyncio
    async def test_pydantic_dict_deserialization(self, mock_session: Mock):
        """Test deserializing dict of dicts back to Pydantic models"""

        class UserDictContainer:
            sync: Sync
            users: dict[str, User]

            @sync_all("USER_DICT")
            def __init__(self):
                self.users: dict[str, User] = {}

        container = UserDictContainer()

        new_state = {
            "users": {
                "john": {"name": "John", "age": 30},
                "jane": {"name": "Jane", "age": 25, "email": "jane@example.com"},
            }
        }

        await container.sync._set_state(new_state)

        assert len(container.users) == 2
        assert all(isinstance(user, User) for user in container.users.values())
        assert container.users["john"].name == "John"
        assert container.users["jane"].email == "jane@example.com"

    @pytest.mark.asyncio
    async def test_partial_updates_with_patches(self, mock_session: Mock):
        """Test that partial updates work correctly with Pydantic models"""

        class UserContainer:
            sync: Sync
            user: User

            @sync_all("USER_CONTAINER")
            def __init__(self):
                self.user: User = User(name="Original", age=25)

        container = UserContainer()

        # Simulate a patch that only updates the age
        patch = [{"op": "replace", "path": "/user/age", "value": 30}]

        await container.sync._patch_state(patch)

        assert isinstance(container.user, User)
        assert container.user.name == "Original"  # unchanged
        assert container.user.age == 30  # updated

    def test_mixed_pydantic_and_regular_attributes(
        self, mock_session: Mock, sample_user: User
    ):
        """Test syncing objects with both Pydantic and regular attributes"""

        class MixedContainer:
            sync: Sync
            user: User
            count: int
            title: str

            @sync_all("MIXED")
            def __init__(self):
                self.user: User = sample_user
                self.count: int = 42
                self.title: str = "Test Title"

        container = MixedContainer()

        snapshot = container.sync._snapshot()
        assert "user" in snapshot
        assert "count" in snapshot
        assert "title" in snapshot
        assert snapshot["user"]["name"] == "John Doe"
        assert snapshot["count"] == 42
        assert snapshot["title"] == "Test Title"

    def test_sync_only_with_pydantic_models(
        self, mock_session: Mock, sample_user: User
    ):
        """Test sync_only decorator with Pydantic models"""

        class SelectiveContainer:
            sync: Sync
            user: User
            count: int

            @sync_only("SELECTIVE", user=..., count=...)
            def __init__(self):
                self.user: User = sample_user
                self.count: int = 42
                self.private_data: str = "secret"  # not synced

        container = SelectiveContainer()

        snapshot = container.sync._snapshot()
        assert "user" in snapshot
        assert "count" in snapshot
        assert "private_data" not in snapshot

    def test_camel_case_conversion_with_pydantic(
        self, mock_session: Mock, sample_user: User
    ):
        """Test camelCase conversion with Pydantic models"""

        class CamelCaseContainer:
            sync: Sync
            user_profile: User
            user_count: int

            @sync_all("CAMEL_CASE", toCamelCase=True)
            def __init__(self):
                self.user_profile: User = sample_user
                self.user_count: int = 1

        container = CamelCaseContainer()

        snapshot = container.sync._snapshot()
        assert "userProfile" in snapshot
        assert "userCount" in snapshot
        assert "user_profile" not in snapshot
        assert "user_count" not in snapshot

    def test_computed_fields_sync(self, mock_session: Mock):
        """Test that computed fields are included in sync"""

        user = UserWithComputedField(name="John", age=30)

        # Direct sync test - this should fail with current implementation
        user_sync = Sync.all(user, "USER_COMPUTED")

        # Check sync attributes to see if computed field is included
        assert "name" in user_sync.sync_attributes
        assert "age" in user_sync.sync_attributes
        # This should fail with the current implementation
        assert "display_name" in user_sync.sync_attributes

        # Test snapshot includes computed field
        snapshot = user_sync._snapshot()
        assert "name" in snapshot
        assert "age" in snapshot
        assert "display_name" in snapshot
        assert snapshot["display_name"] == "John (age 30)"
