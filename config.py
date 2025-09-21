# config.py — centralized config + metadata engine
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# ---- Top-level constants (also imported by API/worker) ----
TRUST_PROXY = os.getenv("TRUST_PROXY", "1") == "1"
MAX_LOG_BYTES = int(os.getenv("MAX_LOG_BYTES", "4096"))
REDACT_KEYS = {
    k.strip().lower()
    for k in os.getenv(
        "REDACT_KEYS",
        "password,new_password,current_password,token,authorization,secret",
    ).split(",")
    if k.strip()
}
LOG_DIR = os.getenv("LOG_DIR", "./logs")
APP_NAME = os.getenv("APP_NAME", "pgsched-api")
RFC_ENTERPRISE_ID = int(os.getenv("RFC_ENTERPRISE_ID", "32473"))
ROTATE_UTC = os.getenv("LOG_ROTATE_UTC", "1") == "1"
GZIP_AFTER_DAYS = int(os.getenv("GZIP_AFTER_DAYS", "7"))
KEEP_DAYS = int(os.getenv("KEEP_DAYS", "200"))

PUBLIC_KEY_B64_PATH = os.getenv("PUBLIC_KEY_B64_PATH", "./public_key.base64")
PRIVATE_KEY_B64_PATH = os.getenv("APP_PRIVATE_KEY_B64_PATH")  # used by worker/API

# ---- App config holder ----
@dataclass
class Config:
    pg_dsn_app: str
    cors_allowed_origins: List[str]
    default_query_interval: int  # seconds
    _engine: Optional[Engine] = None

    def engine(self) -> Engine:
        if self._engine is None:
            if not self.pg_dsn_app:
                raise RuntimeError("PG_DSN_APP is required")
            self._engine = create_engine(self.pg_dsn_app, pool_pre_ping=True, future=True)
        return self._engine

    def private_key_path(self) -> Optional[Path]:
        if not PRIVATE_KEY_B64_PATH:
            return None
        return Path(PRIVATE_KEY_B64_PATH).expanduser()

# ---- Global cfg instance factory ----
_cfg: Optional[Config] = None

def load_config() -> None:
    global _cfg
    if _cfg is not None:
        return
    pg = os.getenv("PG_DSN_APP", "").strip()
    cors = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",") if o.strip()]
    default_interval = int(os.getenv("DEFAULT_QUERY_INTERVAL", "21600"))  # 6h
    _cfg = Config(pg_dsn_app=pg, cors_allowed_origins=cors, default_query_interval=default_interval)

def cfg() -> Config:
    if _cfg is None:
        load_config()
    return _cfg  # type: ignore[return-value]


