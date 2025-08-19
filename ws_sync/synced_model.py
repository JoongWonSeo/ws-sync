from typing import ClassVar

from pydantic import AliasGenerator, ConfigDict, PrivateAttr, TypeAdapter
from pydantic.alias_generators import to_camel

from .sync import Sync


class Synced:
    """
    A mixin class that provides a `sync` attribute in a way that is compatible with any pydantic BaseModel subclass.

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

    field_validators: ClassVar[dict[str, TypeAdapter]] = {}
    """Maps the field names to the TypeAdapter validator for the field."""

    action_validators: ClassVar[dict[str, TypeAdapter]] = {}
    """Maps the remote_action keys to the TypeAdapter validator for the action handler."""

    task_validators: ClassVar[dict[str, TypeAdapter]] = {}
    """Maps the remote_task keys to the TypeAdapter validator for the task handler."""

    _sync: Sync = PrivateAttr()

    @property
    def sync(self):
        return self._sync

    @sync.setter
    def sync(self, value: Sync):
        self._sync = value

    # ===== Class-level validator creation ===== #
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # TODO: call the static builders for field_validators, action_validators, and task_validators


class SyncedAsCamelCase(Synced):
    """Synced base that serializes fields using camelCase."""

    model_config = Synced.model_config | ConfigDict(
        alias_generator=AliasGenerator(serialization_alias=to_camel),
        serialize_by_alias=True,
    )
