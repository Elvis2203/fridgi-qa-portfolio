from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import make_engine
from app.main import create_app


def test_add_deduplicate_and_preserve_first_original(client):
    response = client.post(
        "/api/pantry/bulk",
        json={"text": "  Chicken ,CHICKEN, greek yoghurt ,Greek yogurt, tomato, cherry tomatoes"},
    )
    assert response.status_code == 201
    data = response.json()
    assert (data["added_count"], data["skipped_count"]) == (4, 2)
    assert len(data["results"]) == 6
    assert data["items"][0]["original_input"] == "  Chicken "
    yogurt = data["items"][1]
    assert yogurt["display_name"] == "Greek yogurt"
    assert yogurt["original_input"] == " greek yoghurt "
    assert yogurt["ingredient_id"] is not None
    assert data["items"][0]["ingredient_id"] is None
    duplicate = client.post("/api/pantry/bulk", json={"text": "chicken, greek yogurt"})
    assert duplicate.status_code == 200
    assert duplicate.json()["added_count"] == 0
    assert duplicate.json()["items"] == data["items"]


def test_unknown_and_html_names_are_data(client):
    names = [
        "nduja",
        "stracchino",
        "gochujang",
        "pane carasau",
        "leftover roast chicken",
        "homemade tomato sauce",
        "<script>alert('x')</script>",
    ]
    response = client.post("/api/pantry/bulk", json={"text": "\n".join(names)})
    assert response.status_code == 201
    assert [item["display_name"] for item in response.json()["items"]] == names
    assert all(item["ingredient_id"] is None for item in response.json()["items"])


@pytest.mark.parametrize(
    "body",
    [
        {"text": "rice," + "x" * 101},
        {"text": " , "},
        {"text": 12},
        {"text": "rice", "user_id": 99},
        {},
    ],
)
def test_invalid_input_is_422_and_does_not_partially_save(client, body):
    response = client.post("/api/pantry/bulk", json=body)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["request_id"] == response.headers["X-Request-ID"]
    assert error["message"]
    assert client.get("/api/pantry").json()["items"] == []


def test_reload_and_new_application_read_committed_data(client, migrated_url):
    expected = client.post("/api/pantry/bulk", json={"text": "gochujang"}).json()["items"]
    assert client.get("/api/pantry").json()["items"] == expected
    with TestClient(create_app(migrated_url)) as restarted:
        assert restarted.get("/api/pantry").json()["items"] == expected


def test_concurrent_duplicate_requests_create_one_row(client):
    def submit(_):
        return client.post("/api/pantry/bulk", json={"text": "rice"})

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(submit, range(4)))
    assert sorted(response.status_code for response in responses) == [200, 200, 200, 201]
    assert len(client.get("/api/pantry").json()["items"]) == 1


def test_database_failure_rolls_back_entire_batch(client, migrated_url):
    engine = make_engine(migrated_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("""
                CREATE TRIGGER fail_test_insert BEFORE INSERT ON pantry_items
                WHEN NEW.display_name = 'fail-test'
                BEGIN SELECT RAISE(ABORT, 'test failure'); END
            """)
            )
        response = client.post("/api/pantry/bulk", json={"text": "rice,fail-test"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
        assert client.get("/api/pantry").json()["items"] == []
    finally:
        engine.dispose()


def test_database_itself_enforces_duplicates_and_foreign_keys(client, migrated_url):
    client.post("/api/pantry/bulk", json={"text": "rice"})
    engine = make_engine(migrated_url)
    try:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text("""
                INSERT INTO pantry_items
                    (user_id, original_input, display_name, normalized_key, normalization_version)
                VALUES (1, 'RICE', 'RICE', 'rice', 1)
            """)
            )
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text("""
                INSERT INTO pantry_items
                    (user_id, original_input, display_name, normalized_key, normalization_version)
                VALUES (999, 'rice', 'rice', 'rice', 1)
            """)
            )
    finally:
        engine.dispose()


def test_documented_contract_and_no_store(client):
    response = client.get("/api/pantry")
    assert response.headers["Cache-Control"] == "no-store"
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/pantry/bulk"]["post"]
    assert {"200", "201", "422", "503"}.issubset(operation["responses"])
