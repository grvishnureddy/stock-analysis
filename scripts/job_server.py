#!/usr/bin/env python3
"""Serve StockScope and expose an allowlisted job API with optional remote access."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import re
from http.cookies import SimpleCookie
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import update_results as nse
import update_company_news as company_news
import update_company_fundamentals as company_fundamentals
import app_database as database
JOBS = {
    "results": ROOT / "scripts" / "update_results.py",
    "news": ROOT / "scripts" / "update_news.py",
    "financials": ROOT / "scripts" / "update_financials.py",
    "market-news": ROOT / "scripts" / "update_market_news.py",
    "stock-analysis": ROOT / "scripts" / "update_stock_analysis.py",
    "practice-prices": ROOT / "scripts" / "update_practice_prices.py",
    "watch-predictions": ROOT / "scripts" / "update_watch_predictions.py",
    "market-overview": ROOT / "scripts" / "update_market_overview.py",
}
STATUS_FILES = {
    "results": ROOT / "data" / "update-status.json",
    "news": ROOT / "data" / "news-update-status.json",
    "financials": ROOT / "data" / "financials-update-status.json",
    "market-news": ROOT / "data" / "market-news-update-status.json",
    "stock-analysis": ROOT / "data" / "stock-analysis-update-status.json",
    "practice-prices": ROOT / "data" / "practice-prices-update-status.json",
    "watch-predictions": ROOT / "data" / "watch-predictions-update-status.json",
    "market-overview": ROOT / "data" / "market-overview-update-status.json",
}
JOB_STATE_FILE = ROOT / "data" / "job-state.json"
ALLOW_REMOTE_JOBS = False


def initial_job_state() -> dict[str, dict[str, object]]:
    saved = {}
    if JOB_STATE_FILE.exists():
        try:
            saved = json.loads(JOB_STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            saved = {}
    state = {}
    for name in JOBS:
        previous = saved.get(name, {})
        if previous.get("status") == "running":
            previous = {}
        status_file = STATUS_FILES[name]
        metadata = {}
        if status_file.exists():
            try:
                metadata = json.loads(status_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                metadata = {}
        updated_at = metadata.get("updatedAt")
        record_count = metadata.get("recordCount")
        errors = metadata.get("errors") or []
        state[name] = {
            "status": previous.get("status") or ("success" if updated_at and not errors else "failed" if updated_at else "idle"),
            "startedAt": previous.get("startedAt"),
            "finishedAt": previous.get("finishedAt") or updated_at,
            "exitCode": previous.get("exitCode"),
            "output": previous.get("output") or (f"Last update produced {record_count} records." if updated_at else ""),
        }
    return state


job_state = initial_job_state()
state_lock = threading.Lock()


def persist_job_state() -> None:
    JOB_STATE_FILE.parent.mkdir(exist_ok=True)
    temporary = JOB_STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(job_state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(JOB_STATE_FILE)


def run_job(name: str) -> None:
    try:
        result = subprocess.run(
            [sys.executable, str(JOBS[name])],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        output = (result.stdout + result.stderr).strip()[-12000:]
        status = "success" if result.returncode == 0 else "failed"
        exit_code = result.returncode
    except subprocess.TimeoutExpired as error:
        output = f"Job timed out after 10 minutes.\n{error.stdout or ''}\n{error.stderr or ''}".strip()[-12000:]
        status = "failed"
        exit_code = -1
    except OSError as error:
        output = str(error)
        status = "failed"
        exit_code = -1
    with state_lock:
        job_state[name].update(
            {
                "status": status,
                "finishedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
                "exitCode": exit_code,
                "output": output,
            }
        )
        persist_job_state()
        database.record_job_run(name, job_state[name])
        if name == "results" and status == "success":
            database.import_result_verifications(ROOT / "data" / "results.json")


class JobHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'")
        super().end_headers()

    def send_json(self, payload: object, status: int = 200, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def session_token(self) -> str | None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return cookie["stockscope_session"].value if "stockscope_session" in cookie else None

    def current_user(self) -> dict | None:
        return database.session_user(self.session_token())

    def require_user(self) -> dict | None:
        user = self.current_user()
        if not user:
            self.send_json({"error": "Authentication required"}, 401)
        return user

    def read_json_body(self) -> dict:
        length = min(int(self.headers.get("Content-Length", "0") or 0), 8192)
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/auth/session":
            user = self.current_user()
            self.send_json({"authenticated": bool(user), "user": user})
            return
        public_paths = {"/", "/index.html", "/styles.css", "/app.js", "/favicon.ico"}
        if parsed.path not in public_paths and not self.require_user():
            return
        if parsed.path == "/api/jobs":
            with state_lock:
                self.send_json(job_state)
            return
        if parsed.path == "/api/results-verification":
            self.send_json(database.verification_summary())
            return
        if parsed.path == "/api/company-profile":
            query = parse_qs(parsed.query)
            symbol = query.get("symbol", [""])[0].upper()
            exchange = query.get("exchange", ["NSE"])[0].upper()
            if exchange != "NSE" or not re.fullmatch(r"[A-Z0-9&.-]{1,30}", symbol):
                self.send_json({"error": "Only valid NSE symbols are supported"}, 400)
                return
            try:
                opener = nse.nse_opener()
                payload = nse.fetch_json(
                    f"https://www.nseindia.com/api/quote-equity?{urlencode({'symbol': symbol})}",
                    opener,
                    f"https://www.nseindia.com/get-quotes/equity?symbol={symbol}",
                )
                self.send_json(payload)
            except RuntimeError as error:
                self.send_json({"error": str(error)}, 502)
            return
        if parsed.path == "/api/company-news":
            query = parse_qs(parsed.query)
            symbol = query.get("symbol", [""])[0].upper()
            exchange = query.get("exchange", ["NSE"])[0].upper()
            company = query.get("company", [""])[0].strip()
            refresh = query.get("refresh", ["0"])[0] == "1"
            if not re.fullmatch(r"[A-Z0-9&.-]{1,30}", symbol) or exchange not in ("NSE", "BSE") or not company or len(company) > 160:
                self.send_json({"error": "Invalid company request"}, 400)
                return
            path = company_news.cache_path(exchange, symbol)
            if path.exists() and not refresh:
                try:
                    self.send_json(json.loads(path.read_text(encoding="utf-8")))
                    return
                except (OSError, json.JSONDecodeError):
                    pass
            try:
                payload = company_news.fetch_company_news(company, symbol, exchange)
                company_news.save_analysis(payload)
                self.send_json(payload)
            except Exception as error:
                self.send_json({"error": str(error)}, 502)
            return
        if parsed.path == "/api/company-fundamentals":
            query = parse_qs(parsed.query)
            symbol = query.get("symbol", [""])[0].upper()
            exchange = query.get("exchange", ["NSE"])[0].upper()
            company = query.get("company", [""])[0].strip()
            refresh = query.get("refresh", ["0"])[0] == "1"
            if not re.fullmatch(r"[A-Z0-9&.-]{1,30}", symbol) or exchange not in ("NSE", "BSE") or not company or len(company) > 160:
                self.send_json({"error": "Invalid company request"}, 400)
                return
            path = company_fundamentals.cache_path(exchange, symbol)
            if path.exists() and not refresh:
                try:
                    cached = json.loads(path.read_text(encoding="utf-8"))
                    if company_fundamentals.has_useful_data(cached):
                        self.send_json(cached)
                        return
                except (OSError, json.JSONDecodeError):
                    pass
            try:
                payload = company_fundamentals.merge_cached_data(company_fundamentals.fetch_company_fundamentals(company, symbol, exchange))
                company_fundamentals.save(payload)
                self.send_json(payload)
            except Exception as error:
                self.send_json({"error": str(error)}, 502)
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/auth/login":
            try:
                payload = self.read_json_body()
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.send_json({"error": "Invalid login request"}, 400)
                return
            user = database.authenticate(str(payload.get("username", "")), str(payload.get("password", "")))
            if not user:
                self.send_json({"error": "Invalid username or password"}, 401)
                return
            token = database.create_session(user["id"], self.client_address[0])
            self.send_json(
                {"authenticated": True, "user": user},
                headers={"Set-Cookie": f"stockscope_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200"},
            )
            return
        if path == "/api/auth/logout":
            database.delete_session(self.session_token())
            self.send_json({"authenticated": False}, headers={"Set-Cookie": "stockscope_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"})
            return
        if not self.require_user():
            return
        if path == "/api/auth/change-password":
            try:
                payload = self.read_json_body()
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.send_json({"error": "Invalid password request"}, 400)
                return
            user = self.current_user()
            changed, message = database.change_password(user["id"], str(payload.get("currentPassword", "")), str(payload.get("newPassword", "")))
            self.send_json({"changed": changed, "message": message}, 200 if changed else 400)
            return
        if self.client_address[0] not in ("127.0.0.1", "::1") and not ALLOW_REMOTE_JOBS:
            self.send_json({"error": "Remote job execution is disabled. Restart with --allow-remote-jobs if this is a trusted Tailscale/LAN session."}, 403)
            return
        if self.headers.get("X-QuarterWatch-Action") != "run":
            self.send_json({"error": "Missing job action header"}, 403)
            return
        if not path.startswith("/api/jobs/"):
            self.send_json({"error": "Not found"}, 404)
            return
        name = path.removeprefix("/api/jobs/")
        if name not in JOBS:
            self.send_json({"error": "Unknown job"}, 404)
            return
        with state_lock:
            if job_state[name]["status"] == "running":
                self.send_json({"error": "Job is already running"}, 409)
                return
            job_state[name] = {
                "status": "running",
                "startedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
                "finishedAt": None,
                "exitCode": None,
                "output": "Job is starting...",
            }
            persist_job_state()
        threading.Thread(target=run_job, args=(name,), daemon=True).start()
        self.send_json({"job": name, "status": "running"}, 202)

    def log_message(self, message: str, *args: object) -> None:
        print(f"[job-server] {self.address_string()} - {message % args}")


def main() -> None:
    global ALLOW_REMOTE_JOBS
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1", help="Bind address. Use 0.0.0.0 or your Tailscale IP to access from other devices.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--allow-remote-jobs", action="store_true", help="Allow non-local devices to trigger updater jobs. Use only on a trusted Tailscale/LAN network.")
    parser.add_argument("--admin-user", default=os.environ.get("STOCKSCOPE_ADMIN_USER", "admin"))
    parser.add_argument("--admin-password", default=os.environ.get("STOCKSCOPE_ADMIN_PASSWORD"), help="Initial admin password. Used only when the database has no users.")
    args = parser.parse_args()
    generated_password = database.initialize_database(args.admin_user, args.admin_password)
    database.import_result_verifications(ROOT / "data" / "results.json")
    ALLOW_REMOTE_JOBS = args.allow_remote_jobs
    handler = lambda *handler_args, **kwargs: JobHandler(*handler_args, directory=str(ROOT), **kwargs)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"QuarterWatch running at http://{args.host}:{args.port}", flush=True)
    if generated_password:
        print(f"Initial admin credentials were written to {database.INITIAL_PASSWORD_FILE.relative_to(ROOT)}", flush=True)
    if args.host not in ("127.0.0.1", "localhost", "::1") and not args.allow_remote_jobs:
        print("Remote devices can view the app, but job execution is disabled. Add --allow-remote-jobs for trusted Tailscale access.", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
