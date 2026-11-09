import httpx
import pytest

from services.ai.ollama_client import OllamaClient, OllamaError


def test_generate_returns_response(monkeypatch):
    def fake_post(url, json, timeout):
        return httpx.Response(
            200,
            json={"response": '{"type": "welcome"}'},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    assert OllamaClient().generate("hi", json_mode=True) == '{"type": "welcome"}'


def test_generate_raises_ollama_error_on_failure(monkeypatch):
    def fake_post(url, json, timeout):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(OllamaError):
        OllamaClient().generate("hi")