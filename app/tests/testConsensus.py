import pytest
from httpx import AsyncClient
from app.main import app
from app.consensus.service import ConsensusService

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest.mark.asyncio
async def test_leader_election(client):
    response = await client.get("/consensus/status")
    assert response.status_code == 200
    data = response.json()
    assert "role" in data
    assert data["role"] in ["FOLLOWER", "CANDIDATE", "LEADER"]

@pytest.mark.asyncio
async def test_log_replication(client):
    # Only the leader can append logs
    status = await client.get("/consensus/status")
    if status.json()["is_leader"]:
        test_log = {"name": "test", "password": "123"}
        response = await client.post("/logs/", json=test_log)
        assert response.status_code == 200
        assert response.json()["name"] == "test"