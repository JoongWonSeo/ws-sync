import asyncio
import logging
from collections.abc import Callable
from typing import Any, cast

from pydantic import AliasGenerator, BaseModel, TypeAdapter
from pydantic_core import CoreSchema, SchemaValidator
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)


async def nonblock_call(func: Callable, *args, **kwargs):
    """Call a function without blocking the current thread."""
    if asyncio.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    logger.warning("function is not async.")
    return await run_in_threadpool(func, *args, **kwargs)


def get_alias_function_for_class(
    target_cls: type,
) -> Callable[[str], str] | None:
    """
    Get the alias function for a pydantic BaseModel subclass.Returns None if the class is not a subclass of BaseModel.
    """
    if issubclass(target_cls, BaseModel):
        alias_gen = getattr(target_cls, "model_config", {}).get("alias_generator")
        if isinstance(alias_gen, AliasGenerator):
            fn = alias_gen.serialization_alias or alias_gen.alias
            return cast("Callable[[str], str] | None", fn)
        if callable(alias_gen):
            return cast("Callable[[str], str]", alias_gen)
    return None


def find_field_schema(model: type[BaseModel], field_name: str) -> CoreSchema:
    schema: CoreSchema = model.__pydantic_core_schema__.copy()
    # we shallow copied, be careful not to mutate the original schema!

    assert schema["type"] in ["definitions", "model"]

    # find the field schema
    field_schema = schema["schema"]  # type: ignore
    while "fields" not in field_schema:
        field_schema = field_schema["schema"]  # type: ignore

    try:
        field_schema = field_schema["fields"][field_name]["schema"]  # type: ignore

        # if the original schema is a definition schema, replace the model schema with the field schema
        if schema["type"] == "definitions":
            schema["schema"] = field_schema
            return schema
        else:
            return field_schema
    except KeyError:
        # Not a regular field; check for computed fields and build a schema from the return type
        if (
            hasattr(model, "model_computed_fields")
            and field_name in model.model_computed_fields
        ):  # type: ignore[attr-defined]
            computed = model.model_computed_fields[field_name]  # type: ignore[index]
            # Build a minimal core schema for the computed field's return type
            return TypeAdapter(computed.return_type).core_schema
        # If we can't find it, re-raise a KeyError for consistency
        raise KeyError(field_name) from None


cache: dict[tuple[type[BaseModel], str], SchemaValidator] = {}


def validate_model_field(model: type[BaseModel], field_name: str, value: Any) -> Any:
    # Only enforce field-level validation during sync operations when
    # the model explicitly opts in via `validate_assignment=True`.
    # Otherwise, upstream TypeAdapters handle basic type coercion.
    # model_cfg = getattr(model, "model_config", {})
    # if not model_cfg.get("validate_assignment", False):
    #     return value

    if (validator := cache.get((model, field_name))) is None:
        validator = SchemaValidator(find_field_schema(model, field_name))
        cache[(model, field_name)] = validator

    return validator.validate_python(value)
