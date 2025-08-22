from dataclasses import dataclass
from unittest.mock import Mock

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError, computed_field

from ws_sync.decorators import sync_all
from ws_sync.sync import Sync
from ws_sync.synced_model import Synced, SyncedAsCamelCase

from .utils import get_patch


class Person(SyncedAsCamelCase, BaseModel):
    first_name: str
    last_name: str

    @sync_all("PERSON")
    def model_post_init(self, context):
        ...
        # self.sync = Sync.all(self, key="PERSON")


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


class PersonWithComputedField(SyncedAsCamelCase, BaseModel):
    first_name: str
    last_name: str

    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def model_post_init(self, context):
        self.sync = Sync.all(self, key="PERSON_COMPUTED")


@dataclass
class Address:
    street: str
    city: str
    zipcode: str


class ContactInfo(BaseModel):
    email: str
    phone: str | None = None


class UserProfile(SyncedAsCamelCase, BaseModel):
    user_id: int
    name: str
    contact: ContactInfo

    @computed_field
    @property
    def address_info(self) -> Address:
        return Address(street="123 Main St", city="Anytown", zipcode="12345")

    @computed_field
    @property
    def profile_summary(self) -> dict:
        return {
            "id": self.user_id,
            "display_name": self.name,
            "has_phone": self.contact.phone is not None,
        }

    @computed_field
    @property
    def contact_methods(self) -> list[str]:
        methods = ["email"]
        if self.contact.phone:
            methods.append("phone")
        return methods

    @computed_field
    @property
    def preferred_contact(self) -> str | None:
        if self.contact.phone:
            return "phone"
        return "email" if self.contact.email else None

    def model_post_init(self, context):
        self.sync = Sync.all(self, key="USER_PROFILE")


class UserWithWritableComputedFields(SyncedAsCamelCase, BaseModel):
    """Model with computed fields that have both getters and setters"""

    first_name: str
    last_name: str
    _nickname: str | None = None

    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @full_name.setter
    def full_name(self, value: str) -> None:
        parts = value.split(" ", 1)
        self.first_name = parts[0]
        self.last_name = parts[1] if len(parts) > 1 else ""

    @computed_field
    @property
    def display_name(self) -> str:
        return self._nickname or self.full_name

    @display_name.setter
    def display_name(self, value: str) -> None:
        # If it matches full name format, update names; otherwise set as nickname
        if " " in value and not self._nickname:
            self.full_name = value
        else:
            self._nickname = value

    def model_post_init(self, context):
        self.sync = Sync.all(self, key="USER_WRITABLE")


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


# computed field behavior


def test_computed_field_snapshot(mock_session: Mock):
    p = PersonWithComputedField(first_name="John", last_name="Doe")
    snapshot = p.sync._snapshot()
    assert snapshot == {"firstName": "John", "lastName": "Doe", "fullName": "John Doe"}


def test_computed_field_patch(mock_session: Mock):
    p = PersonWithComputedField(first_name="John", last_name="Doe")
    p.first_name = "Jane"
    patch = get_patch(p.sync)
    # Should include updates for both firstName and computed fullName
    assert {"op": "replace", "path": "/firstName", "value": "Jane"} in patch
    assert {"op": "replace", "path": "/fullName", "value": "Jane Doe"} in patch


def test_computed_field_dataclass_return(mock_session: Mock):
    profile = UserProfile(
        user_id=1,
        name="John Doe",
        contact=ContactInfo(email="john@example.com", phone="555-1234"),
    )
    snapshot = profile.sync._snapshot()

    # Should serialize dataclass properly
    assert "addressInfo" in snapshot
    address = snapshot["addressInfo"]
    assert address["street"] == "123 Main St"
    assert address["city"] == "Anytown"
    assert address["zipcode"] == "12345"


def test_computed_field_dict_return(mock_session: Mock):
    profile = UserProfile(
        user_id=1, name="John Doe", contact=ContactInfo(email="john@example.com")
    )
    snapshot = profile.sync._snapshot()

    # Should include computed dict field
    assert "profileSummary" in snapshot
    summary = snapshot["profileSummary"]
    assert summary["id"] == 1
    assert summary["display_name"] == "John Doe"
    assert not summary["has_phone"]


