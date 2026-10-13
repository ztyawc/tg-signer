import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from pyrogram.dispatcher import Dispatcher
from pyrogram.handlers import MessageHandler

import tg_signer.core as core
from tg_signer.automation.handlers import register
from tg_signer.automation.models import Event, RuleStateStore
from tg_signer.config import (
    AutomationConfig,
    ClickKeyboardByTextAction,
    HandlerConfig,
    MatchConfig,
    RuleConfig,
    SendTextAction,
    SignChatV3,
    SignConfigV3,
    StartupTriggerConfig,
    TimerTriggerConfig,
)
from tg_signer.sign_record_store import SignRecordStore
from tg_signer.storage import atomic_write_json, task_path

NOW = datetime(2026, 10, 13, 6, tzinfo=timezone(timedelta(hours=8)))


def test_migration_failure_preserves_sources_and_rolls_back(tmp_path):
    store = SignRecordStore(tmp_path)
    files = []
    for name, stamp in [("a", NOW.isoformat()), ("b", {"invalid": "timestamp"})]:
        path = tmp_path / "signs" / name / "1001" / "sign_record.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"2026-10-13": stamp}))
        files.append(path)
    with pytest.raises(ValueError):
        store.migrate_all_json_records(remove_files=True)
    assert all(path.exists() for path in files)
    assert store.load_records("a", "1001") == {}


def test_migration_commit_failure_preserves_source(tmp_path, monkeypatch):
    store = SignRecordStore(tmp_path)
    store.list_record_groups()
    path = tmp_path / "signs" / "a" / "1001" / "sign_record.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"2026-10-13": NOW.isoformat()}))
    original = sqlite3.connect

    class FailingCommit(sqlite3.Connection):
        def commit(self):
            raise sqlite3.OperationalError("simulated commit failure")

    monkeypatch.setattr(
        sqlite3, "connect", lambda *a, **kw: original(*a, factory=FailingCommit, **kw)
    )
    with pytest.raises(sqlite3.OperationalError):
        store.migrate_all_json_records(remove_files=True)
    assert path.exists()
    assert store.load_records("a", "1001") == {}


def test_migration_does_not_overwrite_sqlite_and_can_clean_already_migrated_json(
    tmp_path,
):
    store = SignRecordStore(tmp_path)
    store.upsert_record("a", "1001", "2026-10-13", "2026-10-13T07:00:00+08:00")
    path = tmp_path / "signs" / "a" / "1001" / "sign_record.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"2026-10-13": NOW.isoformat()}))
    summary = store.migrate_all_json_records(remove_files=True)
    assert summary.migrated_records == 0
    assert summary.removed_files == 1
    assert store.load_records("a", "1001")["2026-10-13"] == "2026-10-13T07:00:00+08:00"


def test_migration_keeps_source_modified_during_import(tmp_path, monkeypatch):
    store = SignRecordStore(tmp_path)
    path = tmp_path / "signs" / "a" / "1001" / "sign_record.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"2026-10-13": NOW.isoformat()}))
    original = store._upsert_records

    def insert(*args, **kwargs):
        count = original(*args, **kwargs)
        path.write_text(json.dumps({"2026-10-14": NOW.isoformat()}))
        return count

    monkeypatch.setattr(store, "_upsert_records", insert)
    summary = store.migrate_all_json_records(remove_files=True)
    assert path.exists()
    assert summary.cleanup_failed_files == [path]
    assert "2026-10-13" in store.load_records("a", "1001")


def test_database_connection_is_closed_after_context(tmp_path):
    store = SignRecordStore(tmp_path)
    with store._connect() as connection:
        connection.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_atomic_state_write_keeps_previous_state_on_serialization_error(tmp_path):
    store = RuleStateStore(tmp_path / "state.json", logging.getLogger("test"))
    store.set_rule_vars("r", {"count": 1})
    store.save()
    original = store.path.read_bytes()
    store.set_rule_vars("r", {"bad": object()})
    with pytest.raises(TypeError):
        store.save()
    assert store.path.read_bytes() == original


