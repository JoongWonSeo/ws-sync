from pydantic import AliasGenerator, BaseModel, ConfigDict, PrivateAttr, TypeAdapter
from pydantic.alias_generators import to_camel
from pydantic.json_schema import GenerateJsonSchema

from .sync import Sync


class Synced:
    """
    A mixin class that provides a `sync` attribute in a way that is compatible with any pydantic BaseModel subclass.

    Making a class inherit from Synced means its fields are meant to be synced! Do not overload its usage for other serialization use cases unless it's guaranteed to be a 100% overlap with the synced use case.

    Example with BaseModel:
    ```python
    class SyncedUser(Synced, BaseModel):
        name: str
        contacts: dict[str, str]

        def model_post_init(self, context):
            # create the sync object
            self.sync = Sync.all(self, key="USER")

    u = SyncedUser(name="John", contacts={"email": "john@example.com", "phone": "+1234567890"})
    await u.sync()
    ```

    Example with custom BaseModel:
    ```python
    class MyBaseModel(BaseModel):
        # custom configuration
        pass

    class SyncedUser(Synced, MyBaseModel):
        name: str
        contacts: dict[str, str]

        def model_post_init(self, context):
            self.sync = Sync.all(self, key="USER")
    ```
    """

    model_config = ConfigDict(
        # make fields with default values required in the JSON schema when mode="serialization"
        json_schema_serialization_defaults_required=True,
    )

    _sync: Sync = PrivateAttr()

    @property
    def sync(self):
        return self._sync

    @sync.setter
    def sync(self, value: Sync):
        self._sync = value

    # ===== Class-level validator creation ===== #
    def __init_subclass__(cls, *, is_abstract: bool = False, **kwargs):
        """
        Initialize the subclass with the sync_key.

        Args:
            sync_key: The key to use for the sync object.
        """
        super().__init_subclass__(**kwargs)
        if not is_abstract:
            assert issubclass(cls, BaseModel), (
                f"{cls.__name__} must inherit from BaseModel"
            )

    @classmethod
    def generate_validators(cls):
        cls.field_validators = Sync.build_field_validators(cls)
        cls.action_validators = Sync.build_action_validators(cls)
        cls.task_validators = Sync.build_task_validators(cls)

    @classmethod
    def ws_sync_json_schema(
        cls,
        schema_generator: type[GenerateJsonSchema] = GenerateJsonSchema,
        ref_template: str = "#/$defs/{model}",
    ):
        """
        Returns a JSON schema suitable for ws_sync, meaning the model (all of its fields) as serialization, its action and task inputs as validation.
        """
        assert issubclass(cls, BaseModel), f"{cls.__name__} must inherit from BaseModel"
        cls.generate_validators()
        validation = list(cls.action_validators.items()) + list(
            cls.task_validators.items()
        )
        serialization = [("MODEL", TypeAdapter(cls))]
        schema_inputs: list = [
            (sync_key, "validation", validator) for sync_key, validator in validation
        ] + [
            (sync_key, "serialization", serializer)
            for sync_key, serializer in serialization
        ]
        schemas = TypeAdapter.json_schemas(
            schema_inputs, schema_generator=schema_generator, ref_template=ref_template
        )

        # # merge with model schema
        # model_schema = cls.model_json_schema()
        # model_schema["definitions"] = schemas
        return schemas


class SyncedAsCamelCase(Synced, is_abstract=True):
    """Synced base that serializes fields using camelCase."""

    model_config = Synced.model_config | ConfigDict(
        alias_generator=AliasGenerator(serialization_alias=to_camel),
        serialize_by_alias=True,
    )

    def __init_subclass__(cls, *, is_abstract: bool = False, **kwargs):
        super().__init_subclass__(is_abstract=is_abstract, **kwargs)