def test_computed_field_list_return(mock_session: Mock):
    profile = UserProfile(
        user_id=1,
        name="John Doe",
        contact=ContactInfo(email="john@example.com", phone="555-1234"),
    )
    snapshot = profile.sync._snapshot()

    # Should include computed list field
    assert "contactMethods" in snapshot
    methods = snapshot["contactMethods"]
    assert "email" in methods
    assert "phone" in methods


def test_computed_field_union_return(mock_session: Mock):
    # Test with phone number
    profile_with_phone = UserProfile(
        user_id=1,
        name="John Doe",
        contact=ContactInfo(email="john@example.com", phone="555-1234"),
    )
    snapshot = profile_with_phone.sync._snapshot()
    assert snapshot["preferredContact"] == "phone"

    # Test without phone number
    profile_no_phone = UserProfile(
        user_id=2, name="Jane Doe", contact=ContactInfo(email="jane@example.com")
    )
    snapshot = profile_no_phone.sync._snapshot()
    assert snapshot["preferredContact"] == "email"


def test_computed_field_update_propagation(mock_session: Mock):
    profile = UserProfile(
        user_id=1, name="John Doe", contact=ContactInfo(email="john@example.com")
    )

    # Update contact info (replace the whole object since nested mutations aren't auto-detected)
    profile.contact = ContactInfo(email="john@example.com", phone="555-1234")
    patch = get_patch(profile.sync)

    # Should update computed fields that depend on the contact change
    # Look for any contact-related patches
    contact_patches = [p for p in patch if "/contact" in p["path"]]
    assert len(contact_patches) > 0, f"No contact patches found. Patch: {patch}"

    # Look for computed field updates
    methods_patches = [p for p in patch if "/contactMethods" in p["path"]]
    assert len(methods_patches) > 0, f"No contactMethods patches found. Patch: {patch}"

    preferred_patch = next((p for p in patch if p["path"] == "/preferredContact"), None)
    assert preferred_patch is not None, (
        f"No preferredContact patch found. Patch: {patch}"
    )
    assert preferred_patch["value"] == "phone"

    # Check that profile summary computed field also updates
    summary_patches = [p for p in patch if "/profileSummary" in p["path"]]
    assert len(summary_patches) > 0, f"No profileSummary patches found. Patch: {patch}"


# Bidirectional tests: WebSocket → Python deserialization


@pytest.mark.asyncio
async def test_computed_field_patch_deserialization(mock_session: Mock):
    """Test that computed fields are updated when underlying fields change via patches"""
    p = PersonWithComputedField(first_name="John", last_name="Doe")

    # Apply patch to change first name (regular field)
    await p.sync._patch_state(
        [{"op": "replace", "path": "/firstName", "value": "Jane"}]
    )

    # Verify the regular field was updated
    assert p.first_name == "Jane"
    # Computed field should automatically reflect the change
    assert p.full_name == "Jane Doe"


@pytest.mark.asyncio
async def test_computed_field_set_state_deserialization(mock_session: Mock):
    """Test that computed fields are recalculated when regular fields are set via state"""
    profile = UserProfile(
        user_id=1, name="John Doe", contact=ContactInfo(email="john@example.com")
    )

    # Set new state from frontend (only include regular fields)
    new_state = {
        "userId": 2,
        "name": "Jane Smith",
        "contact": {"email": "jane@example.com", "phone": "555-9999"},
    }

    await profile.sync._set_state(new_state)

    # Verify regular fields were properly deserialized with correct types
    assert profile.user_id == 2
    assert profile.name == "Jane Smith"
    assert isinstance(profile.contact, ContactInfo)
    assert profile.contact.email == "jane@example.com"
    assert profile.contact.phone == "555-9999"

    # Verify computed fields automatically reflect the new data
    assert isinstance(profile.address_info, Address)
    assert profile.address_info.street == "123 Main St"  # Default value
    assert profile.profile_summary["id"] == 2  # Updated from user_id
    assert profile.profile_summary["display_name"] == "Jane Smith"  # Updated from name
    assert profile.profile_summary["has_phone"] is True  # Updated from contact.phone
    assert "phone" in profile.contact_methods  # Updated from contact.phone
    assert profile.preferred_contact == "phone"  # Updated from contact.phone


