# `ws-sync`: WebSocket Sync

Minimal helpers for keeping Python objects and a browser in sync over a
WebSocket connection. State changes are shipped as JSON Patches and there is a
[companion React hook](https://github.com/JoongWonSeo/ws-sync-react).

## Patterns

### 1. Pydantic model (recommended)

```python
from pydantic import BaseModel, Field
from ws_sync import remote_action, remote_task, sync_all, Synced


class Notes(Synced, BaseModel):
    title: str = Field("My Notes", min_length=3, max_length=50)
    notes: list[str] = []

    @sync_all()
    def model_post_init(self, _):
        ...  # Sync is created here

    @remote_action
    async def rename(self, title: str = Field(min_length=3, max_length=50)):
        self.title = title
        await self.sync()

    @remote_task
    async def add(self, note: str):
        self.notes.append(note)
        await self.sync()
```

`Synced` is a thin mixin over `BaseModel`; it honours Pydantic configs and
validates both the fields and any remote actions/tasks.

### 2. Classic class with annotations

```python
from ws_sync import remote_action, sync_all
from ws_sync.sync import Sync


class Notes:
    sync: Sync  # type checking & validation via TypeAdapter
    title: str
    notes: list[str]

    @sync_all()
    def __init__(self):
        self.title = "My Notes"
        self.notes = []

    @remote_action
    async def rename(self, title: str):
        self.title = title
        await self.sync()
```

### 3. Manual sync without validation

```python
from ws_sync.sync import Sync


class Notes:
    def __init__(self):
        self.title = "My Notes"
        self.notes = []
        self.sync = Sync.all(self, "NOTES")
```

Attributes are sent as-is with no type validation.

## Remote actions & tasks

```python
class Counter(Synced, BaseModel):
    value: int = 0

    @remote_action
    async def reset(self):
        self.value = 0
        await self.sync()

    @remote_task
    async def inc(self, by: int):
        self.value += by
        await self.sync()
```

`@remote_action` exposes a method for one-off calls. `@remote_task` spawns a
concurrent task that can be cancelled. All parameters are validated using the
type hints (Pydantic models, dataclasses, enums, etc.).

## Frontend

The second parameter of `useSynced` is the initial state.

The returned `notes` object not only contains the state, but also the setters and syncers:

```jsx
const Notes = () => {
  const notes = useSynced("NOTES", {
    title: "",
    notes: [],
  });

  return (
    <div>
      <input
        value={notes.title}
        onChange={(e) => notes.syncTitle(e.target.value)}
      />
      <ul>
        {notes.notes.map((note) => (
          <li>{note}</li>
        ))}
      </ul>
    </div>
  );
};
```

## Server

Example using FastAPI:

```python
from fastapi import FastAPI, WebSocket
from ws_sync import Session
from .notes import Notes

# FastAPI server
app = FastAPI()


# create a new session, in this case only 1 global session
with Session() as session:
    my_notes = Notes()
    my_session = session

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await my_session.handle_connection(ws)
```

## Concepts and Implementation

### High-Level

**Session**: A session is a connection between a frontend and a backend, and it _persists across WebSocket reconnects_. This means that any interruption of the connection will not affect the backend state in any way, and all the `self.sync()` calls will be ignored. On reconnect, the frontend will automatically restore the latest state from the backend.

**Sync**: A sync operation will generate a new snapshot of the object state, calculate the difference to the previous state snapshot, and send a JSON Patch object to the frontend. The frontend will then apply the patch to its local state. This is done automatically on every `self.sync()` call. This way, only the changes are sent over the network, and the frontend state is always in sync with the backend state.

### Low-Level

**Events**: The primitive of the protocol are events. An event is a JSON object with a simple `{"type": "event_type", "data": any}` format. All the operations done by the `Sync` object uses different events, including actions and tasks.

## Validators and Schema Generation

### Static

If you use the `Synced` object with pydantic `BaseModel`s, you can get JSON schemas for the synced state, registered actions and tasks. This can then be used to generate frontend client types and codes.

```python
class Notes(Synced, BaseModel):
    title: str = Field(min_length=3, max_length=50)
    content: dict[str, list[str]] = {}

    @remote_action
    async def set_title(self, title: str):
        self.title = title
        await self.sync()

Notes.ws_sync_json_schema()
```
