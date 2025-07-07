from unittest.mock import AsyncMock, Mock

import jsonpatch
import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from ws_sync.session import Session, session_context
from ws_sync.sync import Sync
from ws_sync.synced_model import Synced, SyncedAsCamelCase


class Person(SyncedAsCamelCase, BaseModel):
    first_name: str
    last_name: str

    def model_post_init(self, context):
        self.sync = Sync(self, key="PERSON", sync_all=True)


class Animal(Synced, BaseModel):
    species_name: str

    def model_post_init(self, context):
        self.sync = Sync(self, key="ANIMAL", sync_all=True)


class CamelParent(SyncedAsCamelCase, BaseModel):
    nick_name: str

    def model_post_init(self, context):
        self.sync = Sync(self, key="PARENT", sync_all=True)


class CamelChild(CamelParent):
    pass


class PlainChild(CamelParent):
    model_config = ConfigDict()


# utils


def get_patch(sync: Sync):
    prev = sync.state_snapshot
    sync.state_snapshot = sync._snapshot()
    return jsonpatch.make_patch(prev, sync.state_snapshot).patch


@pytest.fixture
def mock_session() -> Mock:
    session = Mock(spec=Session)
    session.send = AsyncMock()
    session.register_event = Mock()
    session.register_init = Mock()
    session.deregister_event = Mock()
    session.is_connected = True

    session_context.set(session)
    return session


# camelCase behavior


def test_dump_camel_case(mock_session: Mock):
    p = Person(first_name="John", last_name="Doe")
    assert p.model_dump() == {"firstName": "John", "lastName": "Doe"}


def test_snapshot_camel_case(mock_session: Mock):
    p = Person(first_name="John", last_name="Doe")
    assert p.sync._snapshot() == {"firstName": "John", "lastName": "Doe"}


def test_patch_camel_case(mock_session: Mock):
    p = Person(first_name="John", last_name="Doe")
    p.first_name = "Jane"
    assert get_patch(p.sync) == [
        {"op": "replace", "path": "/firstName", "value": "Jane"}
    ]


@pytest.mark.asyncio
async def test_patch_apply_camel_case(mock_session: Mock):
    p = Person(first_name="John", last_name="Doe")
    await p.sync._patch_state(
        [{"op": "replace", "path": "/firstName", "value": "Jane"}]
    )
    assert p.first_name == "Jane"


# snake_case behavior


def test_dump_snake_case(mock_session: Mock):
    a = Animal(species_name="Dog")
    assert a.model_dump() == {"species_name": "Dog"}


def test_snapshot_snake_case(mock_session: Mock):
    a = Animal(species_name="Dog")
    assert a.sync._snapshot() == {"species_name": "Dog"}


def test_patch_snake_case(mock_session: Mock):
    a = Animal(species_name="Dog")
    a.species_name = "Cat"
    assert get_patch(a.sync) == [
        {"op": "replace", "path": "/species_name", "value": "Cat"}
    ]


def test_init_uses_field_names(mock_session: Mock):
    with pytest.raises(ValidationError):
        Person(**{"firstName": "John", "last_name": "Doe"})


# subclass behavior


def test_inherited_config(mock_session: Mock):
    c = CamelChild(nick_name="X")
    assert c.model_dump() == {"nickName": "X"}


def test_override_config(mock_session: Mock):
    p = PlainChild(nick_name="Y")
    assert p.model_dump() == {"nick_name": "Y"}
