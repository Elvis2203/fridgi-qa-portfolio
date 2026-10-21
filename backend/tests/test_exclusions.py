from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.recipe_provider import SAMPLE_RECIPE


class Provider:
    source = "groq"
    configured = True

    def __init__(self):
        self.calls = []

    def generate(self, context):
        self.calls.append(context)
        clean = deepcopy(SAMPLE_RECIPE)
        clean["ingredients"] = [i for i in clean["ingredients"] if i["name"] != "apple"]
        return {"recipes": [SAMPLE_RECIPE, clean]}


@pytest.mark.parametrize("path", ["/api/recipe-requests/check", "/api/recipes/suggestions"])
def test_alias_conflict_prevents_provider_call(migrated_url, path):
    provider = Provider()
    with TestClient(create_app(migrated_url, provider)) as client:
        item = client.post("/api/pantry/bulk", json={"text": "greek yoghurt"}).json()["items"][0]
        body = {"must_use_item_ids": [item["id"]], "excluded_text": "GREEK YOGURT"}
        if path.endswith("suggestions"):
            body["source"] = "groq"
        response = client.post(path, json=body)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "CONFLICTING_REQUIREMENTS"
        assert "Greek yogurt" in response.json()["error"]["message"]
        assert provider.calls == []


def test_preference_warns_exclusion_rejects_without_writes(client):
    before = client.get("/api/pantry").json()
    path = "/api/recipes/suggestions"
    preferred = client.post(path, json={"prefer_to_avoid_text": "apple"})
    assert preferred.status_code == 200
    assert preferred.json()["recipes"][0]["warnings"][0]["code"] == "PREFERRED_AVOID_PRESENT"
    excluded = client.post(path, json={"prefer_to_avoid_text": "apple", "excluded_text": "APPLE"})
    assert excluded.status_code == 502
    assert "EXCLUDED_INGREDIENT_PRESENT" in excluded.json()["error"]["reason_codes"]
    assert client.get("/api/pantry").json() == before


def test_partial_rejection_and_provider_contract(migrated_url):
    provider = Provider()
    with TestClient(create_app(migrated_url, provider)) as client:
        response = client.post(
            "/api/recipes/suggestions", json={"source": "groq", "excluded_text": "apple"}
        )
    assert response.status_code == 200
    result = response.json()
    assert len(result["recipes"]) == 1
    assert result["rejected"] == [{"candidate_index": 1, "codes": ["EXCLUDED_INGREDIENT_PRESENT"]}]
    assert provider.calls[0]["do_not_use"] == ["apple"]


def test_conservative_names_and_custom_exclusions(client):
    item = client.post("/api/pantry/bulk", json={"text": "tomato"}).json()["items"][0]
    response = client.post(
        "/api/recipe-requests/check",
        json={
            "must_use_item_ids": [item["id"]],
            "excluded_text": "cherry tomatoes,homemade sauce, CHERRY TOMATOES",
        },
    )
    assert response.status_code == 200
    assert [i["normalized_key"] for i in response.json()["excluded"]] == [
        "cherry tomatoes",
        "homemade sauce",
    ]


@pytest.mark.parametrize(
    "value,status",
    [
        ("x" * 100, 200),
        ("x" * 101, 422),
        (",".join(f"food{i}" for i in range(50)), 200),
        (",".join(f"food{i}" for i in range(51)), 422),
        ("", 200),
    ],
)
def test_exclusion_boundaries(client, value, status):
    response = client.post("/api/recipe-requests/check", json={"excluded_text": value})
    assert response.status_code == status
    if status == 422:
        assert response.json()["error"]["field"] == "excluded_text"