def test_atomic_write_preserves_original_on_replace_failure(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    atomic_write_json(path, {"value": 1})
    original = path.read_bytes()

    def fail(*args):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("tg_signer.storage.os.replace", fail)
    with pytest.raises(OSError):
        atomic_write_json(path, {"value": 2})
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "name", ["../outside", "../../outside", "/tmp/outside", "a/b", "a\\b", "..", "a\n"]
)
def test_task_name_cannot_escape_directory(tmp_path, name):
    with pytest.raises(ValueError):
        task_path(tmp_path, name)


def test_task_directory_symlink_cannot_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        task_path(root, "linked")


@pytest.mark.parametrize(
    "changes",
    [{"random_seconds": -1}, {"sign_interval": -1}, {"sign_at": "invalid cron"}],
)
def test_invalid_schedule_is_rejected(changes):
    with pytest.raises(ValidationError):
        SignConfigV3(
            chats=[],
            sign_at="0 6 * * *",
            **{k: v for k, v in changes.items() if k != "sign_at"},
        ) if "sign_at" not in changes else SignConfigV3(chats=[], **changes)


@pytest.mark.parametrize(
    "params",
    [
        {"interval_seconds": -60},
        {"random_seconds": -1, "interval_seconds": 60},
        {"cron": "invalid"},
        {},
        {"cron": "0 6 * * *", "interval_seconds": 60},
    ],
)
def test_invalid_timer_is_rejected(params):
    with pytest.raises(ValidationError):
        TimerTriggerConfig(type="timer", params=params)


def test_v1_config_load_migrates_entire_compatibility_chain():
    loaded = SignConfigV3.load(
        {
            "chat_id": 123,
            "sign_text": "demo",
            "sign_at": "06:00:00",
            "random_seconds": 0,
        }
    )
    assert loaded is not None
    cfg, converted = loaded
    assert converted
    assert isinstance(cfg, SignConfigV3)
    assert cfg.chats[0].actions[0].text == "demo"


def test_unknown_sender_is_rejected_by_explicit_allowlist():
    msg = SimpleNamespace(from_user=None)
    assert not MatchConfig(chat_id=123, from_user_ids=[1001]).match_user(msg)
    assert MatchConfig(chat_id=123).match_user(msg)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_type", [RuntimeError, ConnectionError, asyncio.CancelledError]
)
async def test_client_start_failure_can_retry(monkeypatch, signer_factory, error_type):
    client = signer_factory().app
    starts = 0

    async def start(self):
        nonlocal starts
        starts += 1
        if starts == 1:
            raise error_type()
        self.is_initialized = True

    monkeypatch.setattr(core.Client, "start", start)
    monkeypatch.setattr(core.Client, "stop", AsyncMock())
    with pytest.raises(error_type):
        async with client:
            pass
    assert core._CLIENT_REFS[client.key] == 0
    async with client:
        assert core._CLIENT_REFS[client.key] == 1
    assert starts == 2


@pytest.mark.asyncio
async def test_client_connection_cycle_preserves_registered_handlers(
    signer_factory, monkeypatch
):
    client = signer_factory().app
    worker = signer_factory()
    handles = worker.register_handlers(MessageHandler(worker.on_message))
    await asyncio.sleep(0)
    assert client.dispatcher.groups

    async def terminate(*, clear_handlers=True):
        if clear_handlers:
            client.dispatcher.groups.clear()

    monkeypatch.setattr(client, "terminate", terminate)
    monkeypatch.setattr(client, "disconnect", AsyncMock())
    await client.stop()
    assert client.dispatcher.groups
    worker.unregister_handlers(handles)
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_action_timeout_releases_waiter(signer_factory):
    worker = signer_factory()
    chat = SignChatV3(chat_id=123, actions=[ClickKeyboardByTextAction(text="demo")])
    with pytest.raises(core.ActionTimeoutError):
        await worker.wait_for(chat, chat.actions[0], timeout=0)
    assert not worker.context.waiter
    assert worker.context.waiting_message is None


