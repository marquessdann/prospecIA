"""Aplica as migrações do Alembic programaticamente (usado com AUTO_MIGRATE=true na nuvem)."""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import settings

log = logging.getLogger("prospecia.migrate")
ROOT = Path(__file__).resolve().parents[1]


def upgrade_head() -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    url = settings.database_url_unpooled or settings.database_url
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(cfg, "head")
    log.info("migrações aplicadas")
