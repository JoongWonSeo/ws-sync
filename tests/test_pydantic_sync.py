"""
Tests for Pydantic object syncing feature in ws-sync.
"""

from unittest.mock import Mock

import pytest

from ws_sync import sync_all, sync_only
from ws_sync.sync import Sync

from .utils import (
    Company,
    Team,
    User,
    UserWithComputedField,
    UserWithWritableComputedField,
)

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

    @pytest.mark.asyncio
    async def test_computed_field_updates_on_dependency_change(
        self, mock_session: Mock
    ):
        """Test that computed fields update when their dependencies change via patches"""

        user = UserWithComputedField(name="John", age=30)
        user_sync = Sync.all(user, "USER_COMPUTED")

        # Apply patch to change age (dependency of computed field)
        await user_sync._patch_state([{"op": "replace", "path": "/age", "value": 35}])

        # Verify the regular field was updated
        assert user.age == 35
        # Computed field should automatically reflect the change
        assert user.display_name == "John (age 35)"

    @pytest.mark.asyncio
    async def test_computed_field_type_adapter_deserialization(
        self, mock_session: Mock
    ):
        """Test that computed fields use type adapters for proper deserialization"""

        class UserContainer:
            sync: Sync
            user: UserWithComputedField

            @sync_all("USER_COMPUTED_CONTAINER")
            def __init__(self):
                self.user: UserWithComputedField = UserWithComputedField(
                    name="Initial", age=0
                )

        container = UserContainer()

        # Set new state from frontend
        new_state = {
            "user": {
                "name": "Jane",
                "age": "25",
            }  # age as string, should be coerced to int
        }

        await container.sync._set_state(new_state)

        # Verify proper deserialization with type coercion
        assert isinstance(container.user, UserWithComputedField)
        assert container.user.name == "Jane"
        assert isinstance(container.user.age, int)
        assert container.user.age == 25
        # Computed field should reflect the changes
        assert container.user.display_name == "Jane (age 25)"

    @pytest.mark.asyncio
    async def test_computed_field_complex_nested_deserialization(
        self, mock_session: Mock
    ):
        """Test computed fields work correctly with complex nested structures during deserialization"""

        class UserListContainer:
            sync: Sync
            users: list[UserWithComputedField]

            @sync_all("USER_COMPUTED_LIST")
            def __init__(self):
                self.users: list[UserWithComputedField] = []

        container = UserListContainer()

        # Set state with list of users having computed fields
        new_state = {
            "users": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": "25"},  # Test string coercion
            ]
        }

        await container.sync._set_state(new_state)

        # Verify proper deserialization of list elements
        assert len(container.users) == 2
        assert all(isinstance(user, UserWithComputedField) for user in container.users)

        # Check first user
        assert container.users[0].name == "Alice"
        assert container.users[0].age == 30
        assert container.users[0].display_name == "Alice (age 30)"

        # Check second user (with type coercion)
        assert container.users[1].name == "Bob"
        assert isinstance(container.users[1].age, int)
        assert container.users[1].age == 25
        assert container.users[1].display_name == "Bob (age 25)"

    @pytest.mark.asyncio
    async def test_writable_computed_field_patch_deserialization(
        self, mock_session: Mock
    ):
        """Test that writable computed fields can be set via patches and use type adapters"""

        user = UserWithWritableComputedField(first_name="John", last_name="Doe")
        user_sync = Sync.all(user, "USER_WRITABLE_COMPUTED")

        # Apply patch to writable computed field
        await user_sync._patch_state(
            [{"op": "replace", "path": "/full_name", "value": "Jane Smith"}]
        )

        # Verify the setter was called and underlying fields were updated
        assert user.first_name == "Jane"
        assert user.last_name == "Smith"
        assert user.full_name == "Jane Smith"

    @pytest.mark.asyncio
    async def test_writable_computed_field_set_state_deserialization(
        self, mock_session: Mock
    ):
        """Test that writable computed fields work correctly in set_state"""

        class UserContainer:
            sync: Sync
            user: UserWithWritableComputedField

            @sync_all("USER_WRITABLE_CONTAINER")
            def __init__(self):
                self.user: UserWithWritableComputedField = (
                    UserWithWritableComputedField(
                        first_name="Initial", last_name="User"
                    )
                )

        container = UserContainer()

        # Set state with writable computed field - order matters!
        new_state = {
            "user": {
                "full_name": "Bob Wilson",  # Process this first to set the base names
                "first_name": "Alice",  # This will override first_name after the setter
                "last_name": "Johnson",  # This will override last_name after the setter
            }
        }

        await container.sync._set_state(new_state)

        # Verify proper deserialization and field order processing
        assert isinstance(container.user, UserWithWritableComputedField)
        # Fields are processed in order, so last values win
        assert container.user.first_name == "Alice"
        assert container.user.last_name == "Johnson"
        assert container.user.full_name == "Alice Johnson"

    @pytest.mark.asyncio
    async def test_writable_computed_field_type_validation(self, mock_session: Mock):
        """Test that writable computed fields use type adapters for validation"""

        # Test directly on the model, not through a container
        user = UserWithWritableComputedField(first_name="John", last_name="Doe")
        user_sync = Sync.all(user, "USER_WRITABLE_VALIDATION")

        # Test that type adapter validates string input for computed field
        await user_sync._patch_state(
            [{"op": "replace", "path": "/full_name", "value": "Jane Smith"}]
        )

        # Verify proper string handling and setter invocation
        assert isinstance(user.full_name, str)
        assert user.full_name == "Jane Smith"
        assert isinstance(user.first_name, str)
        assert user.first_name == "Jane"
        assert isinstance(user.last_name, str)
        assert user.last_name == "Smith"
