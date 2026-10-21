import io
import json
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.recipe_models import CandidateBatch
from app.recipe_provider import SAMPLE_RECIPE, GroqRecipeProvider, configured_provider
from app.recipes import InvalidRecipeOutput


def envelope(content=None, finish="stop"):
    return {
        "choices": [
            {
                "finish_reason": finish,
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"recipes": [SAMPLE_RECIPE]})
                    if content is None
                    else content,
                },
            }
        ]
    }


def setup_groq(monkeypatch, payload):
    monkeypatch.setenv("FRIDGI_ENABLE_AI", "1")
    monkeypatch.setenv("FRIDGI_RECIPE_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "unused-openai-secret")
    monkeypatch.delenv("FRIDGI_GROQ_MODEL", raising=False)
    calls = []

    def respond(request, timeout):
        calls.append((request, timeout))
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr("app.recipe_provider.urlopen", respond)
    return calls


def test_groq_request_and_independent_validation(migrated_url, monkeypatch):
    calls = setup_groq(monkeypatch, envelope())
    with TestClient(create_app(migrated_url)) as api:
        assert api.get("/api/recipes/capabilities").json() == {
            "sample_available": True,
            "live_available": True,
            "live_source": "groq",
        }
        yogurt = api.post("/api/pantry/bulk", json={"text": "greek yoghurt"}).json()["items"][0]
        result = api.post(
            "/api/recipes/suggestions",
            json={
                "source": "groq",
                "must_use_item_ids": [yogurt["id"]],
                "prefer_to_avoid_text": "apple",
            },
        ).json()
        assert result["source"] == "groq"
        checked = result["recipes"][0]
        assert checked["in_pantry"][0]["pantry_item_id"] == yogurt["id"]
        assert [item["name"] for item in checked["missing"]] == ["apple", "oats"]
        assert checked["warnings"][0]["code"] == "PREFERRED_AVOID_PRESENT"
        eggs = api.post("/api/pantry/bulk", json={"text": "eggs"}).json()["items"][-1]
        rejected = api.post(
            "/api/recipes/suggestions",
            json={
                "source": "groq",
                "must_use_item_ids": [eggs["id"]],
            },
        )
        assert rejected.status_code == 502
        assert rejected.json()["error"]["reason_codes"] == ["MISSING_REQUIRED_INGREDIENT"]
    request, timeout = calls[0]
    assert request.full_url == "https://api.groq.com/openai/v1/chat/completions"
    assert request.get_header("User-agent") == "Fridgi/0.1"
    assert request.get_header("Accept") == "application/json"
    assert request.get_header("Authorization") == "Bearer groq-test-secret"
    body = json.loads(request.data)
    assert body["model"] == "openai/gpt-oss-20b"
    assert body["max_completion_tokens"] == 4000
    assert body["reasoning_effort"] == "low"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"] == CandidateBatch.model_json_schema()
    assert json.loads(body["messages"][1]["content"])["must_use"] == ["Greek yogurt"]
    assert "unused-openai-secret" not in str(request.headers) + str(body)
    assert timeout == 40


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"choices": []},
        {"choices": [None]},
        {"choices": [1, 2]},
        envelope(finish="length"),
        envelope(finish="content_filter"),
        envelope("broken json"),
        {"choices": [{"finish_reason": "stop", "message": {"refusal": "private"}}]},
        {"choices": [{"finish_reason": "stop", "message": {"content": None}}]},
        {"choices": [{"finish_reason": "stop", "message": {"tool_calls": [1]}}]},
    ],
)
def test_groq_malformed_and_incomplete_responses(monkeypatch, payload):
    calls = setup_groq(monkeypatch, payload)
    with pytest.raises(InvalidRecipeOutput):
        GroqRecipeProvider().generate({})
    assert len(calls) == 1


def test_groq_failure_never_retries_or_falls_back(migrated_url, monkeypatch, caplog):
    setup_groq(monkeypatch, {})
    calls = []

    def fail(request, timeout):
        calls.append(request.full_url)
        raise HTTPError(
            request.full_url,
            429,
            "private",
            {},
            io.BytesIO(b'{"error":{"code":"rate_limit_exceeded","message":"groq-test-secret"}}'),
        )

    monkeypatch.setattr("app.recipe_provider.urlopen", fail)
    with TestClient(create_app(migrated_url)) as api:
        result = api.post("/api/recipes/suggestions", json={"source": "groq"})
        assert result.status_code == 503
        assert "Groq limited" in result.json()["error"]["message"]
        assert result.json()["error"]["reason_codes"] == ["PROVIDER_RATE_LIMITED"]
        assert "recipes" not in result.json()
        assert "groq-test-secret" not in result.text + caplog.text
    assert calls == ["https://api.groq.com/openai/v1/chat/completions"]


def test_missing_groq_key_and_stale_source_never_use_openai(migrated_url, monkeypatch):
    calls = setup_groq(monkeypatch, envelope())
    monkeypatch.delenv("GROQ_API_KEY")
    monkeypatch.delenv("FRIDGI_RECIPE_PROVIDER")
    assert isinstance(configured_provider(), GroqRecipeProvider)
    with TestClient(create_app(migrated_url)) as api:
        assert not api.get("/api/recipes/capabilities").json()["live_available"]
        assert api.post("/api/recipes/suggestions", json={"source": "groq"}).status_code == 503
        stale = api.post("/api/recipes/suggestions", json={"source": "openai"})
        assert stale.json()["error"]["reason_codes"] == ["PROVIDER_MISMATCH"]
        assert api.post("/api/recipes/suggestions", json={"source": "sample"}).status_code == 200
    assert calls == []


def test_unknown_provider_never_defaults_to_paid_service(monkeypatch):
    monkeypatch.setenv("FRIDGI_RECIPE_PROVIDER", "typo")
    with pytest.raises(ValueError, match="FRIDGI_RECIPE_PROVIDER"):
        configured_provider()
