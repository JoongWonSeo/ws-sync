from pydantic import AliasGenerator, ConfigDict, PrivateAttr
from pydantic.alias_generators import to_camel

from .sync import Sync


class Synced:
    """Mixin providing a ``sync`` attribute compatible with Pydantic models."""

    model_config = ConfigDict()

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
