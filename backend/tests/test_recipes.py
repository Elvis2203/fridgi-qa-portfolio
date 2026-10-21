import copy
import io
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.recipe_models import RecipeCandidate
from app.recipe_provider import SAMPLE_RECIPE, OpenAIRecipeProvider, ProviderUnavailable
from app.recipes import InvalidRecipeOutput

ENDPOINT = "/api/recipes/suggestions"


class FakeProvider:
    configured = True
    source = "openai"

    def __init__(self, payload=None):
        self.payload = (
            payload if payload is not None else {"recipes": [copy.deepcopy(SAMPLE_RECIPE)]}
        )
        self.calls = []

    def generate(self, context):
        self.calls.append(context)
        return self.payload


def test_sample_groups_aliases_and_soft_preferences_without_writes(client):
    pantry = client.post("/api/pantry/bulk", json={"text": "greek yoghurt,oats"}).json()["items"]
    response = client.post(
        ENDPOINT,
        json={
            "must_use_item_ids": [pantry[0]["id"]],
            "prefer_to_avoid_text": "APPLE,Greek yoghurt",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "sample"
    assert data["check_scope"] == "structure_and_ingredient_names_only"
    recipe = data["recipes"][0]
    assert [item["name"] for item in recipe["in_pantry"]] == ["Greek yogurt", "oats"]
    assert [item["name"] for item in recipe["missing"]] == ["apple"]
    assert recipe["in_pantry"][0]["pantry_item_id"] == pantry[0]["id"]
    assert {warning["code"] for warning in recipe["warnings"]} == {
        "PREFERRED_AVOID_PRESENT",
        "REQUIRED_AND_PREFERRED_AVOID",
    }
    assert client.get("/api/pantry").json()["items"] == pantry
    assert response.headers["Cache-Control"] == "no-store"


def test_empty_pantry_sample_has_every_ingredient_missing(client):
    result = client.post(ENDPOINT, json={}).json()["recipes"][0]
    assert result["in_pantry"] == []
    assert len(result["missing"]) == 3


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", " "),
        ("title", "x" * 161),
        ("servings", 0),
        ("servings", 13),
        ("servings", True),
        ("servings", "2"),
        ("prep_minutes", -1),
        ("cook_minutes", 241),
        ("ingredients", []),
        ("instructions", []),
        ("instructions", [" "]),
        ("instructions", ["x" * 1001]),
        ("allergy_safe", True),
    ],
)
def test_malformed_candidate_is_rejected(migrated_url, field, value):
    bad = copy.deepcopy(SAMPLE_RECIPE)
    bad[field] = value
    with TestClient(create_app(migrated_url, FakeProvider({"recipes": [bad]}))) as api:
        response = api.post(ENDPOINT, json={"source": "openai"})
        assert response.status_code == 502
        assert "INVALID_STRUCTURE" in response.json()["error"]["reason_codes"]
        assert "recipes" not in response.json()


@pytest.mark.parametrize("quantity", [0, -1, True, "10", float("nan"), float("inf"), 100001])
def test_invalid_quantity_is_rejected(quantity):
    candidate = copy.deepcopy(SAMPLE_RECIPE)
    candidate["ingredients"][0]["quantity"] = quantity
    with pytest.raises(ValueError):
        RecipeCandidate.model_validate(candidate)


@pytest.mark.parametrize("name", [" ", "x" * 101, "eggs,rice", "eggs\nrice", "eggs\x00"])
def test_invalid_ingredient_name_is_rejected(name):
    candidate = copy.deepcopy(SAMPLE_RECIPE)
    candidate["ingredients"][0]["name"] = name
    with pytest.raises(ValueError):
        RecipeCandidate.model_validate(candidate)


def test_total_time_and_unit_validation():
    candidate = copy.deepcopy(SAMPLE_RECIPE)
    candidate["prep_minutes"] = 0
    with pytest.raises(ValueError):
        RecipeCandidate.model_validate(candidate)
    candidate["prep_minutes"] = 5
    candidate["ingredients"][0]["unit"] = "handful"
    with pytest.raises(ValueError):
        RecipeCandidate.model_validate(candidate)


def test_partial_output_omits_missing_required_and_duplicate_candidates(migrated_url):
    absent = copy.deepcopy(SAMPLE_RECIPE)
    absent["ingredients"] = absent["ingredients"][1:]
    absent["title"] = "Greek yogurt is mentioned only in prose"
    duplicate = copy.deepcopy(SAMPLE_RECIPE)
    duplicate["ingredients"].append({"name": "greek yoghurt", "quantity": 1, "unit": "tsp"})
    provider = FakeProvider({"recipes": [absent, duplicate, copy.deepcopy(SAMPLE_RECIPE)]})
    with TestClient(create_app(migrated_url, provider)) as api:
        item = api.post("/api/pantry/bulk", json={"text": "Greek yoghurt"}).json()["items"][0]
        response = api.post(ENDPOINT, json={"source": "openai", "must_use_item_ids": [item["id"]]})
        assert response.status_code == 200
        data = response.json()
        assert len(data["recipes"]) == 1
        assert data["rejected"] == [
            {"candidate_index": 1, "codes": ["MISSING_REQUIRED_INGREDIENT"]},
            {"candidate_index": 2, "codes": ["DUPLICATE_INGREDIENT"]},
        ]
        assert provider.calls[0]["extra_ingredients_allowed"] is True
        assert provider.calls[0]["must_use"] == ["Greek yogurt"]


