"""Configuration for the wedding studio bot.

Values come from environment variables, optionally loaded from a `.env`
file sitting next to this file (so `python bot.py` works without exporting
anything).
"""

from __future__ import annotations

import os
from datetime import timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv() -> None:
    """Minimal .env loader (no external dependency).

    Existing environment variables always win, which is what you want on a
    VPS where systemd supplies the real values.
    """
    path = BASE_DIR / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_dotenv()


def _parse_admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for chunk in raw.replace(",", " ").split():
        try:
            ids.add(int(chunk))
        except ValueError:
            continue
    return ids


BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "").strip()

# Telegram numeric user ids of the team leaders. Comma or space separated.
ADMIN_IDS: set[int] = _parse_admin_ids(os.environ.get("ADMIN_IDS", ""))

# SQLite file. Relative paths resolve against this file's directory.
_db_raw = os.environ.get("DB_PATH", "data/bot.db").strip() or "data/bot.db"
_db_path = Path(_db_raw)
DB_PATH: str = str(_db_path if _db_path.is_absolute() else BASE_DIR / _db_path)

TZ_NAME: str = os.environ.get("TZ_NAME", "Asia/Tehran").strip() or "Asia/Tehran"

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo(TZ_NAME)
except Exception:  # missing tzdata on some Windows setups
    TZ = timezone.utc

# Hard limits for the access-code gate.
CODE_MAX_ATTEMPTS = 8
CODE_WINDOW_SECONDS = 900

# Proxy (optional): "socks5://user:pass@host:port" or "http://host:port"
# Set PROXY_URL in .env to enable. Empty = no proxy.
PROXY_URL: str = os.environ.get("PROXY_URL", "").strip()

# Port for health check server (Render sets PORT env var for Web Services)
PORT: str = os.environ.get("PORT", "10000")
