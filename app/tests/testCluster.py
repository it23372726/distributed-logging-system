import subprocess
import time
import httpx

# Start 3 FastAPI instances (in background)
processes = [
    subprocess.Popen(["uvicorn", "app.main:app", "--port", "8000", "--env-file", ".env.node1"]),
    subprocess.Popen(["uvicorn", "app.main:app", "--port", "8001", "--env-file", ".env.node2"]),
    subprocess.Popen(["uvicorn", "app.main:app", "--port", "8002", "--env-file", ".env.node3"])
]

time.sleep(5)  # Wait for servers to start

async def test_cluster():
    async with httpx.AsyncClient() as client:
        # Test leader election
        leaders = set()
        for port in [8000, 8001, 8002]:
            resp = await client.get(f"http://localhost:{port}/consensus/status")
            if resp.json()["is_leader"]:
                leaders.add(port)
        assert len(leaders) == 1, "Cluster should have exactly one leader"

        # Test log replication
        leader_port = leaders.pop()
        test_log = {"name": "cluster_test", "password": "abc"}
        resp = await client.post(f"http://localhost:{leader_port}/logs/", json=test_log)
        assert resp.status_code == 200

        # Verify log exists on all nodes
        for port in [8000, 8001, 8002]:
            resp = await client.get(f"http://localhost:{port}/logs/")
            assert any(log["name"] == "cluster_test" for log in resp.json())

# Run the test
import asyncio
asyncio.run(test_cluster())

# Cleanup
for p in processes:
    p.terminate()