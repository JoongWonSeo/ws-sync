"""
Common test utilities and helper functions for ws-sync tests.
"""

import jsonpatch
from pydantic import BaseModel, computed_field

from ws_sync.sync import Sync


def get_patch(sync: Sync):
    """Helper to get patch from sync object"""
    prev = sync.state_snapshot
    sync.state_snapshot = sync._snapshot()
    return jsonpatch.make_patch(prev, sync.state_snapshot).patch


# Test model classes used across multiple test files


class User(BaseModel):
    """Test Pydantic model"""

    name: str
    age: int
    email: str | None = None


class Team(BaseModel):
    """Test Pydantic model with nested structure"""

    name: str
    members: list[User]
    leader: User | None = None


class Company(BaseModel):
    """Test Pydantic model with complex nesting"""

    name: str
    teams: list[Team]
    employees: dict[str, User]


class UserWithComputedField(BaseModel):
    """Test Pydantic model with computed field"""

    name: str
    age: int

    @computed_field
    @property
    def display_name(self) -> str:
        return f"{self.name} (age {self.age})"


class UserWithWritableComputedField(BaseModel):
    """Test Pydantic model with writable computed field"""

    first_name: str
    last_name: str

    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @full_name.setter
    def full_name(self, value: str) -> None:
        parts = value.split(" ", 1)
        self.first_name = parts[0]
        self.last_name = parts[1] if len(parts) > 1 else ""
