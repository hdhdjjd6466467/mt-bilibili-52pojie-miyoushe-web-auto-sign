from __future__ import annotations

from datetime import datetime
from pathlib import Path
import secrets

from cryptography.fernet import Fernet


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
RUN_LOG_DIR = LOG_DIR / "runs"
SESSION_LOG_DIR = LOG_DIR / "sessions"
STATE_DIR = BASE_DIR / "state"
TARGET_STATE_DIR = STATE_DIR / "targets"
TEMPLATE_DIR = BASE_DIR / "templates"
VENDOR_DIR = BASE_DIR / "vendor"
VENDOR_52 = VENDOR_DIR / "52pojie-auto-sign"
VENDOR_MIHOYO = VENDOR_DIR / "MihoyoBBSTools"
VENDOR_BILIBILI = VENDOR_DIR / "bilibili-auto-sign"
VENDOR_BINMT = VENDOR_DIR / "binmt-auto-sign"
DB_PATH = DATA_DIR / "app.db"
FERNET_KEY_PATH = DATA_DIR / "secret.key"
FLASK_SECRET_PATH = DATA_DIR / "flask-secret.txt"
INITIAL_ADMIN_PASSWORD_PATH = DATA_DIR / "initial-admin-password.txt"

SITE_ORDER = ["binmt", "mihoyo", "bilibili", "52pojie"]


def ensure_directories() -> None:
    for path in (
        DATA_DIR,
        LOG_DIR,
        RUN_LOG_DIR,
        SESSION_LOG_DIR,
        STATE_DIR,
        TARGET_STATE_DIR,
        TEMPLATE_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def now_local() -> datetime:
    return datetime.now().astimezone()


def now_iso() -> str:
    return now_local().isoformat(timespec="seconds")


def today_iso() -> str:
    return now_local().date().isoformat()


def get_fernet() -> Fernet:
    ensure_directories()
    if not FERNET_KEY_PATH.exists():
        FERNET_KEY_PATH.write_bytes(Fernet.generate_key())
    return Fernet(FERNET_KEY_PATH.read_bytes())


def get_flask_secret() -> str:
    ensure_directories()
    if not FLASK_SECRET_PATH.exists():
        FLASK_SECRET_PATH.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    return FLASK_SECRET_PATH.read_text(encoding="utf-8").strip()

