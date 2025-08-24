from __future__ import annotations

import argparse
import asyncio
from collections import deque
from time import time
from typing import Any

from rich.console import Console
from rich.json import JSON
from rich.live import Live
from rich.table import Table

from .sync import Sync


async def watch_sync(sync: Sync, history: int = 20) -> None:
    """Watch a :class:`Sync` object and display updates in real time."""

    console = Console()
    intervals: deque[float] = deque(maxlen=history)
    last = time()
    state: dict[str, Any] = {}
    event = asyncio.Event()

    async def on_snapshot(snapshot: dict[str, Any]) -> None:
        nonlocal last, state
        now = time()
        intervals.append(now - last)
        last = now
        state = snapshot
        event.set()

    sync.on_snapshot = on_snapshot

    def render() -> Table:
        table = Table(show_header=False)
        table.add_row("Δt", " ".join(f"{dt:.2f}s" for dt in intervals))
        table.add_row("State", JSON.from_data(state))
        return table

    with Live(render(), console=console, refresh_per_second=4) as live:
        while True:
            await event.wait()
            event.clear()
            live.update(render())


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug a Sync instance")
    parser.add_argument("path", help="Import path to Sync object, e.g. module:attr")
    args = parser.parse_args()

    module_name, attr = args.path.split(":")
    module = __import__(module_name, fromlist=[attr])
    sync = getattr(module, attr)
    if not isinstance(sync, Sync):
        raise SystemExit("Provided path is not a Sync instance")
    asyncio.run(watch_sync(sync))


if __name__ == "__main__":
    main()
