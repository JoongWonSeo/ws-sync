from pydantic import BaseModel, PrivateAttr

from .sync import Sync


class SyncedModel(BaseModel):
    """
    A simple base class (or mixin) that provides a `sync` attribute in a way that is compatible with pydantic.

    Example:
    ```python
    class SyncedUser(SyncedModel):
        name: str
        contacts: dict[str, str]

        def model_post_init(self, context):
            # create the sync object
            self.sync = Sync(self, key="USER", sync_all=True, toCamelCase=True)

    u = SyncedUser(name="John", contacts={"email": "john@example.com", "phone": "+1234567890"})

    await u.sync()

    ```
    """

    _sync: Sync = PrivateAttr()

    @property
    def sync(self):
        return self._sync

    @sync.setter
    def sync(self, value: Sync):
        self._sync = value
