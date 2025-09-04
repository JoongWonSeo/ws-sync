from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict, Field

from ws_sync.utils.json_schema import CustomGenerateJsonSchema


class SimpleModel(BaseModel):
    # same schema for validation and serialization
    name: str
    age: int


class DefaultedModel(BaseModel):
    # divergent: serialization includes defaults if configured
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    name: str = "John"
    age: int


class AliasModel(BaseModel):
    # aliasing does not create divergence between validation and serialization schemas here
    name: str = Field(alias="full_name")

    model_config = ConfigDict(populate_by_name=True)


@pytest.mark.parametrize(
    ("model_cls", "expected_val", "expected_ser"),
    [
        (SimpleModel, "SimpleModel", "SimpleModel"),
        (DefaultedModel, "CreateDefaultedModel", "DefaultedModel"),
        (AliasModel, "AliasModel", "AliasModel"),
    ],
)
def test_schema_def_names(
    model_cls: type[BaseModel], expected_val: str, expected_ser: str
) -> None:
    # Use models_json_schema to force $defs and $ref
    from pydantic.json_schema import models_json_schema

    (schemas_map, envelope) = models_json_schema(
        [(model_cls, "serialization"), (model_cls, "validation")],
        schema_generator=CustomGenerateJsonSchema,
    )

    assert "$defs" in envelope

    ser_schema = schemas_map[(model_cls, "serialization")]
    val_schema = schemas_map[(model_cls, "validation")]

    # Find the model's own $ref key
    def extract_ref_name(schema: dict) -> str:
        ref = schema.get("$ref")
        assert isinstance(ref, str) and ref.startswith("#/$defs/")
        return ref.split("#/$defs/")[-1]

    ser_ref = extract_ref_name(ser_schema)
    val_ref = extract_ref_name(val_schema)

    assert ser_ref == expected_ser
    assert val_ref == expected_val


def test_collision_handling_different_modules() -> None:
    # Two distinct models with different names should map directly to their base names
    class User(BaseModel):
        id: int

    class User2(BaseModel):
        id: int

    from pydantic.json_schema import models_json_schema

    (schemas_map, envelope) = models_json_schema(
        [(User, "serialization"), (User2, "serialization")],
        schema_generator=CustomGenerateJsonSchema,
    )

    ser_ref_1 = schemas_map[(User, "serialization")]["$ref"].split("#/$defs/")[-1]
    ser_ref_2 = schemas_map[(User2, "serialization")]["$ref"].split("#/$defs/")[-1]

    assert ser_ref_1 == "User"
    assert ser_ref_2 == "User2"