@pytest.mark.asyncio
async def test_computed_field_complex_type_deserialization(mock_session: Mock):
    """Test that regular fields with complex types are properly deserialized via type adapters"""
    profile = UserProfile(
        user_id=1, name="John Doe", contact=ContactInfo(email="john@example.com")
    )

    # Apply patch to nested ContactInfo object - should use type adapter for proper deserialization
    await profile.sync._patch_state(
        [
            {
                "op": "replace",
                "path": "/contact",
                "value": {"email": "new@example.com", "phone": "555-7777"},
            }
        ]
    )

    # Verify the ContactInfo object was properly deserialized (not just a dict)
    assert isinstance(profile.contact, ContactInfo)
    assert profile.contact.email == "new@example.com"
    assert profile.contact.phone == "555-7777"

    # Verify computed fields automatically reflect the change
    assert profile.preferred_contact == "phone"
    assert "phone" in profile.contact_methods
    assert profile.profile_summary["has_phone"] is True


@pytest.mark.asyncio
async def test_computed_field_nested_patch_deserialization(mock_session: Mock):
    """Test nested patches on regular fields trigger computed field updates"""
    profile = UserProfile(
        user_id=1, name="John Doe", contact=ContactInfo(email="john@example.com")
    )

    # Apply nested patch to contact phone field
    await profile.sync._patch_state(
        [{"op": "replace", "path": "/contact/phone", "value": "555-9999"}]
    )

    # Verify the nested ContactInfo field was properly updated
    assert isinstance(profile.contact, ContactInfo)
    assert profile.contact.phone == "555-9999"
    assert profile.contact.email == "john@example.com"  # Unchanged

    # Verify computed fields automatically reflect the nested change
    assert profile.preferred_contact == "phone"
    assert "phone" in profile.contact_methods
    assert profile.profile_summary["has_phone"] is True


@pytest.mark.asyncio
async def test_type_adapter_validation_during_patch(mock_session: Mock):
    """Test that type adapters properly validate and coerce values during patch application"""
    profile = UserProfile(
        user_id=1, name="John Doe", contact=ContactInfo(email="john@example.com")
    )

    # Apply patch with string value for user_id (should be coerced to int)
    await profile.sync._patch_state(
        [{"op": "replace", "path": "/userId", "value": "42"}]
    )

    # Verify type adapter properly coerced string to int
    assert isinstance(profile.user_id, int)
    assert profile.user_id == 42

    # Verify computed field reflects the change
    assert profile.profile_summary["id"] == 42


@pytest.mark.asyncio
async def test_type_adapter_validation_during_set_state(mock_session: Mock):
    """Test that type adapters work correctly during full state setting"""
    profile = UserProfile(
        user_id=1, name="John Doe", contact=ContactInfo(email="john@example.com")
    )

    # Set state with mixed types that need validation/coercion
    new_state = {
        "userId": "123",  # String that should become int
        "name": "Jane Smith",
        "contact": {  # Dict that should become ContactInfo
            "email": "jane@example.com",
            "phone": None,
        },
    }

    await profile.sync._set_state(new_state)

    # Verify type adapters properly handled all types
    assert isinstance(profile.user_id, int)
    assert profile.user_id == 123
    assert isinstance(profile.name, str)
    assert profile.name == "Jane Smith"
    assert isinstance(profile.contact, ContactInfo)
    assert profile.contact.email == "jane@example.com"
    assert profile.contact.phone is None

    # Verify computed fields work with validated types
    assert profile.profile_summary["id"] == 123
    assert profile.profile_summary["display_name"] == "Jane Smith"
    assert not profile.profile_summary["has_phone"]
    assert profile.preferred_contact == "email"


# Writable computed field tests


