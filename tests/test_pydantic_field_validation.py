"""
Comprehensive tests for Pydantic Field validations in ws-sync.

This test suite validates that Pydantic Field constraints work correctly across
different contexts in the ws-sync library, including:

1. Model creation and validation
2. Field constraints (min/max length, numeric bounds, patterns, etc.)
3. Field aliases and serialization
4. Remote action parameter validation (via sync.actions())
5. Remote task parameter validation (via sync.tasks())
6. Sync operation behavior with and without validate_assignment=True
7. Field validator behavior in different contexts

Key Insights:
- Field validation DOES work for remote actions and tasks through TypeAdapter validation
- Field validation is BYPASSED during sync operations by default (TypeAdapter limitation, not intentional)
- With model_config = ConfigDict(validate_assignment=True), Field validation WORKS in sync operations
- Type coercion still works during sync operations via TypeAdapters
- Field validators (like custom strip_whitespace) work with validate_assignment=True
- Remote actions use sync.actions(), remote tasks use sync.tasks()
"""

from decimal import Decimal
from unittest.mock import Mock

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ws_sync.decorators import remote_action, remote_task
from ws_sync.sync import Sync
from ws_sync.synced_model import Synced, SyncedAsCamelCase

from .utils import get_patch

# Test Models with Field Validations


class StringValidationModel(SyncedAsCamelCase, BaseModel):
    # Basic string constraints
    short_name: str = Field(min_length=2, max_length=10)
    email: str = Field(pattern=r"^[^@]+@[^@]+\.[^@]+$")
    trimmed_field: str = Field()
    optional_description: str | None = Field(default=None, max_length=100)

    @field_validator("trimmed_field")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()

    def model_post_init(self, context):
        self.sync = Sync.all(self, key="STRING_VALIDATION")


class NumericValidationModel(SyncedAsCamelCase, BaseModel):
    # Numeric constraints
    positive_int: int = Field(gt=0)
    percentage: int = Field(ge=0, le=100)
    price: Decimal = Field(gt=Decimal("0.0"), decimal_places=2)
    optional_score: float | None = Field(default=None, ge=0.0, le=10.0)

    def model_post_init(self, context):
        self.sync = Sync.all(self, key="NUMERIC_VALIDATION")


class AliasedModel(SyncedAsCamelCase, BaseModel):
    # Field with alias and description
    internal_id: int = Field(alias="id", description="Internal identifier")
    user_name: str = Field(alias="username", min_length=3, max_length=20)
    is_active: bool = Field(
        alias="active", default=True, description="User active status"
    )

    def model_post_init(self, context):
        self.sync = Sync.all(self, key="ALIASED_MODEL")


class ComplexValidationModel(SyncedAsCamelCase, BaseModel):
    # Complex validation combining multiple constraints
    product_code: str = Field(
        pattern=r"^[A-Z]{2}-\d{4}$", description="Product code format: XX-9999"
    )
    discount_rate: Decimal = Field(
        ge=Decimal("0.00"),
        le=Decimal("1.00"),
        decimal_places=2,
        description="Discount rate between 0.00 and 1.00",
    )
    tags: list[str] = Field(min_length=1, max_length=5, description="1-5 product tags")

    @field_validator("tags")
    def validate_tag_format(cls, v):
        for tag in v:
            if not tag.strip() or len(tag) > 20:
                raise ValueError("Each tag must be 1-20 characters")
        return v

    def model_post_init(self, context):
        self.sync = Sync.all(self, key="COMPLEX_VALIDATION")


# Remote Action/Task Models with Field Validation


