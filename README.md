# `ws-sync`: WebSocket Sync

This library defines a very simple WebSocket and JSON & JSON Patch based protocol for keeping the python backend and the browser frontend in sync. There's a [corresponding react library](https://github.com/JoongWonSeo/ws-sync-react) that implements the frontend side of the protocol.

## Quickstart

### Syncing with Type Safety (Recommended)

The safest and most robust way to use ws-sync is with Pydantic models, which provide automatic validation, type coercion, and comprehensive serialization:

#### Backend

```python
from pydantic import BaseModel
from ws_sync import sync_all, remote_action

class User(BaseModel):
    name: str
    age: int
    email: str | None = None

class Notes(BaseModel):
    title: str = "My Notes"
    notes: list[str] = []

    @sync_all("NOTES")
    def model_post_init(self, __context):
        pass  # Sync is automatically set up

    @property
    def total_length(self):
        return sum(len(note) for note in self.notes)

    @remote_action("RENAME")
    async def rename(self, new_title: str):
        self.title = new_title
        await self.sync()

    @remote_action("ADD_NOTE")
    async def add_note(self, note: str):
        self.notes.append(note)
        await self.sync()
```

**Key Benefits:**

- **Type validation**: `new_title: str` ensures the frontend sends valid strings
- **Automatic coercion**: `age: int` converts string "25" to integer 25
- **Null safety**: `email: str | None` handles missing optional fields
- **Complex types**: Lists, dicts, nested models all work seamlessly

#### Type-Safe Collections

```python
class TeamManager:
    users: list[User]          # List of validated User models
    user_index: dict[str, User]  # Dict with validated User values

    @sync_all("TEAM")
    def __init__(self):
        self.users: list[User] = []
        self.user_index: dict[str, User] = {}

    @remote_action("ADD_USER")
    async def add_user(self, user_data: dict):
        # Automatic validation and conversion
        user = User(**user_data)
        self.users.append(user)
        self.user_index[user.name] = user
        await self.sync()
```

### Syncing Simple Objects (Basic Version)

For simple use cases without validation:

```python
from ws_sync import sync_all

class Notes:
    @sync_all("NOTES")
    def __init__(self):
        self.title = "My Notes"
        self.notes = []

    async def rename(self, new_title):
        self.title = new_title
        await self.sync()

    async def add(self, note):
        self.notes.append(note)
        await self.sync()
```

**Important**: The basic version only supports JSON-serializable types (str, int, float, bool, list, dict). No validation or type coercion is performed.

### Advanced Features

#### Computed Fields and Auto-Updates

```python
from pydantic import BaseModel, computed_field

class UserProfile(BaseModel):
    first_name: str
    last_name: str

    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @sync_all("PROFILE")
    def model_post_init(self, __context):
        pass
```

When `first_name` changes, `full_name` automatically updates in the frontend.

#### Actions and Tasks

```python
class TaskManager(BaseModel):
    tasks: list[Task] = []

    @sync_all("TASKS")
    def model_post_init(self, __context):
        pass

    @remote_action("CREATE_TASK")
    async def create_task(self, task_data: Task):
        # Validates task_data against Task model
        self.tasks.append(task_data)
        await self.sync()

    @remote_task("PROCESS_BATCH")
    async def process_batch(self, items: list[str]):
        for item in items:
            # Long-running, cancellable operation
            await asyncio.sleep(1)
            yield f"Processed {item}"
```

#### CamelCase Conversion

```python
from ws_sync.synced_model import SyncedAsCamelCase

class UserProfile(SyncedAsCamelCase, BaseModel):
    first_name: str  # becomes "firstName" in frontend
    last_name: str   # becomes "lastName" in frontend

    @sync_all("PROFILE")
    def model_post_init(self, __context):
        pass
```

#### Manual Attribute Selection

```python
@sync_only("NOTES",
    title = ...,           # sync as-is
    notes = ...,           # sync as-is
    total_length = "size", # sync as "size" in frontend
)
def __init__(self):
    self.title = "My Notes"
    self.notes = []
    self.private_data = "secret"  # not synced
```

