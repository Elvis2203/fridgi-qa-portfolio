import io
import json
import ssl
from urllib.error import HTTPError, URLError

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.recipe_provider import OpenAIRecipeProvider, ProviderUnavailable, http_failure


@pytest.mark.parametrize(
    "status,code,kind,reason",
    [
        (401, "invalid_api_key", None, "PROVIDER_AUTHENTICATION_FAILED"),
        (403, None, None, "PROVIDER_ACCESS_DENIED"),
        (404, None, None, "PROVIDER_MODEL_UNAVAILABLE"),
        (400, "model_not_found", None, "PROVIDER_MODEL_UNAVAILABLE"),
        (429, "insufficient_quota", None, "PROVIDER_QUOTA_EXCEEDED"),
        (429, "credit_balance_exhausted", None, "PROVIDER_QUOTA_EXCEEDED"),
        (429, "project_spend_limit_exceeded", None, "PROVIDER_QUOTA_EXCEEDED"),
        (429, "organization_spend_limit_exceeded", None, "PROVIDER_QUOTA_EXCEEDED"),
        (429, "organization_usage_limit_exceeded", None, "PROVIDER_QUOTA_EXCEEDED"),
        (429, "unknown", "insufficient_quota", "PROVIDER_QUOTA_EXCEEDED"),
        (429, "rate_limit_exceeded", None, "PROVIDER_RATE_LIMITED"),
        (400, "invalid_json_schema", None, "PROVIDER_REQUEST_REJECTED"),
        (422, None, None, "PROVIDER_REQUEST_REJECTED"),
        (503, None, None, "PROVIDER_SERVICE_ERROR"),
        (418, None, None, "PROVIDER_HTTP_ERROR"),
    ],
)
def test_provider_errors_reach_api_without_raw_data(
    migrated_url, monkeypatch, caplog, status, code, kind, reason
):
    monkeypatch.setenv("FRIDGI_ENABLE_AI", "1")
    monkeypatch.setenv("FRIDGI_RECIPE_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-test-key")
    calls = []
    stream = io.BytesIO(
        json.dumps(
            {
                "error": {
                    "code": code,
                    "type": kind,
                    "message": "secret-test-key private-pantry-text",
                }
            }
        ).encode()
    )

    def fail(*args, **kwargs):
        calls.append(1)
        raise HTTPError("https://api.openai.com", status, "private-reason", {}, stream)

    monkeypatch.setattr("app.recipe_provider.urlopen", fail)
    with TestClient(create_app(migrated_url)) as api:
        response = api.post("/api/recipes/suggestions", json={"source": "openai"})
        assert response.status_code == 503
        error = response.json()["error"]
        assert error["code"] == "RECIPE_SERVICE_UNAVAILABLE"
        assert error["reason_codes"] == [reason]
        assert "No automatic retry" in error["message"]
        assert error["request_id"] == response.headers["X-Request-ID"]
        assert error["request_id"] in caplog.text
        assert reason in caplog.text
        assert f"upstream_status={status}" in caplog.text
        for private in ("secret-test-key", "private-pantry-text", "private-reason"):
            assert private not in response.text + caplog.text
    assert stream.closed
    assert len(calls) == 1


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b"[]",
        b'{"error":null}',
        b'{"error":{"code":[]}}',
        b"x" * 20000,
    ],
)
def test_unusable_error_body_preserves_status_fallback(body):
    stream = io.BytesIO(body)
    failure = http_failure(HTTPError("https://api.openai.com", 429, "private", {}, stream))
    assert failure.reason == "PROVIDER_RATE_LIMITED"
    assert stream.closed


@pytest.mark.parametrize(
    "failure,reason",
    [
        (TimeoutError("private"), "PROVIDER_TIMEOUT"),
        (URLError(TimeoutError("private")), "PROVIDER_TIMEOUT"),
        (URLError(ssl.SSLCertVerificationError("private")), "PROVIDER_TLS_ERROR"),
        (URLError("private"), "PROVIDER_CONNECTION_ERROR"),
    ],
)
def test_connection_failures_are_distinguished_without_retry(monkeypatch, failure, reason):
    monkeypatch.setenv("FRIDGI_ENABLE_AI", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise failure

    monkeypatch.setattr("app.recipe_provider.urlopen", fail)
    with pytest.raises(ProviderUnavailable) as caught:
        OpenAIRecipeProvider().generate({})
    assert caught.value.reason == reason
    assert "private" not in str(caught.value)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "body,reason",
    [
        (b"error code: 1010", "PROVIDER_CLIENT_BLOCKED"),
        (b"error code: 1010\n", "PROVIDER_CLIENT_BLOCKED"),
        (b'{"error":{"code":"model_permission_blocked_org"}}', "PROVIDER_MODEL_BLOCKED"),
        (b'{"error":{"code":"model_permission_blocked_project"}}', "PROVIDER_MODEL_BLOCKED"),
        (b"unknown private response", "PROVIDER_ACCESS_DENIED"),
    ],
)
def test_403_distinguishes_gateway_from_model_permissions(body, reason):
    stream = io.BytesIO(body)
    failure = http_failure(HTTPError("https://api.groq.com", 403, "private", {}, stream), "Groq")
    assert failure.reason == reason
    assert failure.upstream_status == 403
    assert "Groq" in str(failure)
    assert "OpenAI" not in str(failure)
    assert "private" not in str(failure)
    assert stream.closed
