import pytest
from httpx import AsyncClient

from app import main as app_main
from app.model_client import ModelResponse


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(app=app_main.app, base_url="http://test") as ac:
        r = await ac.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_query_missing_fields():
    async with AsyncClient(app=app_main.app, base_url="http://test") as ac:
        # Missing prompt and user_id should produce 400
        r = await ac.post("/api/v1/query", json={"user_id": "", "prompt": ""})
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_query_success(monkeypatch):
    """
    Monkeypatch the model_client used by the running app to avoid external calls.
    """
    class DummyClient:
        async def generate(self, prompt, model_hint=None, **kwargs):
            return ModelResponse(text="Hello, this is a test reply.", model_name="nemotron-super")

    # Replace the real model_client with our dummy client instance
    monkeypatch.setattr(app_main, "model_client", DummyClient())

    payload = {"user_id": "test-user", "prompt": "Say hi", "use_memory": False}
    async with AsyncClient(app=app_main.app, base_url="http://test") as ac:
        r = await ac.post("/api/v1/query", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert "reply" in data and "Hello" in data["reply"]
        assert data["model_used"] == "nemotron-super"