def test_tomato_does_not_satisfy_required_cherry_tomatoes(migrated_url):
    candidate = copy.deepcopy(SAMPLE_RECIPE)
    candidate["ingredients"].append({"name": "tomato", "quantity": 1, "unit": "piece"})
    with TestClient(create_app(migrated_url, FakeProvider({"recipes": [candidate]}))) as api:
        item = api.post("/api/pantry/bulk", json={"text": "cherry tomatoes"}).json()["items"][0]
        response = api.post(ENDPOINT, json={"source": "openai", "must_use_item_ids": [item["id"]]})
        assert response.status_code == 502
        assert "MISSING_REQUIRED_INGREDIENT" in response.text


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"recipes": []},
        {"recipes": [SAMPLE_RECIPE] * 4},
        {"recipes": [SAMPLE_RECIPE], "safe": True},
        [],
    ],
)
def test_invalid_provider_envelope(migrated_url, payload):
    with TestClient(create_app(migrated_url, FakeProvider(payload))) as api:
        assert api.post(ENDPOINT, json={"source": "openai"}).status_code == 502


@pytest.mark.parametrize(
    "body",
    [
        {"allergies": ["eggs"]},
        {"source": "invented"},
        {"must_use_item_ids": [999]},
        {"prefer_to_avoid_text": "x" * 101},
    ],
)
def test_invalid_request_never_calls_provider(migrated_url, body):
    provider = FakeProvider()
    with TestClient(create_app(migrated_url, provider)) as api:
        response = api.post(ENDPOINT, json={"source": "openai", **body})
        assert response.status_code == 422
        assert provider.calls == []


def test_pantries_can_change_during_generation_and_concurrent_call_is_rejected(migrated_url):
    entered, release = Event(), Event()

    class WaitingProvider(FakeProvider):
        def generate(self, context):
            entered.set()
            assert release.wait(5)
            return super().generate(context)

    with TestClient(create_app(migrated_url, WaitingProvider())) as api:
        item = api.post("/api/pantry/bulk", json={"text": "greek yoghurt"}).json()["items"][0]
        with ThreadPoolExecutor() as pool:
            pending = pool.submit(
                api.post,
                ENDPOINT,
                json={
                    "source": "openai",
                    "must_use_item_ids": [item["id"]],
                },
            )
            try:
                assert entered.wait(5)
                assert api.post(ENDPOINT, json={"source": "openai"}).status_code == 429
                assert api.delete(f"/api/pantry/{item['id']}").status_code == 200
            finally:
                release.set()
            response = pending.result()
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "PANTRY_CHANGED"
        assert api.post(ENDPOINT, json={"source": "openai"}).status_code == 200


def test_missing_config_disables_live_but_not_sample(client, monkeypatch):
    monkeypatch.delenv("FRIDGI_ENABLE_AI", raising=False)
    assert client.get("/api/recipes/capabilities").json()["live_available"] is False
    assert client.post(ENDPOINT, json={"source": "openai"}).status_code == 503
    assert client.post(ENDPOINT, json={"source": "sample"}).status_code == 200


def configure_provider(monkeypatch, envelope):
    monkeypatch.setenv("FRIDGI_ENABLE_AI", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    captured = []

    def respond(request, timeout):
        captured.append((request, timeout))
        return io.BytesIO(json.dumps(envelope).encode())

    monkeypatch.setattr("app.recipe_provider.urlopen", respond)
    return OpenAIRecipeProvider(), captured


def test_openai_request_uses_schema_and_extracts_message_after_reasoning(monkeypatch):
    provider, calls = configure_provider(
        monkeypatch,
        {
            "status": "completed",
            "output": [
                {"type": "reasoning"},
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": json.dumps({"recipes": [SAMPLE_RECIPE]})}
                    ],
                },
            ],
        },
    )
    assert provider.generate({"pantry": ["eggs"]}) == {"recipes": [SAMPLE_RECIPE]}
    request, timeout = calls[0]
    body = json.loads(request.data)
    assert body["store"] is False
    assert body["text"]["format"]["strict"] is True
    assert body["text"]["format"]["schema"]["additionalProperties"] is False
    assert body["max_output_tokens"] == 4000
    assert timeout == 40
    assert request.full_url == "https://api.openai.com/v1/responses"


@pytest.mark.parametrize(
    "envelope",
    [
        {"status": "incomplete"},
        {"status": "completed", "output": []},
        {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal"}]}]},
        {
            "status": "completed",
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": "broken json"}]}
            ],
        },
        [],
    ],
)
def test_openai_refusal_incomplete_or_malformed_output(monkeypatch, envelope):
    provider, _ = configure_provider(monkeypatch, envelope)
    with pytest.raises(InvalidRecipeOutput):
        provider.generate({})


def test_openai_failures_are_sanitized_and_not_retried(monkeypatch):
    provider, _ = configure_provider(monkeypatch, {})
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise HTTPError("https://api.openai.com", 401, "test-key-not-real", {}, None)

    monkeypatch.setattr("app.recipe_provider.urlopen", fail)
    with pytest.raises(ProviderUnavailable) as caught:
        provider.generate({})
    assert "test-key" not in str(caught.value)
    assert len(calls) == 1


def test_openai_response_size_limit(monkeypatch):
    provider, _ = configure_provider(monkeypatch, {})
    monkeypatch.setattr("app.recipe_provider.urlopen", lambda *a, **k: io.BytesIO(b"x" * 262145))
    with pytest.raises(InvalidRecipeOutput, match="size limit"):
        provider.generate({})
