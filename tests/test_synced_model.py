from unittest.mock import Mock

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from ws_sync.sync import Sync
from ws_sync.synced_model import Synced, SyncedAsCamelCase

from .utils import get_patch


class Person(SyncedAsCamelCase, BaseModel):
    first_name: str
    last_name: str

    def model_post_init(self, context):
        self.sync = Sync.all(self, key="PERSON")


class Animal(Synced, BaseModel):
    species_name: str

    def model_post_init(self, context):
        self.sync = Sync.all(self, key="ANIMAL")


class CamelParent(SyncedAsCamelCase, BaseModel):
    nick_name: str

    def model_post_init(self, context):
        self.sync = Sync.all(self, key="PARENT")


class CamelChild(CamelParent):
    also_camel: str = ""


class PlainChild(CamelParent):
    model_config = ConfigDict(alias_generator=None, serialize_by_alias=False)
    snake_case: str = ""


# Test utilities are imported from .utils


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
    c = CamelChild(nick_name="X", also_camel="Y")
    assert c.model_dump() == {"nickName": "X", "alsoCamel": "Y"}
    c.nick_name = "A"
    assert get_patch(c.sync) == [{"op": "replace", "path": "/nickName", "value": "A"}]


def test_override_config(mock_session: Mock):
    p = PlainChild(nick_name="Y", snake_case="Z")
    assert p.model_dump() == {"nick_name": "Y", "snake_case": "Z"}
    p.nick_name = "A"
    assert get_patch(p.sync) == [{"op": "replace", "path": "/nick_name", "value": "A"}]
    p.snake_case = "B"
    assert get_patch(p.sync) == [{"op": "replace", "path": "/snake_case", "value": "B"}]
