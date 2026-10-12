from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

from tg_signer.webui.data import DEFAULT_LOG_FILE, DEFAULT_WORKDIR, get_workdir


class UIState:
    """View preferences belonging to one browser session."""

    def __init__(self, storage: MutableMapping[str, Any]):
        self.storage = storage
        self.workdir = get_workdir(storage.get("webui_workdir", DEFAULT_WORKDIR))
        self.log_path = Path(storage.get("webui_log_path", DEFAULT_LOG_FILE))
        self.log_limit = 200
        self.record_filter = ""

    def set_workdir(self, path: str) -> None:
        self.workdir = get_workdir(Path(path).expanduser())
        self.storage["webui_workdir"] = str(self.workdir)

    def set_log_path(self, path: str) -> None:
        self.log_path = Path(path).expanduser()
        self.storage["webui_log_path"] = str(self.log_path)
