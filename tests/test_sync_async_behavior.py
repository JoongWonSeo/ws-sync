import asyncio
from time import perf_counter
from typing import Any, cast

import pytest

from ws_sync import Session, Sync, remote_action, remote_task, sync_all
from ws_sync.sync import action_event, task_start_event

from .utils import Duration, FakeWebSocket


class TestSyncVsAsyncDecorators:
    @pytest.mark.asyncio
    async def test_remote_action_allows_sync_and_async_when_blocking_false(
        self, mock_session
    ):
        class Counter:
            sync: Sync

            @sync_all("COUNTER")
            def __init__(self):
                self.value = 0

            @remote_action("INC")
            def inc(self, amount: int = 1):
                self.value += amount

            @remote_action("AINC")
            async def ainc(self, amount: int = 1):
                self.value += amount

        c = Counter()

        # Sync action
        await c.sync.actions({"type": "INC", "amount": 2})
        assert c.value == 2

        # Async action
        await c.sync.actions({"type": "AINC", "amount": 3})
        assert c.value == 5

    @pytest.mark.asyncio
    async def test_remote_task_allows_sync_and_async_when_blocking_false(
        self, mock_session
    ):
        class Runner:
            sync: Sync

            @sync_all("RUNNER")
            def __init__(self):
                self.progress = 0

            @remote_task("WORK")
            def work(self, amount: int = 1):
                self.progress += amount

            @remote_task("AWORK")
            async def awork(self, amount: int = 1):
                self.progress += amount

        r = Runner()

        # Sync task
        await r.sync.tasks({"type": "WORK", "amount": 2})
        task = r.sync.running_tasks["WORK"]
        await task
        assert r.progress == 2

        # Async task
        await r.sync.tasks({"type": "AWORK", "amount": 3})
        task2 = r.sync.running_tasks["AWORK"]
        await task2
        assert r.progress == 5


