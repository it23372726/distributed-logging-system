import subprocess
import time
import asyncio
import httpx
import pytest

# List of node configurations (ports and env files)
NODES = [
    {"port": 8000, "env": ".env.node1"},
    {"port": 8001, "env": ".env.node2"},
    {"port": 8002, "env": ".env.node3"},
]

def start_cluster():
    """Start all Raft nodes using uvicorn in subprocesses."""
    processes = []
    for node in NODES:
        process = subprocess.Popen([
            "uvicorn", "app.main:app",
            "--host", "127.0.0.1",
            "--port", str(node["port"]),
            "--env-file", node["env"]
        ])
        processes.append(process)
    return processes

def stop_cluster(processes):
    """Terminate all node processes."""
    for process in processes:
        process.terminate()
    for process in processes:
        process.wait()

@pytest.mark.asyncio
async def test_raft_cluster_consensus():
    """Full integration test of Raft leader election and log replication."""
    processes = start_cluster()
    time.sleep(5)  # Allow time for servers to start and elect a leader

    try:
        async with httpx.AsyncClient() as client:
            # Step 1: Check for leader
            leaders = []
            for node in NODES:
                response = await client.get(f"http://localhost:{node['port']}/consensus/status")
                assert response.status_code == 200
                data = response.json()
                if data.get("is_leader"):
                    leaders.append(node["port"])
            assert len(leaders) == 1, f"Expected one leader, found {len(leaders)}"
            leader_port = leaders[0]
            print(f"[✓] Leader elected on port: {leader_port}")

            # Step 2: Append a log entry to the leader
            test_log = {"name": "raft_test", "password": "abc123"}
            response = await client.post(
                f"http://localhost:{leader_port}/logs/",
                json=test_log
            )
            assert response.status_code == 200
            result = response.json()
            assert result.get("name") == "raft_test"
            print(f"[✓] Log entry appended to leader {leader_port}")

            # Step 3: Wait briefly for replication to complete
            await asyncio.sleep(2)

            # Step 4: Validate the log is present in all nodes
            for node in NODES:
                response = await client.get(f"http://localhost:{node['port']}/logs/")
                assert response.status_code == 200
                logs = response.json()
                assert any(log.get("name") == "raft_test" for log in logs), \
                    f"Log not replicated to node {node['port']}"
                print(f"[✓] Log found in node {node['port']}")

    finally:
        stop_cluster(processes)
        print("[✓] Cluster shutdown complete.")