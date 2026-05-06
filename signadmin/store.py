from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import sqlite3
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from . import config


@dataclass(frozen=True)
class TargetDefaults:
    schedule_start: str = "00:20"
    schedule_end: str = "01:30"
    jitter_seconds: int = 120


DEFAULTS = TargetDefaults()
DEFAULT_APP_TITLE = "SignAdmin 多站签到中控台"


def _bool(value: Any) -> int:
    return 1 if bool(value) else 0


def connect() -> sqlite3.Connection:
    config.ensure_directories()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (key, value, config.now_iso()),
    )


def _get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    return str(row["value"] or "")


def init_db() -> None:
    schema = """
    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS members (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      remark TEXT NOT NULL DEFAULT '',
      enabled INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS targets (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
      site TEXT NOT NULL,
      display_name TEXT NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 1,
      schedule_enabled INTEGER NOT NULL DEFAULT 1,
      schedule_start TEXT NOT NULL DEFAULT '00:20',
      schedule_end TEXT NOT NULL DEFAULT '01:30',
      jitter_seconds INTEGER NOT NULL DEFAULT 120,
      notify_enabled INTEGER NOT NULL DEFAULT 1,
      config_json TEXT NOT NULL DEFAULT '{}',
      secret_json TEXT NOT NULL DEFAULT '',
      last_run_at TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS run_history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      target_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
      trigger_type TEXT NOT NULL,
      status TEXT NOT NULL,
      exit_code INTEGER NOT NULL,
      summary TEXT NOT NULL,
      log_path TEXT NOT NULL,
      started_at TEXT NOT NULL,
      finished_at TEXT NOT NULL
    );
    """
    with connect() as conn:
        conn.executescript(schema)
        app_title = _get_setting(conn, "app_title")
        if not app_title or app_title in {
            "签到管理台",
            "签到控制台",
            "MT / 哔哩哔哩 / 52破解 / 米游社 自动签到 Web 管理台",
        }:
            _set_setting(conn, "app_title", DEFAULT_APP_TITLE)
        if not _get_setting(conn, "wecom_webhook_url"):
            _set_setting(conn, "wecom_webhook_url", "")
        if conn.execute("SELECT 1 FROM settings WHERE key = 'admin_username'").fetchone() is None:
            _set_setting(conn, "admin_username", "")
        if conn.execute("SELECT 1 FROM settings WHERE key = 'admin_password_hash'").fetchone() is None:
            _set_setting(conn, "admin_password_hash", "")
        conn.commit()
    if config.INITIAL_ADMIN_PASSWORD_PATH.exists():
        config.INITIAL_ADMIN_PASSWORD_PATH.unlink()


