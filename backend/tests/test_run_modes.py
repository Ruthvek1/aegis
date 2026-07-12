import pytest
from httpx import AsyncClient, ASGITransport
import datetime

from aegis.server import app, _daily_spend_usd

@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")

@pytest.mark.asyncio
async def test_demo_mode_requires_captcha(client):
    response = await client.post("/runs", json={"task": "test", "mode": "demo"})
    assert response.status_code == 400
    assert "Invalid CAPTCHA" in response.json()["detail"]

@pytest.mark.asyncio
async def test_demo_mode_valid_captcha(client):
    # Set limit low to ensure it falls back if exceeded, but we start at 0
    today = datetime.datetime.now().date().isoformat()
    _daily_spend_usd[today] = 0.0

    response = await client.post("/runs", json={"task": "test", "mode": "demo", "captcha_token": "valid_mock_123"})
    assert response.status_code == 200
    assert response.json()["mode"] == "demo"

@pytest.mark.asyncio
async def test_demo_mode_fallback_to_replay(client):
    today = datetime.datetime.now().date().isoformat()
    _daily_spend_usd[today] = 1.0  # Over 0.50 budget

    response = await client.post("/runs", json={"task": "test", "mode": "demo", "captcha_token": "valid_mock_123"})
    assert response.status_code == 200
    assert response.json()["mode"] == "replay"  # Should have mutated

@pytest.mark.asyncio
async def test_byo_key_mode(client):
    response = await client.post("/runs", json={"task": "test", "mode": "byo", "api_key": "sk-ant-testkey"})
    assert response.status_code == 200
    assert response.json()["mode"] == "byo"