@pytest.mark.asyncio
async def test_shared_client_delivers_to_both_topic_tasks(signer_factory):
    workers = [
        signer_factory(task_name=name, loop=asyncio.get_running_loop())
        for name in ["one", "two"]
    ]
    handles = []
    for worker, topic in zip(workers, [10, 20], strict=True):
        chat = SignChatV3(chat_id=123, message_thread_id=topic, actions=[])
        worker.context.sign_chats[(123, topic)].append(chat)
        handles.append(worker.register_handlers(MessageHandler(worker.on_message)))
    await asyncio.sleep(0)
    message = core.Message(
        id=1,
        chat=core.Chat(id=123, type=core.ChatType.FORUM),
        from_user=core.User(id=100),
        text="demo",
        message_thread_id=20,
    )

    class Update:
        pass

    async def parse(*args):
        return message, MessageHandler

    dispatcher: Dispatcher = workers[0].app.dispatcher
    dispatcher.update_parsers = {Update: parse}
    await dispatcher.updates_queue.put((Update(), {}, {}))
    await dispatcher.updates_queue.put(None)
    await dispatcher.handler_worker(asyncio.Lock())
    assert not workers[0].context.chat_messages
    assert workers[1].context.chat_messages[(123, 20)][1] is message
    for worker, tokens in zip(workers, handles, strict=True):
        worker.unregister_handlers(tokens)
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_failed_round_does_not_write_success_record(signer_factory):
    worker = signer_factory()
    worker.user = SimpleNamespace(id=1001)
    worker.sign_a_chat = AsyncMock(
        side_effect=core.errors.RPCError("simulated failure")
    )
    cfg = SignConfigV3(
        chats=[SignChatV3(chat_id=123, actions=[SendTextAction(text="demo")])],
        sign_at="0 6 * * *",
        sign_interval=0,
    )
    await worker._execute_sign_round(cfg, {}, NOW, NOW)
    assert worker.sign_record_store.load_records(worker.task_name, "1001") == {}
    assert (
        worker.sign_record_store.recent_runs(worker.task_name)[0]["status"] == "failed"
    )


@pytest.mark.asyncio
async def test_concurrent_rule_events_preserve_both_updates(tmp_path):
    from tests.test_automation_engine import make_worker

    worker = make_worker(tmp_path)

    async def increment(event, ctx, params):
        count = ctx.vars.get("count", 0)
        await asyncio.sleep(0)
        ctx.vars["count"] = count + 1
        return "continue"

    register("test_increment", increment)
    rule = RuleConfig(
        id="r", triggers=[], handlers=[HandlerConfig(handler="test_increment")]
    )
    event = Event(
        type="message", chat_id=123, message=None, now=NOW, trigger_id="t", rule_id="r"
    )
    await asyncio.gather(worker._run_rule(rule, event), worker._run_rule(rule, event))
    assert worker.state.get_rule_vars("r")["count"] == 2


class StopSchedule(BaseException):
    pass


class ScheduledApp:
    key = "scheduled-test-client"

    def __init__(self):
        self.handles = []

    def add_handler(self, handler, group=0):
        self.handles.append((handler, group))

    def remove_handler(self, handler, group=0):
        self.handles.remove((handler, group))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,expected", [("scheduled", [11]), ("immediate", [0, 11])])
