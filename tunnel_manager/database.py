from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    project_dir TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS services (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    workdir TEXT NOT NULL,
                    executable TEXT NOT NULL,
                    args_json TEXT NOT NULL DEFAULT '[]',
                    port INTEGER NOT NULL,
                    hostname TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def get_profiles(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM profiles ORDER BY name COLLATE NOCASE").fetchall()
            return [dict(row) for row in rows]

    def save_profile(self, name: str, project_dir: str, profile_id: str | None = None) -> str:
        profile_id = profile_id or str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO profiles(id, name, project_dir) VALUES(?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, project_dir=excluded.project_dir",
                (profile_id, name.strip(), project_dir.strip()),
            )
        return profile_id

    def delete_profile(self, profile_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM profiles WHERE id=?", (profile_id,))

    def get_services(self, profile_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if profile_id:
                rows = conn.execute(
                    "SELECT s.*, p.name AS profile_name FROM services s "
                    "JOIN profiles p ON p.id=s.profile_id WHERE s.profile_id=? "
                    "ORDER BY s.name COLLATE NOCASE",
                    (profile_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT s.*, p.name AS profile_name FROM services s "
                    "JOIN profiles p ON p.id=s.profile_id ORDER BY p.name, s.name"
                ).fetchall()
            result = [dict(row) for row in rows]
            for item in result:
                try:
                    item["args"] = json.loads(item.pop("args_json"))
                except (json.JSONDecodeError, TypeError):
                    item["args"] = []
            return result

    def save_service(
        self,
        profile_id: str,
        name: str,
        workdir: str,
        executable: str,
        args: list[str],
        port: int,
        hostname: str,
        service_id: str | None = None,
    ) -> str:
        service_id = service_id or str(uuid.uuid4())
        args_json = json.dumps(args, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO services(id, profile_id, name, workdir, executable, args_json, port, hostname) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET profile_id=excluded.profile_id, name=excluded.name, "
                "workdir=excluded.workdir, executable=excluded.executable, args_json=excluded.args_json, "
                "port=excluded.port, hostname=excluded.hostname",
                (service_id, profile_id, name.strip(), workdir.strip(), executable.strip(), args_json, port, hostname.strip().lower()),
            )
        return service_id

    def delete_service(self, service_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM services WHERE id=?", (service_id,))

    def get_setting(self, key: str, default: str = "") -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return str(row["value"]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get_all_settings(self) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            return {str(row["key"]): str(row["value"]) for row in rows}