class TestBlockingAndOrdering:
    @pytest.mark.asyncio
    async def test_actions_execute_sequentially_per_session(self):
        a1_duration = Duration(0.05)
        a2_duration = Duration(0.01)

        class Ordered:
            sync: Sync

            @sync_all("ORD")
            def __init__(self):
                self.a1_start: float | None = None
                self.a1_end: float | None = None
                self.a2_start: float | None = None
                self.a2_end: float | None = None

            @remote_action("A1")
            async def a1(self):
                self.a1_start = perf_counter()
                await asyncio.sleep(a1_duration.seconds)
                self.a1_end = perf_counter()

            @remote_action("A2")
            async def a2(self):
                self.a2_start = perf_counter()
                await asyncio.sleep(a2_duration.seconds)
                self.a2_end = perf_counter()

        session = Session()
        with session:
            obj = Ordered()

        ws = FakeWebSocket()
        task = asyncio.create_task(session.handle_connection(cast(Any, ws)))
        await asyncio.sleep(0)
        ws.send_from_client({"type": action_event("ORD"), "data": {"type": "A1"}})
        ws.send_from_client({"type": action_event("ORD"), "data": {"type": "A2"}})
        ws.client_disconnect()
        await task

        assert obj.a1_start is not None and obj.a1_end is not None
        assert obj.a2_start is not None and obj.a2_end is not None
        # Ordering: A2 starts only after A1 ends
        assert obj.a1_end <= obj.a2_start
        # Durations roughly match
        assert a1_duration.roughly_equal(obj.a1_end - obj.a1_start)
        assert a2_duration.roughly_equal(obj.a2_end - obj.a2_start)

    @pytest.mark.asyncio
    async def test_sync_handlers_run_in_threadpool_nonblocking_across_sessions(self):
        block_duration = Duration(0.2)

        # One session runs a sync action that sleeps; another should proceed unblocked
        class ServiceA:
            sync: Sync

            @sync_all("A")
            def __init__(self):
                self.block_start: float | None = None
                self.block_end: float | None = None

            @remote_action("BLOCK")
            def block(self):
                t0 = perf_counter()
                self.block_start = t0
                # Intentional synchronous sleep to exercise threadpool offload
                import time as _time

                _time.sleep(block_duration.seconds)
                self.block_end = perf_counter()

        class ServiceB:
            sync: Sync

            @sync_all("B")
            def __init__(self):
                self.ping_time: float | None = None

            @remote_action("PING")
            async def ping(self):
                self.ping_time = perf_counter()

        s1 = Session()
        s2 = Session()
        with s1:
            a = ServiceA()
        with s2:
            b = ServiceB()

        ws1 = FakeWebSocket()
        ws2 = FakeWebSocket()

        # Run both sessions concurrently and interleave
        tsk1 = asyncio.create_task(s1.handle_connection(cast(Any, ws1)))
        tsk2 = asyncio.create_task(s2.handle_connection(cast(Any, ws2)))
        await asyncio.sleep(0)
        ws1.send_from_client({"type": action_event("A"), "data": {"type": "BLOCK"}})
        await asyncio.sleep(0.01)
        ws2.send_from_client({"type": action_event("B"), "data": {"type": "PING"}})
        ws1.client_disconnect()
        ws2.client_disconnect()
        await asyncio.gather(tsk1, tsk2)

        assert a.block_start is not None and a.block_end is not None
        assert b.ping_time is not None
        # PING should occur before the sync BLOCK completes
        assert b.ping_time < a.block_end  # type: ignore[operator]

    @pytest.mark.asyncio
    async def test_remote_tasks_run_concurrently_and_overlap(self):
        t_duration = Duration(0.15)

        class Runner:
            sync: Sync

            @sync_all("RUN")
            def __init__(self):
                self.starts: dict[str, float] = {}
                self.ends: dict[str, float] = {}

            @remote_task("T1")
            async def t1(self):
                self.starts["T1"] = perf_counter()
                await asyncio.sleep(t_duration.seconds)
                self.ends["T1"] = perf_counter()

            @remote_task("T2")
            async def t2(self):
                self.starts["T2"] = perf_counter()
                await asyncio.sleep(t_duration.seconds)
                self.ends["T2"] = perf_counter()

        session = Session()
        with session:
            r = Runner()

        ws = FakeWebSocket()

        # Start connection processing and interleave task starts
        conn_task = asyncio.create_task(session.handle_connection(cast(Any, ws)))
        await asyncio.sleep(0)
        ws.send_from_client({"type": task_start_event("RUN"), "data": {"type": "T1"}})
        await asyncio.sleep(0.005)
        ws.send_from_client({"type": task_start_event("RUN"), "data": {"type": "T2"}})
        await asyncio.sleep(0.02)

        # Both tasks should be present (running concurrently)
        assert set(r.sync.running_tasks.keys()) == {"T1", "T2"}
        t1 = r.sync.running_tasks["T1"]
        t2 = r.sync.running_tasks["T2"]

        # Wait for both tasks to complete, then disconnect and finish
        await asyncio.gather(t1, t2)
        ws.client_disconnect()
        await conn_task

        # Ends recorded and both overlapped (each starts before the other ends)
        assert r.starts["T1"] < r.ends["T2"]
        assert r.starts["T2"] < r.ends["T1"]
        # Durations ~0.15s
        assert t_duration.roughly_equal(r.ends["T1"] - r.starts["T1"])
        assert t_duration.roughly_equal(r.ends["T2"] - r.starts["T2"])

    @pytest.mark.asyncio
    async def test_combined_actions_sequential_tasks_concurrent_via_session(self):
        a1_first = Duration(0.02)
        a1_second = Duration(0.01)
        a1_duration = Duration(a1_first.seconds + a1_second.seconds)
        a2_duration = Duration(0.01)
        long_first = Duration(0.1)
        long_second = Duration(0.1)

        class Combo:
            sync: Sync

            @sync_all("CMB")
            def __init__(self):
                self.task_running = False
                self.long_start: float | None = None
                self.long_end: float | None = None
                self.a1_start: float | None = None
                self.a1_mid: float | None = None
                self.a1_end: float | None = None
                self.a2_start: float | None = None
                self.a2_end: float | None = None

            @remote_task("LONG")
            async def long(self):
                self.task_running = True
                self.long_start = perf_counter()
                await asyncio.sleep(long_first.seconds)
                await asyncio.sleep(long_second.seconds)
                self.long_end = perf_counter()
                self.task_running = False

            @remote_action("A1")
            async def a1(self):
                self.a1_start = perf_counter()
                await asyncio.sleep(a1_first.seconds)
                self.a1_mid = perf_counter()
                await asyncio.sleep(a1_second.seconds)
                self.a1_end = perf_counter()

            @remote_action("A2")
            async def a2(self):
                self.a2_start = perf_counter()
                await asyncio.sleep(a2_duration.seconds)
                self.a2_end = perf_counter()

        session = Session()
        with session:
            c = Combo()

        ws = FakeWebSocket()
        task = asyncio.create_task(session.handle_connection(cast(Any, ws)))
        await asyncio.sleep(0)
        ws.send_from_client({"type": task_start_event("CMB"), "data": {"type": "LONG"}})
        # Let LONG register and capture the task to await later
        await asyncio.sleep(0.005)
        long_task = c.sync.running_tasks.get("LONG")
        ws.send_from_client({"type": action_event("CMB"), "data": {"type": "A1"}})
        await asyncio.sleep(0.005)
        ws.send_from_client({"type": action_event("CMB"), "data": {"type": "A2"}})
        ws.client_disconnect()
        await task
        # Ensure LONG finishes before asserting timings
        if long_task is not None:
            await long_task

        assert c.long_start and c.long_end
        assert c.a1_start and c.a1_mid and c.a1_end and c.a2_start and c.a2_end
        # Task overlaps with A1 around mid
        assert c.long_start <= c.a1_mid <= c.long_end
        # A2 must start after A1 ends (sequential actions)
        assert c.a1_end <= c.a2_start
        # Duration checks
        assert a1_duration.roughly_equal(c.a1_end - c.a1_start)
        assert a2_duration.roughly_equal(c.a2_end - c.a2_start)


