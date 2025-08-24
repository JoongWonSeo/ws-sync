# `ws-sync`: WebSocket Sync

Minimal helpers for keeping Python objects and a browser in sync over a
WebSocket connection. State changes are shipped as JSON Patches and there is a
[companion React hook](https://github.com/JoongWonSeo/ws-sync-react).

## Patterns

### 1. Pydantic model (recommended)

```python
from pydantic import BaseModel
from ws_sync import remote_action, remote_task, sync_all
from ws_sync.synced_model import Synced


class Notes(Synced, BaseModel):
    title: str = "My Notes"
    notes: list[str] = []

    @sync_all("NOTES")
    def model_post_init(self, _):
        ...  # Sync is created here

    @remote_action("RENAME")
    async def rename(self, title: str):
        self.title = title
        await self.sync()

    @remote_task("ADD")
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

    @sync_all("NOTES")
    def __init__(self):
        self.title = "My Notes"
        self.notes = []

    @remote_action("RENAME")
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

    @remote_action("RESET")
    async def reset(self):
        self.value = 0
        await self.sync()

    @remote_task("INC")
    async def inc(self, by: int):
        self.value += by
        await self.sync()
```

`@remote_action` exposes a method for one-off calls. `@remote_task` spawns a
concurrent task that can be cancelled. All parameters are validated using the
type hints (Pydantic models, dataclasses, enums, etc.).

## Frontend

```jsx
const notes = useSynced("NOTES", { title: "", notes: [] });
```

The hook returns the state plus helper setters like `syncTitle`.

## Server

Example using FastAPI:

```python
from fastapi import FastAPI, WebSocket
from fastapi import FastAPI, WebSocket
from ws_sync import Session


app = FastAPI()

with Session() as session:
    notes = Notes()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await session.handle_connection(ws)
```

## Schemas

Pydantic models can export JSON Schema for their state, actions and tasks:

```python
Notes.ws_sync_json_schema()
```