async def test_scheduler_respects_deadline_without_adding_execution_time(
    signer_factory, monkeypatch, mode, expected
):
    worker = signer_factory()
    worker.user = SimpleNamespace(id=1001)
    app = ScheduledApp()
    worker.app = app
    clock, executions = [NOW], []
    worker.write_config(
        SignConfigV3(
            chats=[SignChatV3(chat_id=123, actions=[SendTextAction(text="demo")])],
            sign_at="* * * * * *",
            random_seconds=10,
            sign_interval=0,
        )
    )

    async def sign(chat):
        executions.append(int((clock[0] - NOW).total_seconds()))
        if len(executions) == len(expected):
            raise StopSchedule()
        clock[0] += timedelta(seconds=2)

    async def sleep(seconds):
        clock[0] += timedelta(seconds=seconds)

    worker.sign_a_chat = sign
    monkeypatch.setattr(core, "get_now", lambda: clock[0])
    monkeypatch.setattr(core.random, "randint", lambda *args: 10)
    monkeypatch.setattr(core.asyncio, "sleep", sleep)
    with pytest.raises(StopSchedule):
        await worker.normal_run(start_mode=mode)
    assert executions == expected
    assert app.handles == []


@pytest.mark.asyncio
async def test_scheduler_restores_persisted_random_deadline(
    signer_factory, monkeypatch
):
    from tg_signer.storage import config_digest

    worker = signer_factory()
    worker.user = SimpleNamespace(id=1001)
    worker.app = ScheduledApp()
    config = SignConfigV3(
        chats=[SignChatV3(chat_id=123, actions=[SendTextAction(text="demo")])],
        sign_at="* * * * * *",
        random_seconds=10,
        sign_interval=0,
    )
    worker.write_config(config)
    planned = NOW + timedelta(seconds=7)
    worker.sign_record_store.save_runtime(
        worker.task_name,
        "1001",
        account="test",
        config_hash=config_digest(config.to_jsonable()),
        state="stopped",
        next_run_at=planned.isoformat(),
        updated_at=NOW.isoformat(),
        pid=0,
    )
    clock = [NOW]

    async def sleep(seconds):
        clock[0] += timedelta(seconds=seconds)

    async def sign(chat):
        assert clock[0] == planned
        raise StopSchedule()

    worker.sign_a_chat = sign
    monkeypatch.setattr(core, "get_now", lambda: clock[0])
    monkeypatch.setattr(core.asyncio, "sleep", sleep)
    with pytest.raises(StopSchedule):
        await worker.normal_run()


@pytest.mark.asyncio
async def test_scheduler_reloads_saved_config_without_restarting(
    signer_factory, monkeypatch
):
    worker = signer_factory()
    worker.user = SimpleNamespace(id=1001)
    worker.app = ScheduledApp()
    original = SignConfigV3(
        chats=[SignChatV3(chat_id=123, actions=[SendTextAction(text="before")])],
        sign_at="* * * * * *",
        random_seconds=10,
        sign_interval=0,
    )
    worker.write_config(original)
    clock, sleeps, ceilings = [NOW], [], []

    def random(lower, upper):
        ceilings.append(upper)
        return upper

    async def sleep(seconds):
        clock[0] += timedelta(seconds=seconds)
        sleeps.append(seconds)
        if len(sleeps) == 1:
            worker.write_config(original.model_copy(update={"random_seconds": 1}))

    async def sign(chat):
        assert worker.config.random_seconds == 1
        assert clock[0] == NOW + timedelta(seconds=7)
        raise StopSchedule()

    worker.sign_a_chat = sign
    monkeypatch.setattr(core, "get_now", lambda: clock[0])
    monkeypatch.setattr(core.random, "randint", random)
    monkeypatch.setattr(core.asyncio, "sleep", sleep)
    with pytest.raises(StopSchedule):
        await worker.normal_run()
    assert ceilings[0:2] == [10, 1]