class UserActionModel(Synced, BaseModel):
    name: str
    email: str

    def model_post_init(self, context):
        self.sync = Sync.all(self, key="USER_ACTIONS")

    @remote_action("UPDATE_NAME")
    async def update_name(
        self,
        new_name: str = Field(
            min_length=2, max_length=50, description="User's new name"
        ),
    ):
        self.name = new_name
        await self.sync()
        return {"success": True, "name": self.name}

    @remote_action("UPDATE_EMAIL")
    async def update_email(
        self,
        new_email: str = Field(
            pattern=r"^[^@]+@[^@]+\.[^@]+$", description="Valid email address"
        ),
    ):
        self.email = new_email
        await self.sync()
        return {"success": True, "email": self.email}

    @remote_task("BULK_UPDATE")
    async def bulk_update(
        self,
        name: str = Field(min_length=2, max_length=50),
        email: str = Field(pattern=r"^[^@]+@[^@]+\.[^@]+$"),
        batch_size: int = Field(gt=0, le=100, default=10),
    ):
        self.name = name
        self.email = email
        await self.sync()
        return {"updated": True, "batch_size": batch_size}


# Test Models with validate_assignment=True


class StringValidationModelWithAssignment(SyncedAsCamelCase, BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    # Basic string constraints
    short_name: str = Field(min_length=2, max_length=10)
    email: str = Field(pattern=r"^[^@]+@[^@]+\.[^@]+$")
    trimmed_field: str = Field()
    optional_description: str | None = Field(default=None, max_length=100)

    @field_validator("trimmed_field")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()

    def model_post_init(self, context):
        self.sync = Sync.all(self, key="STRING_VALIDATION_WITH_ASSIGNMENT")


class NumericValidationModelWithAssignment(SyncedAsCamelCase, BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    # Numeric constraints
    positive_int: int = Field(gt=0)
    percentage: int = Field(ge=0, le=100)
    price: Decimal = Field(gt=Decimal("0.0"), decimal_places=2)
    optional_score: float | None = Field(default=None, ge=0.0, le=10.0)

    def model_post_init(self, context):
        self.sync = Sync.all(self, key="NUMERIC_VALIDATION_WITH_ASSIGNMENT")


# Basic Field Constraint Tests


def test_string_field_min_max_length(mock_session: Mock):
    # Valid length
    model = StringValidationModel(
        short_name="John", email="john@example.com", trimmed_field="  test  "
    )
    assert model.short_name == "John"
    assert model.trimmed_field == "test"  # Should be trimmed

    # Test min_length constraint
    with pytest.raises(ValidationError) as exc_info:
        StringValidationModel(
            short_name="J",  # Too short
            email="john@example.com",
            trimmed_field="test",
        )
    assert "at least 2 characters" in str(exc_info.value)

    # Test max_length constraint
    with pytest.raises(ValidationError) as exc_info:
        StringValidationModel(
            short_name="VeryLongName",  # Too long
            email="john@example.com",
            trimmed_field="test",
        )
    assert "at most 10 characters" in str(exc_info.value)


def test_string_field_regex_validation(mock_session: Mock):
    # Valid email
    model = StringValidationModel(
        short_name="John", email="john@example.com", trimmed_field="test"
    )
    assert model.email == "john@example.com"

    # Invalid email format
    with pytest.raises(ValidationError) as exc_info:
        StringValidationModel(
            short_name="John",
            email="invalid-email",  # No @ or domain
            trimmed_field="test",
        )
    assert "String should match pattern" in str(exc_info.value)


def test_numeric_field_constraints(mock_session: Mock):
    # Valid numeric values
    model = NumericValidationModel(
        positive_int=5, percentage=75, price=Decimal("19.99")
    )
    assert model.positive_int == 5
    assert model.percentage == 75
    assert model.price == Decimal("19.99")

    # Test gt constraint (positive_int must be > 0)
    with pytest.raises(ValidationError) as exc_info:
        NumericValidationModel(
            positive_int=0,  # Should be > 0
            percentage=75,
            price=Decimal("19.99"),
        )
    assert "greater than 0" in str(exc_info.value)

    # Test ge/le constraints (percentage 0-100)
    with pytest.raises(ValidationError) as exc_info:
        NumericValidationModel(
            positive_int=5,
            percentage=101,  # Should be <= 100
            price=Decimal("19.99"),
        )
    assert "less than or equal to 100" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        NumericValidationModel(
            positive_int=5,
            percentage=-1,  # Should be >= 0
            price=Decimal("19.99"),
        )
    assert "greater than or equal to 0" in str(exc_info.value)


def test_field_aliases(mock_session: Mock):
    # Create model using aliases
    model = AliasedModel(id=123, username="johndoe", active=True)
    assert model.internal_id == 123
    assert model.user_name == "johndoe"
    assert model.is_active is True

    # Test camelCase serialization includes aliases
    snapshot = model.sync._snapshot()
    assert "id" in snapshot  # Alias should be used
    assert "username" in snapshot
    assert "active" in snapshot
    assert snapshot["id"] == 123
    assert snapshot["username"] == "johndoe"
    assert snapshot["active"] is True

    # Test alias validation
    with pytest.raises(ValidationError) as exc_info:
        AliasedModel(id=123, username="xy", active=True)  # username too short
    assert "at least 3 characters" in str(exc_info.value)


def test_complex_field_validation(mock_session: Mock):
    # Valid complex model
    model = ComplexValidationModel(
        product_code="AB-1234",
        discount_rate=Decimal("0.15"),
        tags=["electronics", "premium"],
    )
    assert model.product_code == "AB-1234"
    assert model.discount_rate == Decimal("0.15")
    assert model.tags == ["electronics", "premium"]

    # Test regex pattern
    with pytest.raises(ValidationError) as exc_info:
        ComplexValidationModel(
            product_code="invalid",  # Should match XX-9999 pattern
            discount_rate=Decimal("0.15"),
            tags=["electronics"],
        )
    assert "String should match pattern" in str(exc_info.value)

    # Test decimal constraints
    with pytest.raises(ValidationError) as exc_info:
        ComplexValidationModel(
            product_code="AB-1234",
            discount_rate=Decimal("1.50"),  # Should be <= 1.00
            tags=["electronics"],
        )
    assert "less than or equal to 1" in str(exc_info.value)

    # Test list length constraints
    with pytest.raises(ValidationError) as exc_info:
        ComplexValidationModel(
            product_code="AB-1234",
            discount_rate=Decimal("0.15"),
            tags=[],  # Should have at least 1 item
        )
    assert "at least 1 item" in str(exc_info.value)

    # Test custom validator
    with pytest.raises(ValidationError) as exc_info:
        ComplexValidationModel(
            product_code="AB-1234",
            discount_rate=Decimal("0.15"),
            tags=["a" * 21],  # Tag too long
        )
    assert "Each tag must be 1-20 characters" in str(exc_info.value)


# Sync Operation Tests


@pytest.mark.asyncio
async def test_field_validation_in_patch_operations(mock_session: Mock):
    """Test behavior of Field constraints during sync patch operations.

    Note: Field validation constraints are NOT enforced during patch operations
    by default due to TypeAdapter limitations (not intentional design choice).
    Use validate_assignment=True to enable validation during sync operations.
    """
    model = StringValidationModel(
        short_name="John", email="john@example.com", trimmed_field="test"
    )

    # Valid patch works as expected
    await model.sync._patch_state(
        [{"op": "replace", "path": "/shortName", "value": "Jane"}]
    )
    assert model.short_name == "Jane"

    # Invalid values that would fail Field validation are still accepted
    # during patch operations (validation is skipped for performance)
    await model.sync._patch_state(
        [
            {
                "op": "replace",
                "path": "/shortName",
                "value": "J",
            }  # Too short, but allowed
        ]
    )
    assert model.short_name == "J"  # Value is accepted despite constraint violation

    # Similarly, invalid email patterns are accepted during patch
    await model.sync._patch_state(
        [{"op": "replace", "path": "/email", "value": "invalid-email"}]
    )
    assert model.email == "invalid-email"  # Accepted despite pattern mismatch


@pytest.mark.asyncio
async def test_field_validation_in_set_state(mock_session: Mock):
    """Test behavior of Field constraints during sync set_state operations.

    Like patch operations, set_state also skips Field validation due to
    TypeAdapter limitations, but still applies type coercion where possible.
    Use validate_assignment=True to enable validation during sync operations.
    """
    model = NumericValidationModel(
        positive_int=5, percentage=75, price=Decimal("19.99")
    )

    # Valid state update with type coercion
    await model.sync._set_state(
        {
            "positiveInt": 10,
            "percentage": 80,
            "price": "29.99",  # String will be converted to Decimal via TypeAdapter
        }
    )
    assert model.positive_int == 10
    assert model.percentage == 80
    assert model.price == Decimal("29.99")

    # Invalid values that violate Field constraints are still accepted
    # (validation is bypassed but type coercion still happens)
    await model.sync._set_state(
        {
            "positiveInt": -1,  # Violates gt=0 constraint but still accepted
            "percentage": 150,  # Violates le=100 constraint but still accepted
            "price": "0.00",  # Violates gt=0.0 constraint but still accepted
        }
    )
    assert model.positive_int == -1  # Accepted despite constraint violation
    assert model.percentage == 150  # Accepted despite constraint violation
    assert model.price == Decimal("0.00")  # Accepted despite constraint violation


@pytest.mark.asyncio
async def test_field_validation_preserves_whitespace_trimming(mock_session: Mock):
    """Test that field validators apply during model creation.

    Note: Field validators like strip_whitespace only apply during initial
    validation (model creation) by default, not during patch/set_state operations
    due to TypeAdapter limitations. Use validate_assignment=True to enable them.
    """
    model = StringValidationModel(
        short_name="John", email="john@example.com", trimmed_field="  initial  "
    )

    # Verify initial trimming during creation
    assert model.trimmed_field == "initial"

    # During patch operations, field validators are not applied
    # to preserve performance - the sync system trusts the frontend data
    await model.sync._patch_state(
        [{"op": "replace", "path": "/trimmedField", "value": "  updated  "}]
    )
    # Field validator is NOT called during sync operations
    assert model.trimmed_field == "  updated  "

    # Similarly for set_state operations
    await model.sync._set_state(
        {"shortName": "Jane", "email": "jane@example.com", "trimmedField": "  final  "}
    )
    # Field validator is NOT called during sync operations
    assert model.trimmed_field == "  final  "


# validate_assignment=True Tests


@pytest.mark.asyncio
async def test_validate_assignment_enables_field_validation_in_patch(
    mock_session: Mock,
):
    """Test that validate_assignment=True enables Field validation during patch operations."""
    model = StringValidationModelWithAssignment(
        short_name="John", email="john@example.com", trimmed_field="test"
    )

    # Valid patch should work
    await model.sync._patch_state(
        [{"op": "replace", "path": "/shortName", "value": "Jane"}]
    )
    assert model.short_name == "Jane"

    # Invalid patch should now raise ValidationError (unlike models without validate_assignment)
    with pytest.raises(ValidationError) as exc_info:
        await model.sync._patch_state(
            [
                {"op": "replace", "path": "/shortName", "value": "J"}  # Too short
            ]
        )
    assert "at least 2 characters" in str(exc_info.value)
    assert model.short_name == "Jane"  # Should remain unchanged

    # Test email pattern validation during patch
    with pytest.raises(ValidationError) as exc_info:
        await model.sync._patch_state(
            [{"op": "replace", "path": "/email", "value": "invalid-email"}]
        )
    assert "String should match pattern" in str(exc_info.value)
    assert model.email == "john@example.com"  # Should remain unchanged


@pytest.mark.asyncio
async def test_validate_assignment_enables_field_validation_in_set_state(
    mock_session: Mock,
):
    """Test that validate_assignment=True enables Field validation during set_state operations."""
    model = NumericValidationModelWithAssignment(
        positive_int=5, percentage=75, price=Decimal("19.99")
    )

    # Valid state update should work
    await model.sync._set_state({"positiveInt": 10, "percentage": 80, "price": "29.99"})
    assert model.positive_int == 10
    assert model.percentage == 80
    assert model.price == Decimal("29.99")

    # Invalid state should now raise ValidationError (unlike models without validate_assignment)
    with pytest.raises(ValidationError) as exc_info:
        await model.sync._set_state(
            {
                "positiveInt": -1,  # Violates gt=0
                "percentage": 80,
                "price": "29.99",
            }
        )
    assert "greater than 0" in str(exc_info.value)

    # Test percentage bounds validation
    with pytest.raises(ValidationError) as exc_info:
        await model.sync._set_state(
            {
                "positiveInt": 10,
                "percentage": 150,  # Violates le=100
                "price": "29.99",
            }
        )
    assert "less than or equal to 100" in str(exc_info.value)


@pytest.mark.asyncio
async def test_validate_assignment_enables_field_validators_in_sync(mock_session: Mock):
    """Test that validate_assignment=True enables field validators during sync operations."""
    model = StringValidationModelWithAssignment(
        short_name="John", email="john@example.com", trimmed_field="  initial  "
    )

    # Verify initial trimming during creation
    assert model.trimmed_field == "initial"

    # With validate_assignment=True, field validators should now work in patch
    await model.sync._patch_state(
        [{"op": "replace", "path": "/trimmedField", "value": "  updated  "}]
    )
    assert (
        model.trimmed_field == "updated"
    )  # Should be trimmed due to validate_assignment

    # Test trimming in set_state as well
    await model.sync._set_state(
        {"shortName": "Jane", "email": "jane@example.com", "trimmedField": "  final  "}
    )
    assert (
        model.trimmed_field == "final"
    )  # Should be trimmed due to validate_assignment


def test_validate_assignment_comparison_with_regular_models(mock_session: Mock):
    """Compare behavior between models with and without validate_assignment."""
    # Regular model (no validate_assignment)
    regular_model = StringValidationModel(
        short_name="John", email="john@example.com", trimmed_field="test"
    )

    # Assignment validation model
    assignment_model = StringValidationModelWithAssignment(
        short_name="John", email="john@example.com", trimmed_field="test"
    )

    # Direct assignment to regular model: no validation
    regular_model.short_name = "X"  # Too short, but allowed
    assert regular_model.short_name == "X"

    # Direct assignment to validation model: validation enforced
    with pytest.raises(ValidationError) as exc_info:
        assignment_model.short_name = "X"  # Too short, should fail
    assert "at least 2 characters" in str(exc_info.value)
    assert assignment_model.short_name == "John"  # Should remain unchanged


def test_practical_example_field_validation_in_sync_operations(mock_session: Mock):
    """Practical example showing the impact of validate_assignment on sync operations."""

    # Scenario: User profile with email validation
    class UserProfile(SyncedAsCamelCase, BaseModel):
        name: str = Field(min_length=2)
        email: str = Field(pattern=r"^[^@]+@[^@]+\.[^@]+$")

        def model_post_init(self, context):
            self.sync = Sync.all(self, key="USER_PROFILE")

    class ValidatedUserProfile(SyncedAsCamelCase, BaseModel):
        model_config = ConfigDict(validate_assignment=True)

        name: str = Field(min_length=2)
        email: str = Field(pattern=r"^[^@]+@[^@]+\.[^@]+$")

        def model_post_init(self, context):
            self.sync = Sync.all(self, key="VALIDATED_USER_PROFILE")

    # Regular profile (no validation during sync)
    profile = UserProfile(name="John", email="john@example.com")

    # This would succeed even with invalid data during sync operations
    profile.name = "J"  # Too short, but allowed
    profile.email = "invalid"  # Invalid format, but allowed
    assert profile.name == "J"
    assert profile.email == "invalid"

    # Validated profile (validation during sync)
    validated_profile = ValidatedUserProfile(name="John", email="john@example.com")

    # These assignments should fail with validation errors
    with pytest.raises(ValidationError):
        validated_profile.name = "J"  # Too short, should fail

    with pytest.raises(ValidationError):
        validated_profile.email = "invalid"  # Invalid format, should fail

    # Original values should remain unchanged
    assert validated_profile.name == "John"
    assert validated_profile.email == "john@example.com"


# Remote Action/Task Field Validation Tests


@pytest.mark.asyncio
async def test_remote_action_field_validation_success(mock_session: Mock):
    """Test that remote actions properly validate Field constraints."""
    model = UserActionModel(name="John", email="john@example.com")

    # Valid action calls should work and not raise validation errors
    await model.sync.actions(
        {
            "type": "UPDATE_NAME",
            "new_name": "Jane Doe",  # Valid: meets min_length=2, max_length=50
        }
    )
    # Check that the action was executed successfully
    assert model.name == "Jane Doe"

    await model.sync.actions(
        {
            "type": "UPDATE_EMAIL",
            "new_email": "jane.doe@example.com",  # Valid: matches email pattern
        }
    )
    # Check that the action was executed successfully
    assert model.email == "jane.doe@example.com"


@pytest.mark.asyncio
async def test_remote_action_field_validation_failure(mock_session: Mock):
    """Test that remote actions reject invalid Field values."""
    model = UserActionModel(name="John", email="john@example.com")

    # Test name too short (violates min_length=2)
    with pytest.raises(ValidationError) as exc_info:
        await model.sync.actions(
            {
                "type": "UPDATE_NAME",
                "new_name": "J",  # Too short
            }
        )
    assert "at least 2 characters" in str(exc_info.value)
    assert model.name == "John"  # Should remain unchanged

    # Test name too long (violates max_length=50)
    with pytest.raises(ValidationError) as exc_info:
        await model.sync.actions(
            {
                "type": "UPDATE_NAME",
                "new_name": "A" * 51,  # Too long
            }
        )
    assert "at most 50 characters" in str(exc_info.value)
    assert model.name == "John"  # Should remain unchanged

    # Test invalid email format (violates pattern)
    with pytest.raises(ValidationError) as exc_info:
        await model.sync.actions(
            {
                "type": "UPDATE_EMAIL",
                "new_email": "invalid-email-format",  # No @ or domain
            }
        )
    assert "String should match pattern" in str(exc_info.value)
    assert model.email == "john@example.com"  # Should remain unchanged


@pytest.mark.asyncio
async def test_remote_task_field_validation(mock_session: Mock):
    """Test that remote tasks properly validate Field constraints."""
    model = UserActionModel(name="John", email="john@example.com")

    # Valid task call should work and not raise validation errors
    await model.sync.tasks(
        {
            "type": "BULK_UPDATE",
            "name": "Jane Smith",  # Valid name
            "email": "jane.smith@example.com",  # Valid email
            "batch_size": 25,  # Valid: gt=0, le=100
        }
    )
    # Wait for task completion
    task = model.sync.running_tasks["BULK_UPDATE"]
    await task
    # Check that the task was executed successfully
    assert model.name == "Jane Smith"
    assert model.email == "jane.smith@example.com"

    # Test invalid batch_size (violates gt=0)
    with pytest.raises(ValidationError) as exc_info:
        await model.sync.tasks(
            {
                "type": "BULK_UPDATE",
                "name": "Valid Name",
                "email": "valid@example.com",
                "batch_size": 0,  # Should be > 0
            }
        )
    assert "greater than 0" in str(exc_info.value)

    # Test invalid batch_size (violates le=100)
    with pytest.raises(ValidationError) as exc_info:
        await model.sync.tasks(
            {
                "type": "BULK_UPDATE",
                "name": "Valid Name",
                "email": "valid@example.com",
                "batch_size": 150,  # Should be <= 100
            }
        )
    assert "less than or equal to 100" in str(exc_info.value)

    # Test with invalid name and email in task
    with pytest.raises(ValidationError) as exc_info:
        await model.sync.tasks(
            {
                "type": "BULK_UPDATE",
                "name": "X",  # Too short
                "email": "invalid",  # Invalid format
                "batch_size": 10,
            }
        )
    # Should contain errors for both name and email
    error_str = str(exc_info.value)
    assert "at least 2 characters" in error_str
    assert "String should match pattern" in error_str


@pytest.mark.asyncio
async def test_remote_task_default_values_with_validation(mock_session: Mock):
    """Test that default values in remote tasks are properly validated."""
    model = UserActionModel(name="John", email="john@example.com")

    # Test using default batch_size (should be valid)
    await model.sync.tasks(
        {
            "type": "BULK_UPDATE",
            "name": "Test User",
            "email": "test@example.com",
            # batch_size not provided, should use default=10
        }
    )
    # Wait for task completion
    task = model.sync.running_tasks["BULK_UPDATE"]
    await task
    # Check that the task was executed with valid defaults
    assert model.name == "Test User"
    assert model.email == "test@example.com"


# Snapshot and Patch Generation with Field Constraints


def test_field_constraints_in_snapshots(mock_session: Mock):
    model = ComplexValidationModel(
        product_code="AB-1234",
        discount_rate=Decimal("0.15"),
        tags=["electronics", "premium"],
    )

    snapshot = model.sync._snapshot()

    # Verify all fields are properly serialized
    assert snapshot["productCode"] == "AB-1234"
    assert float(snapshot["discountRate"]) == 0.15
    assert snapshot["tags"] == ["electronics", "premium"]


def test_field_constraints_in_patch_generation(mock_session: Mock):
    model = StringValidationModel(
        short_name="John", email="john@example.com", trimmed_field="test"
    )

    # Make valid changes
    model.short_name = "Jane"
    model.email = "jane@example.com"

    patch = get_patch(model.sync)

    # Verify patches are generated correctly
    short_name_patch = next((p for p in patch if p["path"] == "/shortName"), None)
    email_patch = next((p for p in patch if p["path"] == "/email"), None)

    assert short_name_patch is not None
    assert short_name_patch["value"] == "Jane"
    assert email_patch is not None
    assert email_patch["value"] == "jane@example.com"


# Error Handling Tests


def test_validation_error_details(mock_session: Mock):
    # Test that ValidationError contains helpful field information
    try:
        StringValidationModel(
            short_name="",  # Too short
            email="invalid",  # Invalid format
            trimmed_field="test",
        )
    except ValidationError as e:
        errors = e.errors()

        # Check that errors contain field-specific information
        short_name_error = next(
            (err for err in errors if err["loc"] == ("short_name",)), None
        )
        email_error = next((err for err in errors if err["loc"] == ("email",)), None)

        assert short_name_error is not None
        assert "at least 2 characters" in short_name_error["msg"]
        assert email_error is not None
        assert "String should match pattern" in email_error["msg"]


def test_optional_field_validation(mock_session: Mock):
    # Test that optional fields work correctly
    model = StringValidationModel(
        short_name="John",
        email="john@example.com",
        trimmed_field="test",
        # optional_description not provided
    )
    assert model.optional_description is None

    # Test optional field with valid value
    model2 = StringValidationModel(
        short_name="John",
        email="john@example.com",
        trimmed_field="test",
        optional_description="A short description",
    )
    assert model2.optional_description == "A short description"

    # Test optional field with constraint violation
    with pytest.raises(ValidationError) as exc_info:
        StringValidationModel(
            short_name="John",
            email="john@example.com",
            trimmed_field="test",
            optional_description="A" * 101,  # Too long
        )
    assert "at most 100 characters" in str(exc_info.value)