@pytest.mark.asyncio
async def test_writable_computed_field_patch_deserialization(mock_session: Mock):
    """Test that writable computed fields can be set via patches"""
    user = UserWithWritableComputedFields(first_name="John", last_name="Doe")

    # Apply patch to writable computed field
    await user.sync._patch_state(
        [{"op": "replace", "path": "/fullName", "value": "Jane Smith"}]
    )

    # Verify the setter was called and underlying fields were updated
    assert user.first_name == "Jane"
    assert user.last_name == "Smith"
    assert user.full_name == "Jane Smith"


@pytest.mark.asyncio
async def test_writable_computed_field_set_state_deserialization(mock_session: Mock):
    """Test that writable computed fields work correctly in set_state"""
    user = UserWithWritableComputedFields(first_name="John", last_name="Doe")

    # Set state with writable computed fields
    new_state = {
        "firstName": "Alice",
        "lastName": "Johnson",
        "fullName": "Bob Wilson",  # This should override the firstName/lastName via setter
        "displayName": "Bobby",
    }

    await user.sync._set_state(new_state)

    # fullName setter should have been called last, overriding the individual names
    assert user.first_name == "Bob"
    assert user.last_name == "Wilson"
    assert user.full_name == "Bob Wilson"
    assert user.display_name == "Bobby"  # Nickname was set
    assert user._nickname == "Bobby"


@pytest.mark.asyncio
async def test_writable_computed_field_complex_setter_logic(mock_session: Mock):
    """Test complex setter logic for writable computed fields"""
    user = UserWithWritableComputedFields(first_name="John", last_name="Doe")

    # Test display_name setter with full name format
    await user.sync._patch_state(
        [{"op": "replace", "path": "/displayName", "value": "Alice Johnson"}]
    )

    # Should update underlying names since no nickname was set
    assert user.first_name == "Alice"
    assert user.last_name == "Johnson"
    assert user._nickname is None
    assert user.display_name == "Alice Johnson"

    # Now set a nickname
    await user.sync._patch_state(
        [{"op": "replace", "path": "/displayName", "value": "AJ"}]
    )

    # Should set nickname instead of changing names
    assert user.first_name == "Alice"  # Unchanged
    assert user.last_name == "Johnson"  # Unchanged
    assert user._nickname == "AJ"
    assert user.display_name == "AJ"


@pytest.mark.asyncio
async def test_writable_computed_field_type_validation(mock_session: Mock):
    """Test that writable computed fields use type adapters for validation"""
    user = UserWithWritableComputedFields(first_name="John", last_name="Doe")

    # Test that type adapter validates string input for computed field
    await user.sync._patch_state(
        [{"op": "replace", "path": "/fullName", "value": "Jane Smith"}]
    )

    # Verify proper string handling and setter invocation
    assert isinstance(user.full_name, str)
    assert user.full_name == "Jane Smith"
    assert isinstance(user.first_name, str)
    assert user.first_name == "Jane"
    assert isinstance(user.last_name, str)
    assert user.last_name == "Smith"


def test_writable_computed_field_snapshot_includes_setters(mock_session: Mock):
    """Test that writable computed fields are included in snapshots"""
    user = UserWithWritableComputedFields(first_name="John", last_name="Doe")
    snapshot = user.sync._snapshot()

    # Should include both readable and writable computed fields
    assert "fullName" in snapshot
    assert "displayName" in snapshot
    assert snapshot["fullName"] == "John Doe"
    assert snapshot["displayName"] == "John Doe"  # No nickname set


def test_writable_computed_field_patch_generation(mock_session: Mock):
    """Test that changes to writable computed fields generate proper patches"""
    user = UserWithWritableComputedFields(first_name="John", last_name="Doe")

    # Manually change the computed field via setter
    user.full_name = "Jane Smith"
    patch = get_patch(user.sync)

    # Should generate patches for all affected fields
    first_name_patch = next((p for p in patch if p["path"] == "/firstName"), None)
    last_name_patch = next((p for p in patch if p["path"] == "/lastName"), None)
    full_name_patch = next((p for p in patch if p["path"] == "/fullName"), None)

    assert first_name_patch is not None
    assert first_name_patch["value"] == "Jane"
    assert last_name_patch is not None
    assert last_name_patch["value"] == "Smith"
    assert full_name_patch is not None
    assert full_name_patch["value"] == "Jane Smith"
