from pydantic import PrivateAttr

from .sync import Sync


class HasSync:
    """
    A mixin class that provides a `sync` attribute in a way that is compatible with any pydantic BaseModel subclass.

    Example with BaseModel:
    ```python
    class SyncedUser(HasSync, BaseModel):
        name: str
        contacts: dict[str, str]

        def model_post_init(self, context):
            # create the sync object
            self.sync = Sync(self, key="USER", sync_all=True, toCamelCase=True)

    u = SyncedUser(name="John", contacts={"email": "john@example.com", "phone": "+1234567890"})
    await u.sync()
    ```

    Example with custom BaseModel:
    ```python
    class MyBaseModel(BaseModel):
        # custom configuration
        pass

    class SyncedUser(HasSync, MyBaseModel):
        name: str
        contacts: dict[str, str]

        def model_post_init(self, context):
            self.sync = Sync(self, key="USER", sync_all=True, toCamelCase=True)
    ```
    """

    _sync: Sync = PrivateAttr()

    @property
    def sync(self):
        return self._sync

    @sync.setter
    def sync(self, value: Sync):
        self._sync = value