### Frontend

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
        onChange={(e) => notes.rename(e.target.value)}
      />
      <button onClick={() => notes.addNote("New note")}>Add Note</button>
      <ul>
        {notes.notes.map((note, i) => (
          <li key={i}>{note}</li>
        ))}
      </ul>
    </div>
  );
};
```

### Server Setup

```python
from fastapi import FastAPI, WebSocket
from ws_sync import Session

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    session = Session()
    notes = Notes()  # Your synced object

    await session.new_connection(ws)
    await session.handle_connection()
```

## Key Features

### Type Safety & Validation (Pydantic)

- **Automatic validation**: All data from frontend is validated against your types
- **Type coercion**: Strings become integers, objects become models automatically
- **Complex types**: `List[User]`, `Dict[str, Task]`, nested models all supported
- **Computed fields**: Derived values update automatically when dependencies change

### Efficient Synchronization

- **JSON Patch**: Only changed data is sent over the network
- **Automatic detection**: Changes to any synced attribute trigger updates
- **Bidirectional**: Frontend changes update backend state with validation

### Real-time Features

- **Actions**: Call backend methods from frontend with type-safe parameters
- **Tasks**: Long-running, cancellable operations with progress updates
- **Reconnection**: Sessions persist across WebSocket disconnections

### Developer Experience

- **CamelCase conversion**: `snake_case` Python becomes `camelCase` JavaScript
- **Type hints**: Full IDE support with proper type checking
- **Flexible sync**: Sync all attributes or select specific ones

## Type Safety Comparison

**Pydantic Version (Recommended):**

```python
@remote_action("UPDATE_USER")
async def update_user(self, user: User, age: int):
    # ✅ user is validated User model
    # ✅ age is guaranteed to be int (coerced from string if needed)
    # ✅ Missing required fields raise validation errors
    # ✅ Complex nested objects work perfectly
```

**Basic Version (Limited):**

```python
@remote_action("UPDATE_USER")
async def update_user(self, user: dict, age):
    # ❌ user is raw dict, no validation
    # ❌ age might be string "25" instead of int 25
    # ❌ Missing fields silently ignored
    # ❌ Only JSON-serializable types supported
```

For production applications, the Pydantic version provides essential safety and reliability.

## Installation

```bash
pip install ws-sync
```

For more details, see the [React frontend library](https://github.com/JoongWonSeo/ws-sync-react).

## Concurrency and Blocking Semantics

This library is designed for safe async operation across multiple clients while preserving strict per-connection ordering. Key rules:

- **Async-first API**: All event handlers (init, actions, tasks) are expected to be `async` functions. If you supply a synchronous function, it will be executed via a threadpool to avoid blocking the event loop.
- **Per-connection ordering guarantee**: For a single `Session`, incoming websocket events are handled strictly in arrival order. The session waits for each handler to finish before the next event is handled. This guarantees deterministic ordering for a given connection.
- **Actions are sequential (non-concurrent)**: Methods exposed via `@remote_action` run to completion before the next event for the same session starts. Multiple actions will never run concurrently within the same websocket connection.
- **Tasks are concurrent and cancellable**: Methods exposed via `@remote_task` are scheduled as independent asyncio tasks and may run concurrently. They can be cancelled via a corresponding `@remote_task_cancel` handler. Task start/stop does not block further event handling for the same connection.
- **Non-blocking for sync handlers**: If an action or task factory is defined as a synchronous function (e.g., calling `time.sleep()` or other I/O-bound sync APIs), it is executed using `starlette.concurrency.run_in_threadpool` to avoid blocking the event loop and other connections.

Implications:

- Use `await asyncio.sleep(...)` inside async handlers whenever possible.
- If you must call sync, I/O-bound APIs, keep the handler sync, or wrap the calls in a suitable threadpool offload; `ws-sync` already offloads non-async handlers for you.
- Do not rely on concurrent execution of actions within the same session; use `@remote_task` for concurrent, long-running work.
