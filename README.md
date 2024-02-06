# `ws-sync`: WebSocket Sync

This library defines a very simple WebSocket and JSON & JSON Patch based protocol for keeping the python backend and the browser frontend in sync. There's a [corresponding react library](https://github.com/JoongWonSeo/ws-sync-react) that implements the frontend side of the protocol.

## Quickstart

### Syncing simple states
#### Backend
Let's say you have the following object:
```python
class Notes:
    def __init__(self):
        # my attributes, as usual
        self.title = "My Notes"
        self.notes = []
    
    @property
    def total_length(self):
        return sum(len(note) for note in self.notes)
    
    def rename(self, new_title):
        self.title = new_title
    
    def add(self, note):
        self.notes.append(note)
```

To sync it to the frontend, it is as simple as:

```diff
+from ws_sync import Sync

class Notes:
    def __init__(self):
        # my attributes, as usual
        self.title = "My Notes"
        self.notes = []

+       # create the sync object and define the key of the object
+       self.sync = Sync("NOTES", self)
    
    @property
    def total_length(self):
        return sum(len(note) for note in self.notes)
    
+   async def rename(self, new_title):
        self.title = new_title
+       await self.sync() # make sure the frontend knows about the change
    
+   async def add(self, note):
        self.notes.append(note)
+       await self.sync() # make sure the frontend knows about the change
```

The `Sync("Notes", self)` call automatically detects the attributes to sync in `self`, which are all attributes or `@properties` that do not start with an underscore. You can also specify the attributes to sync manually:

```python
self.sync = Sync("NOTES", self,
    title = ...,
    notes = ...,
    total_length = "totalLength",
)
```

The keyword argument is the local name of the attribute, the value is the name of the attribute in the frontend. If the value is `...`, the local and frontend name are the same. This is useful if you want to rename an attribute in the frontend without changing the name in the backend (e.g. snake_case to camelCase).

#### Frontend
On the frontend, you can use the `useSync` hook to sync the state to the backend:

```jsx
const Notes = () => {
    const notes = useSync("NOTES", {
        title: "",
        notes: [],
    })

    return (
        <div>
            <h1>{notes.title}</h1>
            <ul>{notes.notes.map(note => <li>{note}</li>)}</ul>
        </div>
    )
}
```

The second parameter of `useSync` is the initial state.

The returned `notes` object not only contains the state, but also the setters and syncers:

```jsx
const Notes = () => {
    const notes = useSync("NOTES", {
        title: "",
        notes: [],
    })

    return (
        <div>
            <input value={notes.title} onChange={e => notes.syncTitle(e.target.value)} />
            <ul>{notes.notes.map(note => <li>{note}</li>)}</ul>
        </div>
    )
}
```

### Actions
Actions are a way to call methods on the remote (action handlers), usually frontend -> backend.

`TODO`

### Tasks
Tasks are like actions, but for long-running operations and can be cancelled.

`TODO`

### Server
Of course, to actually connect the frontend and backend, you need a server. Here's an example using FastAPI:

```python
from fastapi import FastAPI
from ws_sync import Session
from .notes import Notes

# create a new session, in this case only 1 global session
with Session() as session:
    my_notes = Notes()
    my_session = session

# FastAPI server
app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    try:
        await my_session.new_connection(ws)
        await my_session.handle_connection()
    finally:
        my_session.ws = None
        await ws.close()
```


## Concepts and Implementation

### High-Level
**Session**: A session is a connection between a frontend and a backend, and it *persists across WebSocket reconnects*. This means that any interruption of the connection will not affect the backend state in any way, and all the `self.sync()` calls will be ignored. On reconnect, the frontend will automatically restore the latest state from the backend.

**Sync**: A sync operation will generate a new snapshot of the object state, calculate the difference to the previous state snapshot, and send a JSON Patch object to the frontend. The frontend will then apply the patch to its local state. This is done automatically on every `self.sync()` call. This way, only the changes are sent over the network, and the frontend state is always in sync with the backend state.

### Low-Level
**Events**: The primitive of the protocol are events. An event is a JSON object with a simple `{"type": "event_type", "data": any}` format. All the operations done by the `Sync` object uses different events, including actions and tasks.