class TestMultipleObjectsAndSessions:
    @pytest.mark.asyncio
    async def test_multiple_synced_objects_actions_sequential_tasks_concurrent(self):
        aa_duration = Duration(0.03)
        at_duration = Duration(0.05)
        ba_duration = Duration(0.02)
        bt_duration = Duration(0.05)

        class ObjA:
            sync: Sync

            @sync_all("A")
            def __init__(self):
                self.aa_start: float | None = None
                self.aa_end: float | None = None

            @remote_action("AA")
            async def aa(self):
                self.aa_start = perf_counter()
                await asyncio.sleep(aa_duration.seconds)
                self.aa_end = perf_counter()

            @remote_task("AT")
            async def at(self):
                self.at_start = perf_counter()
                await asyncio.sleep(at_duration.seconds)
                self.at_end = perf_counter()

        class ObjB:
            sync: Sync

            @sync_all("B")
            def __init__(self):
                self.ba_start: float | None = None
                self.ba_end: float | None = None

            @remote_action("BA")
            async def ba(self):
                self.ba_start = perf_counter()
                await asyncio.sleep(ba_duration.seconds)
                self.ba_end = perf_counter()

            @remote_task("BT")
            async def bt(self):
                self.bt_start = perf_counter()
                await asyncio.sleep(bt_duration.seconds)
                self.bt_end = perf_counter()

        session = Session()
        with session:
            a = ObjA()
            b = ObjB()

        # Same session; interleave events for A and B dynamically
        ws = FakeWebSocket(auto_disconnect=False)

        # Run connection; tasks will run concurrently after creation
        conn_task = asyncio.create_task(session.handle_connection(cast(Any, ws)))
        await asyncio.sleep(0)
        ws.send_from_client({"type": action_event("A"), "data": {"type": "AA"}})
        ws.send_from_client({"type": action_event("B"), "data": {"type": "BA"}})
        # Wait until the two actions finish
        for _ in range(80):
            if a.aa_end is not None and b.ba_end is not None:
                break
            await asyncio.sleep(0.005)

        # After first two actions, both should be completed sequentially in order
        assert a.aa_start is not None and a.aa_end is not None
        assert b.ba_start is not None and b.ba_end is not None
        assert a.aa_end <= b.ba_start  # A.AA then B.BA in same session order
        assert aa_duration.roughly_equal(a.aa_end - a.aa_start)
        assert ba_duration.roughly_equal(b.ba_end - b.ba_start)

        # Start tasks interleaved; then wait for registration
        ws.send_from_client({"type": task_start_event("A"), "data": {"type": "AT"}})
        ws.send_from_client({"type": task_start_event("B"), "data": {"type": "BT"}})
        for _ in range(20):
            if set(a.sync.running_tasks.keys()) == {"AT"} and set(
                b.sync.running_tasks.keys()
            ) == {"BT"}:
                break
            await asyncio.sleep(0.005)

        # Wait for completion and disconnect
        await asyncio.gather(
            *a.sync.running_tasks.values(), *b.sync.running_tasks.values()
        )
        ws.client_disconnect()
        await conn_task
        # Concurrency: tasks overlap
        assert a.at_start < b.bt_end and b.bt_start < a.at_end

    @pytest.mark.asyncio
    async def test_cross_session_independence_for_sync_and_async_handlers(self):
        async_a_duration = Duration(0.05)
        async_c_duration = Duration(0.01)

        class Svc1:
            sync: Sync

            @sync_all("S1")
            def __init__(self):
                self.stamps: list[float] = []

            @remote_action("ASYNCA")
            async def async_a(self):
                self.stamps.append(perf_counter())
                await asyncio.sleep(async_a_duration.seconds)

            @remote_action("SYNCB")
            def sync_b(self):
                self.stamps.append(perf_counter())

        class Svc2:
            sync: Sync

            @sync_all("S2")
            def __init__(self):
                self.stamps: list[float] = []

            @remote_action("ASYNCC")
            async def async_c(self):
                self.stamps.append(perf_counter())
                await asyncio.sleep(async_c_duration.seconds)

            @remote_action("SYNCD")
            def sync_d(self):
                self.stamps.append(perf_counter())

        s1 = Session()
        s2 = Session()
        with s1:
            x = Svc1()
        with s2:
            y = Svc2()

        ws1 = FakeWebSocket()
        ws2 = FakeWebSocket()

        t0 = perf_counter()
        tsk1 = asyncio.create_task(s1.handle_connection(cast(Any, ws1)))
        tsk2 = asyncio.create_task(s2.handle_connection(cast(Any, ws2)))
        await asyncio.sleep(0)
        ws1.send_from_client({"type": action_event("S1"), "data": {"type": "ASYNCA"}})
        ws2.send_from_client({"type": action_event("S2"), "data": {"type": "ASYNCC"}})
        ws1.send_from_client({"type": action_event("S1"), "data": {"type": "SYNCB"}})
        ws2.send_from_client({"type": action_event("S2"), "data": {"type": "SYNCD"}})
        ws1.client_disconnect()
        ws2.client_disconnect()
        await asyncio.gather(tsk1, tsk2)
        t1 = perf_counter()

        # Total runtime should be close to max of the longest chain (~0.05 sec), not sum
        assert (t1 - t0) < 0.12
        assert len(x.stamps) == 2 and len(y.stamps) == 2

    @pytest.mark.asyncio
    async def test_async_handler_with_time_sleep_blocks_other_sessions(self):
        bad_block_duration = Duration(0.2)

        class BadSvc:
            sync: Sync

            @sync_all("BAD")
            def __init__(self):
                self.done = False

            @remote_action("BADBLOCK")
            async def badblock(self):
                # Mistakenly blocking inside async handler
                import time as _time

                _time.sleep(bad_block_duration.seconds)  # noqa: ASYNC251
                self.done = True

        class QuickSvc:
            sync: Sync

            @sync_all("QK")
            def __init__(self):
                self.t: float | None = None

            @remote_action("PING")
            async def ping(self):
                self.t = perf_counter()

        slow_sess = Session()
        fast_sess = Session()
        with slow_sess:
            bad = BadSvc()
        with fast_sess:
            quick = QuickSvc()

        ws_slow = FakeWebSocket()
        ws_fast = FakeWebSocket()

        t0 = perf_counter()
        slow_task = asyncio.create_task(slow_sess.handle_connection(cast(Any, ws_slow)))
        fast_task = asyncio.create_task(fast_sess.handle_connection(cast(Any, ws_fast)))
        await asyncio.sleep(0)
        ws_slow.send_from_client(
            {"type": action_event("BAD"), "data": {"type": "BADBLOCK"}}
        )
        await asyncio.sleep(0.01)
        ws_fast.send_from_client({"type": action_event("QK"), "data": {"type": "PING"}})
        ws_slow.client_disconnect()
        ws_fast.client_disconnect()
        await asyncio.gather(slow_task, fast_task)
        t1 = perf_counter()

        # Because the async handler blocked the event loop, the quick session should be delayed significantly
        # If event loop blocked ~0.2s, total should exceed ~0.18s comfortably
        assert (t1 - t0) > 0.18
        assert bad.done is True
        assert quick.t is not None
