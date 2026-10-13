import os
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

pytest.importorskip("nicegui")

from tg_signer.cli.signer import tg_signer  # noqa: E402
from tg_signer.config import SendTextAction, SignChatV3, SignConfigV3  # noqa: E402
from tg_signer.sign_record_store import SignRecordStore  # noqa: E402
from tg_signer.storage import config_digest  # noqa: E402
from tg_signer.webui import auth, data  # noqa: E402
from tg_signer.webui.state import UIState  # noqa: E402


def test_login_attempts_are_limited_across_sessions_and_expire():
    clock = [0]
    limiter = auth.LoginLimiter(clock=lambda: clock[0])
    for _ in range(5):
        assert limiter.remaining("peer") == 0
        limiter.failed("peer")
    assert limiter.remaining("peer") == 300
    assert limiter.remaining("different-peer") == 0
    clock[0] = 300
    assert limiter.remaining("peer") == 0


def test_auth_session_has_expiry_and_is_invalid_after_code_change(monkeypatch):
    monkeypatch.setattr(auth.time, "time", lambda: 1000)
    session = auth.create_session("test-only-code")
    assert "test-only-code" not in str(session)
    assert auth.session_valid(session, "test-only-code")
    assert not auth.session_valid(session, "changed-code")
    assert not auth.session_valid("legacy-plaintext", "legacy-plaintext")
    monkeypatch.setattr(auth.time, "time", lambda: 1000 + auth.SESSION_SECONDS)
    assert not auth.session_valid(session, "test-only-code")


def test_expired_session_cannot_change_workdir(tmp_path):
    state = UIState({"webui_workdir": str(tmp_path)})
    state.authorized = lambda: False
    with pytest.raises(PermissionError):
        state.set_workdir(str(tmp_path / "other"))
    assert not (tmp_path / "other").exists()


def test_log_reader_rejects_files_outside_log_directory_and_symlinks(
    tmp_path, monkeypatch
):
    root = tmp_path / "logs"
    root.mkdir()
    allowed = root / "example.log"
    allowed.write_text("INFO synthetic entry")
    outside = tmp_path / "private.json"
    outside.write_text('{"value":"synthetic"}')
    (root / "linked.log").symlink_to(outside)
    monkeypatch.setattr(data, "LOG_DIR", root)
    assert data.load_logs(10, allowed)[1] == ["INFO synthetic entry"]
    for path in [outside, root / "linked.log", root / "other.json"]:
        with pytest.raises(ValueError):
            data.load_logs(10, path)


def test_gui_rejects_public_bind_without_access_code(tmp_path, monkeypatch):
    monkeypatch.delenv("TG_SIGNER_GUI_AUTHCODE", raising=False)
    result = CliRunner().invoke(
        tg_signer, ["--log-dir", str(tmp_path), "webgui", "--host", "0.0.0.0"]
    )
    assert result.exit_code == 2
    assert "访问码" in result.output


def test_gui_uses_cli_workdir_and_log_dir(tmp_path, monkeypatch):
    import tg_signer.webui as webui

    run = Mock()
    monkeypatch.setattr(webui, "main", run)
    monkeypatch.setenv("TG_SIGNER_WORKDIR", "before")
    monkeypatch.setenv("TG_SIGNER_LOG_DIR", "before")
    result = CliRunner().invoke(
        tg_signer,
        ["--workdir", str(tmp_path), "--log-dir", str(tmp_path / "logs"), "webgui"],
    )
    assert result.exit_code == 0, result.output
    assert os.environ["TG_SIGNER_WORKDIR"] == str(tmp_path)
    assert os.environ["TG_SIGNER_LOG_DIR"] == str(tmp_path / "logs")
    run.assert_called_once()


def test_activation_status_distinguishes_saved_and_applied_config(tmp_path):
    config = SignConfigV3(
        chats=[SignChatV3(chat_id=123, actions=[SendTextAction(text="demo")])],
        sign_at="0 6 * * *",
    )
    store = SignRecordStore(tmp_path)
    store.save_runtime(
        "demo",
        "1001",
        account="test",
        config_hash=config_digest(config.to_jsonable()),
        state="waiting",
        next_run_at="2026-10-14T06:00:00+08:00",
        updated_at=datetime.now(timezone.utc).isoformat(),
        pid=os.getpid(),
    )
    assert (
        data.config_activation_status("signer", "demo", config.to_jsonable(), tmp_path)
        == "已保存并生效"
    )
    changed = config.model_copy(update={"random_seconds": 60}).to_jsonable()
    assert "等待运行任务" in data.config_activation_status(
        "signer", "demo", changed, tmp_path
    )