def encrypt_secrets(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return config.get_fernet().encrypt(payload).decode("utf-8")


def decrypt_secrets(token: str) -> dict[str, Any]:
    if not token:
        return {}
    try:
        payload = config.get_fernet().decrypt(token.encode("utf-8"))
        value = json.loads(payload.decode("utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def admin_is_configured() -> bool:
    with connect() as conn:
        username = _get_setting(conn, "admin_username")
        stored = _get_setting(conn, "admin_password_hash")
    return bool(username.strip()) and bool(stored.strip())


def get_admin_username() -> str:
    with connect() as conn:
        return _get_setting(conn, "admin_username").strip()


def verify_admin_credentials(username: str, password: str) -> bool:
    with connect() as conn:
        stored_username = _get_setting(conn, "admin_username").strip()
        stored = _get_setting(conn, "admin_password_hash")
    if not stored_username or not stored:
        return False
    if username.strip() != stored_username:
        return False
    return bool(stored) and check_password_hash(stored, password)


def setup_admin(username: str, password: str) -> None:
    with connect() as conn:
        _set_setting(conn, "admin_username", username.strip())
        _set_setting(conn, "admin_password_hash", generate_password_hash(password))
        conn.commit()


def update_admin_account(username: str | None = None, password: str | None = None) -> None:
    with connect() as conn:
        if username is not None:
            _set_setting(conn, "admin_username", username.strip())
        if password:
            _set_setting(conn, "admin_password_hash", generate_password_hash(password))
        conn.commit()


def get_settings() -> dict[str, str]:
    with connect() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def update_settings(data: dict[str, str]) -> None:
    with connect() as conn:
        for key, value in data.items():
            _set_setting(conn, key, value)
        conn.commit()


def list_members() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT m.*,
                   COUNT(t.id) AS target_count
            FROM members m
            LEFT JOIN targets t ON t.member_id = m.id
            GROUP BY m.id
            ORDER BY m.enabled DESC, m.name COLLATE NOCASE, m.id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_member(member_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
    return dict(row) if row else None


def delete_member(member_id: int) -> bool:
    with connect() as conn:
        cursor = conn.execute("DELETE FROM members WHERE id = ?", (member_id,))
        conn.commit()
    return cursor.rowcount > 0


def save_member(member_id: int | None, *, name: str, remark: str, enabled: bool) -> int:
    now = config.now_iso()
    with connect() as conn:
        if member_id is None:
            cursor = conn.execute(
                """
                INSERT INTO members (name, remark, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name.strip(), remark.strip(), _bool(enabled), now, now),
            )
            conn.commit()
            return int(cursor.lastrowid)
        conn.execute(
            """
            UPDATE members
            SET name = ?, remark = ?, enabled = ?, updated_at = ?
            WHERE id = ?
            """,
            (name.strip(), remark.strip(), _bool(enabled), now, member_id),
        )
        conn.commit()
        return member_id


def _target_from_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["config"] = json.loads(data.pop("config_json") or "{}")
    data["secrets"] = decrypt_secrets(data.pop("secret_json") or "")
    data["enabled"] = bool(data["enabled"])
    data["schedule_enabled"] = bool(data["schedule_enabled"])
    data["notify_enabled"] = bool(data["notify_enabled"])
    return data


def list_targets(member_id: int | None = None) -> list[dict[str, Any]]:
    query = """
        SELECT t.*, m.name AS member_name
        FROM targets t
        JOIN members m ON m.id = t.member_id
    """
    params: list[Any] = []
    if member_id is not None:
        query += " WHERE t.member_id = ?"
        params.append(member_id)
    query += """
        ORDER BY t.enabled DESC,
                 CASE t.site
                   WHEN 'binmt' THEN 1
                   WHEN 'mihoyo' THEN 2
                   WHEN 'bilibili' THEN 3
                   WHEN '52pojie' THEN 4
                   ELSE 9
                 END,
                 m.name COLLATE NOCASE,
                 t.id
    """
    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_target_from_row(row) for row in rows]


def get_target(target_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT t.*, m.name AS member_name
            FROM targets t
            JOIN members m ON m.id = t.member_id
            WHERE t.id = ?
            """,
            (target_id,),
        ).fetchone()
    return _target_from_row(row) if row else None


def delete_target(target_id: int) -> bool:
    with connect() as conn:
        cursor = conn.execute("DELETE FROM targets WHERE id = ?", (target_id,))
        conn.commit()
    return cursor.rowcount > 0


def save_target(
    target_id: int | None,
    *,
    member_id: int,
    site: str,
    display_name: str,
    enabled: bool,
    schedule_enabled: bool,
    schedule_start: str,
    schedule_end: str,
    jitter_seconds: int,
    notify_enabled: bool,
    config_data: dict[str, Any],
    secrets_data: dict[str, Any],
) -> int:
    now = config.now_iso()
    config_json = json.dumps(config_data, ensure_ascii=False)
    secret_json = encrypt_secrets(secrets_data)
    with connect() as conn:
        if target_id is None:
            cursor = conn.execute(
                """
                INSERT INTO targets (
                    member_id, site, display_name, enabled, schedule_enabled,
                    schedule_start, schedule_end, jitter_seconds, notify_enabled,
                    config_json, secret_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    member_id,
                    site,
                    display_name.strip(),
                    _bool(enabled),
                    _bool(schedule_enabled),
                    schedule_start,
                    schedule_end,
                    int(jitter_seconds),
                    _bool(notify_enabled),
                    config_json,
                    secret_json,
                    now,
                    now,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)
        conn.execute(
            """
            UPDATE targets
            SET member_id = ?, site = ?, display_name = ?, enabled = ?, schedule_enabled = ?,
                schedule_start = ?, schedule_end = ?, jitter_seconds = ?, notify_enabled = ?,
                config_json = ?, secret_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                member_id,
                site,
                display_name.strip(),
                _bool(enabled),
                _bool(schedule_enabled),
                schedule_start,
                schedule_end,
                int(jitter_seconds),
                _bool(notify_enabled),
                config_json,
                secret_json,
                now,
                target_id,
            ),
        )
        conn.commit()
        return target_id


def list_recent_runs(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT r.*, t.site, t.display_name, m.name AS member_name
            FROM run_history r
            JOIN targets t ON t.id = r.target_id
            JOIN members m ON m.id = t.member_id
            ORDER BY r.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_run_log_paths_for_target(target_id: int) -> list[str]:
    with connect() as conn:
        rows = conn.execute("SELECT log_path FROM run_history WHERE target_id = ? ORDER BY id DESC", (target_id,)).fetchall()
    return [str(row["log_path"]) for row in rows if str(row["log_path"] or "").strip()]


def list_target_ids_for_member(member_id: int) -> list[int]:
    with connect() as conn:
        rows = conn.execute("SELECT id FROM targets WHERE member_id = ? ORDER BY id", (member_id,)).fetchall()
    return [int(row["id"]) for row in rows]


def list_runs_for_target_day(target_id: int, day_iso: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM run_history
            WHERE target_id = ?
              AND substr(started_at, 1, 10) = ?
            ORDER BY id DESC
            """,
            (target_id, day_iso),
        ).fetchall()
    return [dict(row) for row in rows]


def get_run(run_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT r.*, t.site, t.display_name, m.name AS member_name
            FROM run_history r
            JOIN targets t ON t.id = r.target_id
            JOIN members m ON m.id = t.member_id
            WHERE r.id = ?
            """,
            (run_id,),
        ).fetchone()
    return dict(row) if row else None


def create_run(
    *,
    target_id: int,
    trigger_type: str,
    status: str,
    exit_code: int,
    summary: str,
    log_path: str,
    started_at: str,
    finished_at: str,
    **_: Any,
) -> int:
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO run_history (
                target_id, trigger_type, status, exit_code, summary, log_path, started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (target_id, trigger_type, status, exit_code, summary, log_path, started_at, finished_at),
        )
        conn.execute(
            "UPDATE targets SET last_run_at = ?, updated_at = ? WHERE id = ?",
            (finished_at, finished_at, target_id),
        )
        conn.commit()
        return int(cursor.lastrowid)


def read_log(path_text: str) -> str:
    path = Path(path_text)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")
