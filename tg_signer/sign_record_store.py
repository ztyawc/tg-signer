import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Optional


@dataclass
class SignRecordGroup:
    task_name: str
    user_id: Optional[str]
    records: list[tuple[str, str]]


@dataclass
class RecentSignRecord:
    task_name: str
    user_id: str
    sign_date: str
    signed_at: str
    account: Optional[str]
    source: str


@dataclass
class MigrationSummary:
    migrated_files: int = 0
    migrated_records: int = 0
    removed_files: int = 0
    skipped_files: list[Path] = field(default_factory=list)
    cleanup_failed_files: list[Path] = field(default_factory=list)


class SignRecordStore:
    DB_FILENAME = "data.sqlite3"
    SCHEMA_VERSION = 2

    def __init__(self, workdir: str | Path):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self) -> Path:
        return self.workdir / self.DB_FILENAME

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            self._ensure_schema(conn)
            with conn:
                yield conn
        finally:
            conn.close()

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        version = self._get_schema_version(conn)
        if version >= self.SCHEMA_VERSION:
            return

        # Keep schema management lightweight, but make migrations explicit so
        # future schema changes can be appended as v2/v3 steps instead of
        # rewriting the bootstrap logic.
        migrations = {
            1: self._migrate_to_v1,
            2: self._migrate_to_v2,
        }
        for target_version in range(version + 1, self.SCHEMA_VERSION + 1):
            migration = migrations.get(target_version)
            if migration is None:
                raise RuntimeError(f"Missing schema migration for v{target_version}")
            migration(conn)
            self._set_schema_version(conn, target_version)
        conn.commit()

    @staticmethod
    def _get_schema_version(conn: sqlite3.Connection) -> int:
        return conn.execute("PRAGMA user_version").fetchone()[0]

    @staticmethod
    def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
        conn.execute(f"PRAGMA user_version = {version}")

    @staticmethod
    def _migrate_to_v1(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sign_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_name TEXT NOT NULL,
                user_id TEXT NOT NULL,
                sign_date TEXT NOT NULL,
                signed_at TEXT NOT NULL,
                account TEXT,
                source TEXT NOT NULL DEFAULT 'runtime',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(task_name, user_id, sign_date)
            );

            CREATE INDEX IF NOT EXISTS idx_sign_records_task_user_date
            ON sign_records(task_name, user_id, sign_date);
            """
        )

    def _upsert_records(
        self,
        conn: sqlite3.Connection,
        task_name: str,
        user_id: str,
        items: Iterable[tuple[str, str]],
        *,
        account: str | None = None,
        source: str = "runtime",
    ) -> int:
        items = list(items)
        if any(
            not isinstance(day, str) or not isinstance(stamp, str)
            for day, stamp in items
        ):
            raise ValueError("签到记录的日期和时间戳必须是字符串")
        rows = [
            (
                task_name,
                user_id,
                sign_date,
                signed_at,
                account,
                source,
            )
            for sign_date, signed_at in items
        ]
        if not rows:
            return 0
        before = conn.total_changes
        conn.executemany(
            """
            INSERT INTO sign_records (
                task_name,
                user_id,
                sign_date,
                signed_at,
                account,
                source
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_name, user_id, sign_date) DO UPDATE SET
                signed_at = excluded.signed_at,
                account = excluded.account,
                source = excluded.source
            WHERE excluded.source != 'json_migrated'
            """,
            rows,
        )
        return conn.total_changes - before

    @staticmethod
    def _migrate_to_v2(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS task_runtime (
                task_name TEXT NOT NULL, user_id TEXT NOT NULL,
                account TEXT, config_hash TEXT NOT NULL,
                state TEXT NOT NULL, next_run_at TEXT,
                updated_at TEXT NOT NULL, pid INTEGER NOT NULL,
                PRIMARY KEY(task_name, user_id)
            );
            CREATE TABLE IF NOT EXISTS sign_runs (
                id TEXT PRIMARY KEY, task_name TEXT NOT NULL,
                user_id TEXT NOT NULL, account TEXT,
                run_key TEXT NOT NULL,
                scheduled_at TEXT NOT NULL, started_at TEXT NOT NULL,
                finished_at TEXT, status TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '[]',
                UNIQUE(task_name, user_id, run_key)
            );
            CREATE INDEX IF NOT EXISTS idx_sign_runs_task_started
            ON sign_runs(task_name, user_id, started_at DESC);
            """
        )

    def get_runtime(self, task_name: str, user_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM task_runtime WHERE task_name=? AND user_id=?",
                (task_name, user_id),
            ).fetchone()
        return dict(row) if row else None

    def list_runtime(self, task_name: str | None = None) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM task_runtime"
                + (" WHERE task_name=?" if task_name else ""),
                (task_name,) if task_name else (),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_runtime(
        self,
        task_name: str,
        user_id: str,
        *,
        account: str,
        config_hash: str,
        state: str,
        next_run_at: str | None,
        updated_at: str,
        pid: int,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO task_runtime VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_name, user_id) DO UPDATE SET
                    account=excluded.account, config_hash=excluded.config_hash,
                    state=excluded.state, next_run_at=excluded.next_run_at,
                    updated_at=excluded.updated_at, pid=excluded.pid""",
                (
                    task_name,
                    user_id,
                    account,
                    config_hash,
                    state,
                    next_run_at,
                    updated_at,
                    pid,
                ),
            )

    def start_run(
        self,
        task_name: str,
        user_id: str,
        *,
        account: str,
        scheduled_at: str,
        started_at: str,
        manual: bool = False,
    ) -> str | None:
        run_id = uuid.uuid4().hex
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO sign_runs
                (id, task_name, user_id, account, run_key, scheduled_at, started_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'running')
                ON CONFLICT(task_name, user_id, run_key) DO NOTHING""",
                (
                    run_id,
                    task_name,
                    user_id,
                    account,
                    run_id if manual else scheduled_at,
                    scheduled_at,
                    started_at,
                ),
            )
            return run_id if cursor.rowcount else None

    def update_run_details(self, run_id: str, details: list) -> None:
        payload = json.dumps(details, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute("UPDATE sign_runs SET details=? WHERE id=?", (payload, run_id))

    def finish_run(
        self, run_id: str, status: str, finished_at: str, details: list
    ) -> None:
        payload = json.dumps(details, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                "UPDATE sign_runs SET status=?, finished_at=?, details=? WHERE id=?",
                (status, finished_at, payload, run_id),
            )

    def interrupt_runs(self, task_name: str, user_id: str, finished_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE sign_runs SET status='interrupted', finished_at=?
                WHERE task_name=? AND user_id=? AND status='running'""",
                (finished_at, task_name, user_id),
            )

    def recent_runs(self, task_name: str | None = None, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sign_runs"
                + (" WHERE task_name=?" if task_name else "")
                + " ORDER BY started_at DESC LIMIT ?",
                (task_name, limit) if task_name else (limit,),
            ).fetchall()
        return [{**dict(row), "details": json.loads(row["details"])} for row in rows]

    def upsert_record(
        self,
        task_name: str,
        user_id: str,
        sign_date: str,
        signed_at: str,
        *,
        account: str | None = None,
        source: str = "runtime",
    ) -> None:
        with self._connect() as conn:
            self._upsert_records(
                conn,
                task_name,
                user_id,
                [(sign_date, signed_at)],
                account=account,
                source=source,
            )
            conn.commit()

    def has_records(self, task_name: str, user_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM sign_records
                WHERE task_name = ? AND user_id = ?
                LIMIT 1
                """,
                (task_name, user_id),
            ).fetchone()
        return row is not None

    def load_records(self, task_name: str, user_id: str) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT sign_date, signed_at
                FROM sign_records
                WHERE task_name = ? AND user_id = ?
                ORDER BY sign_date ASC
                """,
                (task_name, user_id),
            ).fetchall()
        return {row["sign_date"]: row["signed_at"] for row in rows}

    def list_record_groups(self) -> list[SignRecordGroup]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT task_name, user_id, sign_date, signed_at
                FROM sign_records
                ORDER BY task_name ASC, user_id ASC, sign_date DESC
                """
            ).fetchall()

        grouped: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for row in rows:
            key = (row["task_name"], row["user_id"])
            grouped.setdefault(key, []).append((row["sign_date"], row["signed_at"]))

        return [
            SignRecordGroup(task_name=task_name, user_id=user_id, records=records)
            for (task_name, user_id), records in grouped.items()
        ]

    def list_recent_records(
        self,
        limit: int = 10,
        *,
        task_name: str | None = None,
        user_id: str | None = None,
    ) -> list[RecentSignRecord]:
        query = [
            "SELECT task_name, user_id, sign_date, signed_at, account, source",
            "FROM sign_records",
        ]
        conditions = []
        params: list[object] = []
        if task_name:
            conditions.append("task_name = ?")
            params.append(task_name)
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if conditions:
            query.append("WHERE " + " AND ".join(conditions))
        query.append("ORDER BY signed_at DESC, task_name ASC, user_id ASC")
        query.append("LIMIT ?")
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute("\n".join(query), params).fetchall()

        return [
            RecentSignRecord(
                task_name=row["task_name"],
                user_id=row["user_id"],
                sign_date=row["sign_date"],
                signed_at=row["signed_at"],
                account=row["account"],
                source=row["source"],
            )
            for row in rows
        ]

    @staticmethod
    def load_json_records(path: str | Path) -> dict[str, str]:
        file_path = Path(path)
        if not file_path.is_file():
            return {}
        try:
            with open(file_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def import_json_file(
        self,
        task_name: str,
        user_id: str,
        path: str | Path,
        *,
        account: str | None = None,
        source: str = "json_migrated",
    ) -> int:
        records = self.load_json_records(path)
        if not records:
            return 0
        with self._connect() as conn:
            count = self._upsert_records(
                conn,
                task_name,
                user_id,
                records.items(),
                account=account,
                source=source,
            )
            conn.commit()
        return count

    def migrate_all_json_records(
        self,
        *,
        legacy_user_id: str | None = None,
        remove_files: bool = False,
        account: str | None = None,
    ) -> MigrationSummary:
        summary = MigrationSummary()
        signs_dir = self.workdir / "signs"
        if not signs_dir.is_dir():
            return summary

        pending_cleanup = []
        with self._connect() as conn:
            for path in sorted(signs_dir.rglob("sign_record.json")):
                resolved = self.resolve_record_target(
                    path, legacy_user_id=legacy_user_id
                )
                if resolved is None:
                    summary.skipped_files.append(path)
                    continue
                task_name, user_id = resolved
                try:
                    original = path.read_bytes()
                    records = json.loads(original)
                except (OSError, ValueError):
                    summary.skipped_files.append(path)
                    continue
                if not isinstance(records, dict):
                    summary.skipped_files.append(path)
                    continue
                if not records:
                    continue
                count = self._upsert_records(
                    conn,
                    task_name,
                    user_id,
                    records.items(),
                    account=account,
                    source="json_migrated",
                )
                summary.migrated_files += 1
                summary.migrated_records += count
                if remove_files:
                    pending_cleanup.append((path, original))
            conn.commit()
        # Files are only removed after every database write has committed.
        for path, original in pending_cleanup:
            try:
                if path.read_bytes() != original:
                    summary.cleanup_failed_files.append(path)
                    continue
                path.unlink()
                summary.removed_files += 1
            except OSError:
                summary.cleanup_failed_files.append(path)
        return summary

    def resolve_record_target(
        self,
        path: str | Path,
        *,
        legacy_user_id: str | None = None,
    ) -> tuple[str, str] | None:
        file_path = Path(path)
        signs_dir = self.workdir / "signs"
        relative_parts = file_path.relative_to(signs_dir).parts
        if len(relative_parts) >= 3:
            return relative_parts[0], relative_parts[1]
        if len(relative_parts) == 2:
            # Older layouts used signs/<task>/sign_record.json without a user_id
            # segment, so we need an explicit override or a single known user.
            user_id = legacy_user_id or self._infer_single_user_id()
            if user_id:
                return relative_parts[0], user_id
        return None

    def _infer_single_user_id(self) -> str | None:
        users_dir = self.workdir / "users"
        if not users_dir.is_dir():
            return None
        user_ids = sorted(path.name for path in users_dir.iterdir() if path.is_dir())
        if len(user_ids) == 1:
            return user_ids[0]
        return None
