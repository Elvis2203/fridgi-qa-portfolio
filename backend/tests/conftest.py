from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def migrated_url(tmp_path):
    url = f"sqlite:///{(tmp_path / 'pantry.db').as_posix()}"
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")
    return url


@pytest.fixture
def client(migrated_url):
    with TestClient(create_app(migrated_url)) as client:
        yield client
