from pydantic import AliasGenerator, ConfigDict, PrivateAttr
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

    _sync: Sync = PrivateAttr()

    @property
    def sync(self):
        return self._sync

    @sync.setter
    def sync(self, value: Sync):
        self._sync = value


class SyncedAsCamelCase(Synced):
    """Synced base that serializes fields using camelCase."""

    model_config = ConfigDict(
        alias_generator=AliasGenerator(serialization_alias=to_camel),
        serialize_by_alias=True,
    )
