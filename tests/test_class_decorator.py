import pytest
from pydantic import BaseModel, computed_field

from ws_sync import (
    Session,
    SyncedAsCamelCase,
    remote_action,
    sync_all,
    sync_only,
)
from ws_sync.session import session_context


class Note(BaseModel):
    content: str


class Notes(BaseModel):
    title: str
    entries: list[Note]


# User's example pattern
@sync_only(
    # omit entries from syncing
    title=...,
    num_entries=...,
    _toCamelCase=True,
)
class SyncedNotes(SyncedAsCamelCase, Notes):
    @computed_field
    @property
    def num_entries(self) -> int:
        return len(self.entries)

    @remote_action
    async def add_note(self, new_note: Note):
        self.entries.append(new_note)
        await self.sync(toast="Note added!", type="success")

    @remote_action
    async def clear_notes(self):
        self.entries = []
        await self.sync(toast="Notes cleared!", type="success")


@sync_all(exclude=["secret"], toCamelCase=True)
class AllSyncedNotes(SyncedAsCamelCase, Notes):
    secret: str = "hidden"  # noqa: S105

    @computed_field
    @property
    def num_entries(self) -> int:
        return len(self.entries)


@sync_all()
class SimpleClass:
    def __init__(self):
        self.x = 1
        self._private = 2


@pytest.mark.asyncio
async def test_class_decorator_schema():
    """Test that class decorator correctly configures the schema."""

    schemas, definitions = SyncedNotes.ws_sync_json_schema()

    # Check that MODEL STATE schema only includes title and num_entries
    model_state_key = ("MODEL STATE", "serialization")
    assert model_state_key in schemas

    # Depending on implementation, it might be a $ref or the actual schema
    schema = schemas[model_state_key]
    if "$ref" in schema:
        ref_name = schema["$ref"].split("/")[-1]
        schema = definitions["$defs"][ref_name]

    properties = schema.get("properties", {})
    assert "title" in properties
    assert "numEntries" in properties
    assert "entries" not in properties  # Should be excluded


@pytest.mark.asyncio
async def test_class_decorator_sync_all_schema():
    """Test that sync_all class decorator works."""
    schemas, definitions = AllSyncedNotes.ws_sync_json_schema()

    model_state_key = ("MODEL STATE", "serialization")
    schema = schemas[model_state_key]
    if "$ref" in schema:
        ref_name = schema["$ref"].split("/")[-1]
        schema = definitions["$defs"][ref_name]

    properties = schema.get("properties", {})
    assert "title" in properties
    assert "entries" in properties
    assert "numEntries" in properties
    assert "secret" not in properties


@pytest.mark.asyncio
async def test_class_decorator_runtime():
    """Test that the class decorator correctly sets up the sync object at runtime."""

    session = Session()
    token = session_context.set(session)
    try:
        notes = SyncedNotes(title="My Notes", entries=[])

        # Check if sync object is initialized
        assert notes.sync is not None
        assert notes.sync.key == "SyncedNotes"

        # Check if attributes are synced
        assert "title" in notes.sync.sync_attributes
        assert "num_entries" in notes.sync.sync_attributes
        assert "entries" not in notes.sync.sync_attributes

        # Verify camelCase
        assert notes.sync.sync_attributes["title"] == "title"
        assert notes.sync.sync_attributes["num_entries"] == "numEntries"

    finally:
        session_context.reset(token)


@pytest.mark.asyncio
async def test_class_decorator_vanilla_class():
    """Test that the class decorator works on vanilla classes."""

    session = Session()
    token = session_context.set(session)
    try:
        obj = SimpleClass()

        # Check if sync object is initialized
        # Use getattr because Pyright doesn't know about injected 'sync' attribute on vanilla class
        sync_obj = getattr(obj, "sync", None)
        assert sync_obj is not None
        assert sync_obj.key == "SimpleClass"

        # Check if attributes are synced
        assert "x" in sync_obj.sync_attributes
        assert "_private" not in sync_obj.sync_attributes

    finally:
        session_context.reset(token)
