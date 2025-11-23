from pydantic import BaseModel, computed_field

from ws_sync import Session, Sync, SyncedAsCamelCase, remote_action, sync_all, sync_only

# We need to be able to count Sync instantiations.
# We can patch Sync.__init__ globally or inspect the result.


def test_sync_inheritance_double_init():
    # Monkey patch Sync.__init__ to track calls
    original_init = Sync.__init__
    call_log = []

    def new_init(self, *args, **kwargs):
        call_log.append((self, args, kwargs))
        original_init(self, *args, **kwargs)

    Sync.__init__ = new_init

    try:

        class Note(BaseModel):
            content: str

        class Notes(BaseModel):
            title: str
            entries: list[Note]

        @sync_only("Notes", title=..., num_entries=...)
        class SyncedNotes(SyncedAsCamelCase, Notes):
            @computed_field
            @property
            def num_entries(self) -> int:
                return len(self.entries)

        @sync_all("DebugNotes")
        class DebugNotes(SyncedNotes):
            @computed_field
            @property
            def num_entries(self) -> int:
                return sum(len(e.content) for e in self.entries)

            @remote_action
            async def debug_action(self, log: str):
                print(log)

        # Test case 1: Instantiating SyncedNotes (base)
        call_log.clear()
        with Session():
            n = SyncedNotes(title="test", entries=[Note(content="test")])  # noqa: F841

        assert len(call_log) == 1, "SyncedNotes should trigger exactly one Sync init"
        assert call_log[0][2]["key"] == "Notes"

        # Test case 2: Instantiating DebugNotes (child)
        call_log.clear()
        with Session():
            d = DebugNotes(title="test", entries=[Note(content="test")])  # noqa: F841

        assert len(call_log) == 1, (
            f"DebugNotes should trigger exactly one Sync init, but got {len(call_log)}"
        )
        assert call_log[0][2]["key"] == "DebugNotes"

    finally:
        Sync.__init__ = original_init


def test_undecorated_subclass_init():
    # Verify that an undecorated subclass still initializes Sync from the parent

    original_init = Sync.__init__
    call_log = []

    def new_init(self, *args, **kwargs):
        call_log.append((self, args, kwargs))
        original_init(self, *args, **kwargs)

    Sync.__init__ = new_init

    try:

        @sync_all("Base")
        class Base(SyncedAsCamelCase, BaseModel):
            x: int

        class Sub(Base):
            y: int

        call_log.clear()
        with Session():
            s = Sub(x=1, y=2)  # noqa: F841

        assert len(call_log) == 1
        assert call_log[0][2]["key"] == "Base"  # Or whatever key logic applies

    finally:
        Sync.__init__ = original_init
