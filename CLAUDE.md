# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ws-sync is a Python library that implements a WebSocket-based synchronization protocol between Python backends and JavaScript frontends. It uses JSON Patch for efficient state synchronization, allowing real-time updates with minimal data transfer.

## Development Commands

### Build and Installation
```bash
# Install dependencies
poetry install

# Build the package
poetry build

# Install in development mode
poetry install --editable
```

### Testing
```bash
# Run all tests
poetry run pytest

# Run specific test file
poetry run pytest test_pydantic_sync.py

# Run tests with verbose output
poetry run pytest -v
```

### Code Quality and Formatting
```bash
# Run pre-commit hooks (linting, formatting, type checking)
pre-commit run --all-files

# Auto-fix formatting and linting issues
pre-commit run --all-files

# Install pre-commit hooks (run once after cloning)
pre-commit install
```

### Development Workflow
- Uses pytest for testing with pytest-asyncio for async test support
- Pydantic is included as a dev dependency for testing  
- The project uses Poetry for dependency management
- Pre-commit hooks are configured with:
  - **Ruff**: For linting and code formatting (replaces black + flake8)
  - **Pyright**: For static type checking
- **IMPORTANT**: Always run `pre-commit run --all-files` before committing to ensure code quality

### Typing Conventions
- Add type annotations where they provide clarity and aren't obvious to static analysis
- **Function returns**: Only annotate return types for functions with explicit `return` statements
- **No `-> None`**: Don't add `-> None` for functions without returns or with only bare `return`
- **Parameter types**: Always annotate parameters unless types are completely obvious from context
- **Complex types**: Use modern syntax (`dict[str, int]` not `Dict[str, int]`)
- **Forward references**: Use string quotes for forward references (`-> 'ClassName'`)

## Core Architecture

### Key Components

**Session Management** (`session.py`):
- `Session`: Core class managing WebSocket connections and event handling
- `SessionState`: ABC for user-defined session state objects
- `session_context`: ContextVar for per-task session access
- Handles connection lifecycle, event dispatching, and graceful reconnection

**Synchronization** (`sync.py`):
- `Sync`: Main synchronization class that manages object state and frontend communication
- Uses JSON Patch for efficient state updates
- Supports automatic attribute detection or manual specification
- Handles actions, tasks, and binary data transfer

**Decorators** (`decorators.py`):
- `@sync_all()`: Sync all non-private attributes
- `@sync_only()`: Sync only specified attributes
- `@remote_action()`: Expose methods as frontend-callable actions
- `@remote_task()`: Expose methods as long-running, cancellable tasks
- `@remote_task_cancel()`: Handle task cancellation

**Utilities** (`utils.py`):
- `nonblock_call()`: Async wrapper for sync/async functions
- `toCamelCase()`: Convert snake_case to camelCase
- `ensure_jsonable()`: Convert objects to JSON-serializable format

**User Identification** (`id.py`):
- `get_user_session()`: Protocol for identifying users across reconnections

### Protocol Design

The library implements a simple event-based protocol:
- All events follow `{"type": "event_type", "data": any}` format
- State synchronization uses JSON Patch for efficient updates
- Binary data supported through separate metadata/data messages
- Built-in support for actions, tasks, and toast notifications

### Key Features

1. **State Synchronization**: Automatic detection and syncing of object attributes
2. **Efficient Updates**: Uses JSON Patch to send only changed data
3. **Reconnection Handling**: Sessions persist across WebSocket disconnections
4. **Concurrent Tasks**: Support for long-running, cancellable operations
5. **Type-Safe Integration**: Full support for typed Python objects using Pydantic's TypeAdapter
   - Pydantic BaseModel support with validation
   - TypedDict support for structured dictionaries  
   - `List[Type]` and `Dict[str, Type]` support for any type
   - Automatic serialization/deserialization with type validation and coercion
   - Proper handling of nested structures and JSON Patch updates
6. **Camel Case Conversion**: Automatic snake_case to camelCase conversion

## Usage Patterns

### Basic Synchronization
```python
class MyObject:
    @sync_all("MY_KEY")
    def __init__(self):
        self.value = "initial"
    
    async def update_value(self, new_value):
        self.value = new_value
        await self.sync()
```

### Type-Safe Model Syncing
```python
from pydantic import BaseModel
from typing import List, Dict
from typing_extensions import TypedDict

class User(BaseModel):
    name: str
    age: int
    email: str = None

class UserStats(TypedDict):
    total_users: int
    active_users: int
    last_login: str

class UserManager:
    users: List[User]  # Class-level type annotation required
    user_index: Dict[str, User]
    stats: UserStats
    
    @sync_all("USER_MANAGER")
    def __init__(self):
        self.users: List[User] = []
        self.user_index: Dict[str, User] = {}
        self.stats: UserStats = {
            "total_users": 0,
            "active_users": 0, 
            "last_login": ""
        }
    
    async def add_user(self, user_data: dict):
        user = User(**user_data)  # Pydantic validation
        self.users.append(user)
        self.stats["total_users"] += 1
        await self.sync()  # Automatically serializes all typed structures
```

### Actions and Tasks
```python
@remote_action("DO_SOMETHING")
async def do_something(self, param):
    # Handle action
    await self.sync()

@remote_task("LONG_OPERATION")
async def long_operation(self):
    # Long-running task
    pass
```

### Server Integration
Typically used with FastAPI or similar async web frameworks:
```python
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await session.new_connection(ws)
    await session.handle_connection()
```

## Dependencies

- **starlette**: WebSocket handling (>= 0.37.2)
- **jsonpatch**: JSON Patch implementation (^1.33)
- **pydantic**: Type validation and serialization (^2.0)
- **python**: ^3.9

## Implementation Details

The library uses Pydantic's `TypeAdapter` for all type validation and conversion, which provides:
- Automatic type coercion (e.g., string "123" → int 123)
- Validation of complex nested structures
- Support for any Python type annotation including TypedDict, dataclasses, and custom types
- Consistent serialization/deserialization behavior

### Performance Optimizations

TypeAdapters are created once during object initialization and cached for the lifetime of the sync object. This means:
- **No runtime TypeAdapter creation** - validation is extremely fast
- **Zero reflection overhead** during state operations
- **Optimal memory usage** - adapters are reused across all sync operations
- **Static type analysis** - type hints are processed once at initialization

The implementation is much simpler than manual type checking while being more powerful and robust.