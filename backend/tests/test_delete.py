from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import make_engine
from app.main import create_app


def test_delete_persists_and_readding_does_not_reuse_id(client, migrated_url):
    items = client.post("/api/pantry/bulk", json={"text": "rice,greek yoghurt"}).json()["items"]
    rice, yogurt = items
    response = client.delete(f"/api/pantry/{yogurt['id']}")
    assert response.status_code == 200
    assert response.json()["items"] == [rice]
    with TestClient(create_app(migrated_url)) as restarted:
        assert restarted.get("/api/pantry").json()["items"] == [rice]
    added = client.post("/api/pantry/bulk", json={"text": "greek yoghurt"})
    new_yogurt = added.json()["items"][-1]
    assert added.status_code == 201
    assert new_yogurt["id"] > yogurt["id"]
    assert new_yogurt["ingredient_id"] == yogurt["ingredient_id"]
    missing = client.delete(f"/api/pantry/{yogurt['id']}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PANTRY_ITEM_NOT_FOUND"
    assert missing.json()["error"]["request_id"] == missing.headers["X-Request-ID"]
    assert client.get("/api/pantry").json()["items"] == added.json()["items"]
    client.delete(f"/api/pantry/{rice['id']}")
    assert client.delete(f"/api/pantry/{new_yogurt['id']}").json()["items"] == []


def test_cannot_delete_another_owners_item(client, migrated_url):
    engine = make_engine(migrated_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO users (id, display_name) VALUES (2, 'Other')"))
            connection.execute(
                text("""
                INSERT INTO pantry_items
                (id, user_id, original_input, display_name, normalized_key, normalization_version)
                VALUES (200, 2, 'rice', 'rice', 'rice', 1)
            """)
            )
        assert client.delete("/api/pantry/200").status_code == 404
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM pantry_items WHERE id = 200")) == 1
    finally:
        engine.dispose()


def test_upgrade_preserves_existing_pantry(tmp_path):
    url = f"sqlite:///{(tmp_path / 'upgrade.db').as_posix()}"
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["database_url"] = url
    command.upgrade(config, "0001")
    with TestClient(create_app(url)) as client:
        before = client.post("/api/pantry/bulk", json={"text": " rice ,greek yoghurt"}).json()[
            "items"
        ]
    command.upgrade(config, "head")
    with TestClient(create_app(url)) as client:
        assert client.get("/api/pantry").json()["items"] == before
        last_id = before[-1]["id"]
        client.delete(f"/api/pantry/{last_id}")
        after = client.post("/api/pantry/bulk", json={"text": "tomato"}).json()["items"]
        assert after[-1]["id"] > last_id
