import json
from datetime import date

import pytest

pytest.importorskip("nicegui")

from tg_signer.sign_record_store import SignRecordStore  # noqa: E402
from tg_signer.webui.data import (  # noqa: E402
    SignRecord,
    load_dashboard,
    record_rows,
)


def test_dashboard_keeps_configs_intact_and_tolerates_broken_task(tmp_path):
    task = tmp_path / "signs" / "daily" / "config.json"
    task.parent.mkdir(parents=True)
    payload = {
        "chats": [{"chat_id": "@demo", "actions": [{"action": 1, "text": "hi"}]}],
        "sign_at": "0 6 * * *",
    }
    task.write_text(json.dumps(payload))
    original = task.read_bytes()
    broken = tmp_path / "signs" / "broken" / "config.json"
    broken.parent.mkdir()
    broken.write_text("not valid json")
    store = SignRecordStore(tmp_path)
    for day in ["2026-10-01", "2026-10-02", "2026-10-13", "2026-10-14"]:
        store.upsert_record("daily", "1001", day, f"{day}T06:00:00+08:00")

    data = load_dashboard(tmp_path, today=date(2026, 10, 14))

    assert task.read_bytes() == original
    assert {item.name: item.valid for item in data.tasks} == {
        "broken": False,
        "daily": True,
    }
    assert len(data.records) == 4
    assert len(data.activity) == 14
    assert data.activity[0] == ("2026-10-01", 1)
    assert data.activity[-1] == ("2026-10-14", 1)
    assert sum(count for _, count in data.activity) == 4


def test_record_rows_can_display_legacy_timestamps(tmp_path):
    records = [
        SignRecord(
            task="daily",
            user_id=None,
            records=[
                ("2026-10-13", "2026-10-13T06:00:12+08:00"),
                ("2026-10-12", "legacy time"),
            ],
            path=tmp_path / "sign_record.json",
        )
    ]

    rows = record_rows(records)

    assert rows[0]["time"] == "06:00:12"
    assert rows[1]["time"] == "legacy time"
    assert rows[0]["user"] == "默认账号"
