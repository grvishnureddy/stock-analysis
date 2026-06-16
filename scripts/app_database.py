#!/usr/bin/env python3
"""SQLite persistence for StockScope users, sessions, job runs, and verification audits."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATABASE = DATA_DIR / "stockscope.db"
INITIAL_PASSWORD_FILE = DATA_DIR / "initial-admin-password.txt"
PBKDF2_ITERATIONS = 310_000


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def initialize_database(admin_user: str = "admin", admin_password: str | None = None) -> str | None:
    DATA_DIR.mkdir(exist_ok=True)
    with closing(connect()) as db, db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                remote_address TEXT
            );
            CREATE TABLE IF NOT EXISTS job_runs (
                id INTEGER PRIMARY KEY,
                job_name TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                exit_code INTEGER,
                output TEXT
            );
            CREATE TABLE IF NOT EXISTS result_verifications (
                id INTEGER PRIMARY KEY,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                result_date TEXT NOT NULL,
                quarter TEXT,
                status TEXT NOT NULL,
                verification_level TEXT NOT NULL,
                source TEXT,
                source_reference TEXT,
                verified_at TEXT,
                payload_json TEXT,
                UNIQUE(exchange, symbol, result_date)
            );
            """
        )
        existing = db.execute("SELECT id FROM users LIMIT 1").fetchone()
        if existing:
            return None
        generated = admin_password or secrets.token_urlsafe(15)
        db.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, 'admin', ?)",
            (admin_user, hash_password(generated), datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    if not admin_password:
        INITIAL_PASSWORD_FILE.write_text(
            f"StockScope initial administrator\nUsername: {admin_user}\nPassword: {generated}\nDelete this file after signing in.\n",
            encoding="utf-8",
        )
    return generated


def authenticate(username: str, password: str) -> dict | None:
    with closing(connect()) as db:
        user = db.execute("SELECT * FROM users WHERE username = ? AND active = 1", (username.strip(),)).fetchone()
    if not user or not verify_password(password, user["password_hash"]):
        return None
    return {"id": user["id"], "username": user["username"], "role": user["role"]}


def create_session(user_id: int, remote_address: str, hours: int = 12) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with closing(connect()) as db, db:
        db.execute("DELETE FROM sessions WHERE expires_at < ?", (now.isoformat(timespec="seconds"),))
        db.execute(
            "INSERT INTO sessions(token_hash, user_id, created_at, expires_at, remote_address) VALUES (?, ?, ?, ?, ?)",
            (hashlib.sha256(token.encode()).hexdigest(), user_id, now.isoformat(timespec="seconds"), (now + timedelta(hours=hours)).isoformat(timespec="seconds"), remote_address),
        )
    return token


def session_user(token: str | None) -> dict | None:
    if not token:
        return None
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(connect()) as db:
        row = db.execute(
            """SELECT users.id, users.username, users.role FROM sessions
               JOIN users ON users.id = sessions.user_id
               WHERE sessions.token_hash = ? AND sessions.expires_at > ? AND users.active = 1""",
            (hashlib.sha256(token.encode()).hexdigest(), now),
        ).fetchone()
    return dict(row) if row else None


def delete_session(token: str | None) -> None:
    if not token:
        return
    with closing(connect()) as db, db:
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (hashlib.sha256(token.encode()).hexdigest(),))


def change_password(user_id: int, current_password: str, new_password: str) -> tuple[bool, str]:
    if len(new_password) < 12:
        return False, "New password must contain at least 12 characters"
    with closing(connect()) as db, db:
        user = db.execute("SELECT password_hash FROM users WHERE id = ? AND active = 1", (user_id,)).fetchone()
        if not user or not verify_password(current_password, user["password_hash"]):
            return False, "Current password is incorrect"
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new_password), user_id))
    INITIAL_PASSWORD_FILE.unlink(missing_ok=True)
    return True, "Password updated"


def record_job_run(name: str, state: dict) -> None:
    with closing(connect()) as db, db:
        db.execute(
            "INSERT INTO job_runs(job_name, status, started_at, finished_at, exit_code, output) VALUES (?, ?, ?, ?, ?, ?)",
            (name, state.get("status"), state.get("startedAt"), state.get("finishedAt"), state.get("exitCode"), state.get("output", "")[-12000:]),
        )


def import_result_verifications(path: Path) -> int:
    if not path.exists():
        return 0
    rows = json.loads(path.read_text(encoding="utf-8"))
    with closing(connect()) as db, db:
        for row in rows:
            db.execute(
                """INSERT INTO result_verifications(exchange, symbol, result_date, quarter, status, verification_level, source, source_reference, verified_at, payload_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(exchange, symbol, result_date) DO UPDATE SET
                   quarter=excluded.quarter, status=excluded.status, verification_level=excluded.verification_level,
                   source=excluded.source, source_reference=excluded.source_reference, verified_at=excluded.verified_at,
                   payload_json=excluded.payload_json""",
                (
                    row.get("exchange"), row.get("symbol"), row.get("date"), row.get("quarter"), row.get("status"),
                    row.get("verificationLevel", "unverified"), row.get("source"), row.get("sourceReference"),
                    row.get("verifiedAt"), json.dumps(row, ensure_ascii=True),
                ),
            )
    return len(rows)


def verification_summary() -> dict:
    with closing(connect()) as db:
        levels = {row["verification_level"]: row["count"] for row in db.execute("SELECT verification_level, COUNT(*) count FROM result_verifications GROUP BY verification_level")}
        jobs = [dict(row) for row in db.execute("SELECT job_name, status, finished_at FROM job_runs ORDER BY id DESC LIMIT 8")]
    return {"levels": levels, "recentJobs": jobs}
