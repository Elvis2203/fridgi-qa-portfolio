import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db import make_engine
from app.domain import Entry, InvalidBatch, check_preferences, parse_batch

ENDPOINT = "/api/recipe-requests/check"


def test_preference_identity_is_conservative_and_preserves_first_input():
    result = check_preferences(
        parse_batch(" greek yoghurt ,GREEK YOGURT,tomato,cherry tomatoes,homemade sauce,EGGS"),
        {"greek yogurt", "tomato", "eggs"},
        {
            "greek yoghurt": Entry("", "Greek yogurt", "greek yogurt"),
            "greek yogurt": Entry("", "Greek yogurt", "greek yogurt"),
        },
    )
    assert [entry.display_name for entry in result.preferences] == [
        "Greek yogurt",
        "tomato",
        "cherry tomatoes",
        "homemade sauce",
        "EGGS",
    ]
    assert result.preferences[0].original_input == " greek yoghurt "
    assert [entry.normalized_key for entry in result.overlaps] == ["greek yogurt", "tomato", "eggs"]


def test_optional_preferences_do_not_change_pantry_empty_batch_rule():
    assert parse_batch(" , \r\n", allow_empty=True) == []
    with pytest.raises(InvalidBatch):
        parse_batch(" , \r\n")
    assert check_preferences(parse_batch("eggs"), {"homemade sauce"}, {}).overlaps == []


def test_empty_check_is_valid_and_scoped(client):
    response = client.post(ENDPOINT, json={})
    assert response.status_code == 200
    assert response.json() == {
        "must_use": [],
        "prefer_to_avoid": [],
        "excluded": [],
        "warnings": [],
        "check_scope": "reviewed_name_overlap_only",
        "recipe_generated": False,
    }
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Request-ID"]
    operation = client.get("/openapi.json").json()["paths"][ENDPOINT]["post"]
    assert {"200", "422", "503"}.issubset(operation["responses"])


def test_check_resolves_aliases_and_custom_foods_without_writes(client, migrated_url):
    pantry = client.post(
        "/api/pantry/bulk", json={"text": " greek yoghurt ,leftover roast chicken,tomato"}
    ).json()["items"]
    yogurt, chicken, tomato = pantry
    engine = make_engine(migrated_url)

    def snapshot():
        with engine.connect() as connection:
            return {
                table: connection.execute(text(f"SELECT * FROM {table}")).fetchall()
                for table in (
                    "users",
                    "ingredients",
                    "ingredient_aliases",
                    "pantry_items",
                    "sqlite_sequence",
                )
            }

    try:
        before = snapshot()
        response = client.post(
            ENDPOINT,
            json={
                "must_use_item_ids": [chicken["id"], yogurt["id"], chicken["id"], tomato["id"]],
                "prefer_to_avoid_text": (
                    " Greek YOGHURT ,greek yogurt,cherry tomatoes,unknown sauce"
                ),
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["must_use"] == [chicken, yogurt, tomato]
        assert [entry["display_name"] for entry in result["prefer_to_avoid"]] == [
            "Greek yogurt",
            "cherry tomatoes",
            "unknown sauce",
        ]
        assert result["prefer_to_avoid"][0]["original_input"] == " Greek YOGHURT "
        assert len(result["warnings"]) == 1
        assert result["warnings"][0]["code"] == "REQUIRED_AND_PREFERRED_AVOID"
        assert result["warnings"][0]["item_id"] == yogurt["id"]
        assert "takes priority" in result["warnings"][0]["message"]
        assert client.post(ENDPOINT, json={"prefer_to_avoid_text": "x" * 101}).status_code == 422
        assert client.post(ENDPOINT, json={"must_use_item_ids": [999]}).status_code == 422
        assert snapshot() == before
        assert client.get("/api/pantry").json()["items"] == pantry
    finally:
        engine.dispose()


@pytest.mark.parametrize("value", [True, "1", None, 1.0, 1.5, 0, -1, 2**63])
def test_invalid_required_id_type_or_range(client, value):
    response = client.post(ENDPOINT, json={"must_use_item_ids": [value]})
    assert response.status_code == 422
    assert response.json()["error"]["field"].startswith("must_use_item_ids")


@pytest.mark.parametrize(
    "body",
    [
        {"must_use_item_ids": None},
        {"must_use_item_ids": [1] * 51},
        {"prefer_to_avoid_text": None},
        {"prefer_to_avoid_text": 12},
        {"prefer_to_avoid_text": "a" * 10001},
        {"prefer_to_avoid_text": ",".join(["rice"] * 51)},
        {"prefer_to_avoid_text": "rice," + "x" * 101},
        {"prefer_to_avoid_text": "rice\x00"},
        {"allergies": ["peanuts"]},
        {"diet": "vegan"},
        {"user_id": 2},
    ],
)
def test_invalid_requirements_return_structured_errors(client, body):
    response = client.post(ENDPOINT, json=body)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["request_id"] == response.headers["X-Request-ID"]
    assert error["field"]
    if body.get("prefer_to_avoid_text") == "rice," + "x" * 101:
        assert error["field"] == "prefer_to_avoid_text"
        assert error["entry_index"] == 2


def test_requirement_boundaries_and_blank_preferences(client):
    item_id = client.post("/api/pantry/bulk", json={"text": "rice"}).json()["items"][0]["id"]
    response = client.post(
        ENDPOINT,
        json={
            "must_use_item_ids": [item_id] * 50,
            "prefer_to_avoid_text": ",".join(["\U0001f34e" * 100] * 50),
        },
    )
    assert response.status_code == 200
    assert len(response.json()["must_use"]) == 1
    assert len(response.json()["prefer_to_avoid"]) == 1
    assert (
        client.post(ENDPOINT, json={"prefer_to_avoid_text": " " * 10000}).json()["prefer_to_avoid"]
        == []
    )


def test_deleted_and_foreign_ids_are_unavailable_without_disclosure(client, migrated_url):
    old = client.post("/api/pantry/bulk", json={"text": "rice"}).json()["items"][0]["id"]
    client.delete(f"/api/pantry/{old}")
    new = client.post("/api/pantry/bulk", json={"text": "rice"}).json()["items"][0]["id"]
    engine = make_engine(migrated_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO users (id, display_name) VALUES (2, 'Other')"))
            connection.execute(
                text("""
                INSERT INTO pantry_items
                (id, user_id, original_input, display_name, normalized_key, normalization_version)
                VALUES (200, 2, 'private food', 'private food', 'private food', 1)
            """)
            )
        errors = []
        for unavailable in (old, 200, 999):
            response = client.post(ENDPOINT, json={"must_use_item_ids": [new, unavailable]})
            assert response.status_code == 422
            error = response.json()["error"]
            assert error["code"] == "UNAVAILABLE_PANTRY_ITEMS"
            assert error["field"] == "must_use_item_ids"
            errors.append(error["message"])
        assert len(set(errors)) == 1
        assert "private food" not in errors[0]
    finally:
        engine.dispose()


def test_unavailable_database_returns_503(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OperationalError("SELECT private data", {}, Exception("database offline"))

    monkeypatch.setattr("app.main.check_requirements", unavailable)
    response = client.post(ENDPOINT, json={})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert "private data" not in response.text
