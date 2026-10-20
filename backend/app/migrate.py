"""Aplica as migrações do Alembic programaticamente (usado com AUTO_MIGRATE=true na nuvem)."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import settings

log = logging.getLogger("prospecia.migrate")
last_error: str | None = None


def describe_error(e: Exception) -> str:
    """Descrição curta do erro, sem credenciais (remove usuário:senha de URLs)."""
    import re

    msg = re.sub(r"://[^@\s/]+@", "://***@", str(e))
    msg = re.sub(r"password=\S+", "password=***", msg)
    return f"{e.__class__.__name__}: {msg}"[:500]
ROOT = Path(__file__).resolve().parents[1]


_lock = threading.Lock()


def upgrade_head() -> None:
    """Aplica as migrações uma vez por processo.

    O Alembic usa estado global (`alembic.context`); requisições simultâneas na mesma instância
    (Fluid compute) não podem migrar em paralelo, por isso a trava.
    """
    with _lock:
        _upgrade()


def _upgrade() -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    url = settings.database_url_unpooled or settings.database_url
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(cfg, "head")
    log.info("migrações aplicadas")
