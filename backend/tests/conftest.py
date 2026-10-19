import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{ROOT / 'test.db'}")
os.environ["REDIS_URL"] = ""
os.environ["OSM_ENABLED"] = "true"
os.environ["GOOGLE_PLACES_API_KEY"] = ""
os.environ["BRAVE_SEARCH_API_KEY"] = ""
os.environ["GOOGLE_CSE_API_KEY"] = ""
os.environ["AI_PROVIDER"] = "none"
os.environ["ENABLE_DOMAIN_GUESSING"] = "false"
os.environ["SECRET_KEY"] = "test-secret-key-with-at-least-32-bytes!!"

import pytest  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app import models  # noqa: E402,F401


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