@pytest.mark.asyncio
async def test_startup_action_waits_for_client_initialization(tmp_path, monkeypatch):
    import tg_signer.automation.engine as engine
    from tests.test_automation_engine import make_worker

    worker = make_worker(tmp_path)
    ready = []

    class ConnectingApp(ScheduledApp):
        initialized = False

        async def __aenter__(self):
            await asyncio.sleep(0)
            self.initialized = True
            return self

        async def send_message(self, *args, **kwargs):
            ready.append(self.initialized)
            return SimpleNamespace(id=1)

    worker.app = ConnectingApp()
    worker.user = SimpleNamespace(id=1001)
    worker.config = AutomationConfig(
        rules=[
            RuleConfig(
                id="startup",
                triggers=[
                    StartupTriggerConfig(type="startup", params={"chat_id": 123})
                ],
                handlers=[HandlerConfig(handler="send_text", params={"text": "demo"})],
            )
        ]
    )
    monkeypatch.setattr(worker, "load_config", lambda *args: worker.config)

    async def idle():
        while not ready:
            await asyncio.sleep(0)

    monkeypatch.setattr(engine, "idle", idle)
    await worker.run()
    assert ready == [True]
    assert not worker._background_tasks
    assert not worker.app.handles


@pytest.mark.asyncio
async def test_slow_timer_does_not_block_other_due_rule(tmp_path, monkeypatch):
    import tg_signer.automation.engine as engine
    from tests.test_automation_engine import make_worker

    worker = make_worker(tmp_path)
    release, fast = asyncio.Event(), asyncio.Event()

    async def slow(event, ctx, params):
        await release.wait()
        return "continue"

    async def quick(event, ctx, params):
        fast.set()
        return "continue"

    register("test_slow_timer", slow)
    register("test_fast_timer", quick)
    rules = []
    for name, handler in [("slow", "test_slow_timer"), ("quick", "test_fast_timer")]:
        rules.append(
            RuleConfig(
                id=name,
                triggers=[
                    TimerTriggerConfig(
                        type="timer", id="tick", params={"interval_seconds": 60}
                    )
                ],
                handlers=[HandlerConfig(handler=handler)],
            )
        )
        worker.state.set_trigger_next_run(name, "tick", NOW)
    worker.config = AutomationConfig(rules=rules)
    monkeypatch.setattr(engine, "get_now", lambda: NOW)
    task = asyncio.create_task(worker.timer_loop())
    try:
        await asyncio.wait_for(fast.wait(), timeout=1)
        assert not release.is_set()
    finally:
        release.set()
        task.cancel()
        pending = list(worker._background_tasks)
        for child in pending:
            child.cancel()
        await asyncio.gather(task, *pending, return_exceptions=True)


@pytest.mark.asyncio
async def test_callback_failure_is_not_silently_accepted(signer_factory):
    worker = signer_factory()
    worker._call_telegram_api = AsyncMock(side_effect=core.errors.BadRequest("demo"))
    with pytest.raises(core.errors.BadRequest):
        await worker.request_callback_answer(worker.app, 123, 1, "demo")


@pytest.mark.asyncio
async def test_scheduler_retries_connection_before_any_actions(
    signer_factory, monkeypatch
):
    worker = signer_factory()
    worker.user = SimpleNamespace(id=1001)
    clock, entries, executions = [NOW], [], []

    class FailingApp(ScheduledApp):
        async def __aenter__(self):
            entries.append(clock[0])
            if len(entries) == 1:
                raise OSError("simulated connection failure")
            return self

    worker.app = FailingApp()
    worker.write_config(
        SignConfigV3(
            chats=[SignChatV3(chat_id=123, actions=[SendTextAction(text="demo")])],
            sign_at="* * * * * *",
            sign_interval=0,
        )
    )

    async def sleep(seconds):
        clock[0] += timedelta(seconds=seconds)

    async def sign(chat):
        executions.append(clock[0])
        raise StopSchedule()

    worker.sign_a_chat = sign
    monkeypatch.setattr(core, "get_now", lambda: clock[0])
    monkeypatch.setattr(core.asyncio, "sleep", sleep)
    with pytest.raises(StopSchedule):
        await worker.normal_run()
    assert entries == [NOW + timedelta(seconds=1), NOW + timedelta(seconds=31)]
    assert executions == [NOW + timedelta(seconds=31)]
