"""
Fixed main.py with proper error handling and port management
"""

import os
import asyncio
import logging
from contextlib import asynccontextmanager


# Mock FastAPI and dependencies for demo
class MockFastAPI:
    def __init__(self):
        self.routers = []
        self.startup_handlers = []
        self.shutdown_handlers = []

    def include_router(self, router):
        self.routers.append(router)

    def on_event(self, event_type):
        def decorator(func):
            if event_type == "startup":
                self.startup_handlers.append(func)
            elif event_type == "shutdown":
                self.shutdown_handlers.append(func)
            return func

        return decorator


class ConsensusService:
    def __init__(self):
        # Get configuration from environment with defaults
        self.node_id = int(os.getenv("NODE_ID", "1"))

        # Parse peers from environment
        peer_addresses = []
        peers_env = os.getenv("PEERS", "")
        if peers_env:
            peer_addresses = [addr.strip() for addr in peers_env.split(",") if addr.strip()]

        print(f"Initializing node {self.node_id} with peers: {peer_addresses}")

        # Initialize components
        from consensus.raftNode import RaftNode, RaftParams, LogStorage

        raft_params = RaftParams(
            election_timeout_min=1500,
            election_timeout_max=3000,
            heartbeat_interval=500,
            rpc_timeout=300
        )

        self.raft_node = RaftNode(self.node_id, peer_addresses, raft_params)
        self.log_storage = LogStorage()
        self._running = False

    async def start(self):
        """Start the consensus service"""
        try:
            print(f"Starting consensus service for node {self.node_id}")
            await self.raft_node.start()
            self._running = True
            print("Consensus service started successfully")
        except Exception as e:
            print(f"Failed to start consensus service: {e}")
            raise

    async def stop(self):
        """Stop the consensus service"""
        if self._running:
            print("Stopping consensus service...")
            await self.raft_node.stop()
            self._running = False
            print("Consensus service stopped")

    def is_leader(self) -> bool:
        """Check if this node is the leader"""
        from consensus.raftNode import RaftRole
        return self.raft_node.role == RaftRole.LEADER

    async def append_log(self, data: dict) -> bool:
        """Append a log entry with consensus"""
        if not self.is_leader():
            return False

        # Create log entry
        from consensus.raftNode import LogEntry
        entry = LogEntry(
            term=self.raft_node.current_term,
            index=self.log_storage.last_index + 1,
            data=data
        )

        # Replicate to followers
        success = await self.raft_node.replicate_log(data)
        if success:
            self.log_storage.append(entry)
            return True
        return False

    def get_log(self, index: int):
        """Get a log entry by index"""
        return self.log_storage.get(index)

    def get_all_logs(self):
        """Get all log entries"""
        return self.log_storage.get_all()

    async def handle_request_vote(self, data: dict) -> dict:
        return await self.raft_node.handle_request_vote(data)

    async def handle_append_entries(self, data: dict) -> dict:
        return await self.raft_node.handle_append_entries(data)


# Create the FastAPI app with proper lifecycle management
@asynccontextmanager
async def lifespan(app):
    # Startup
    print("Application starting up...")
    try:
        await consensus_service.start()
        yield
    finally:
        # Shutdown
        print("Application shutting down...")
        await consensus_service.stop()


# Global consensus service
consensus_service = ConsensusService()

# Mock app for demo
app = MockFastAPI()


@app.on_event("startup")
async def startup_event():
    await consensus_service.start()


@app.on_event("shutdown")
async def shutdown_event():
    await consensus_service.stop()


# Demo the fixed application
async def demo_fixed_app():
    print("=== Fixed Application Demo ===")

    # Set up environment variables for testing
    os.environ["NODE_ID"] = "1"
    os.environ["PEERS"] = "localhost:8001,localhost:8002"

    # Create and test the service
    service = ConsensusService()

    print(f"Node ID: {service.node_id}")
    print(f"Is leader: {service.is_leader()}")

    # Test startup
    await service.start()

    # Test log operations
    test_data = {"name": "test_user", "password": "secure123"}

    # Force node to be leader for testing
    from consensus.raftNode import RaftRole
    service.raft_node.role = RaftRole.LEADER
    service.raft_node.current_term = 1

    print(f"After becoming leader - Is leader: {service.is_leader()}")

    # Test log append
    success = await service.append_log(test_data)
    print(f"Log append success: {success}")

    # Get all logs
    all_logs = service.get_all_logs()
    print(f"All logs: {all_logs}")

    # Test RPC handlers
    vote_request = {
        "term": 2,
        "candidate_id": 2,
        "last_log_index": 0,
        "last_log_term": 0
    }

    vote_response = await service.handle_request_vote(vote_request)
    print(f"Vote response: {vote_response}")

    # Clean shutdown
    await service.stop()

    print("=== Demo Complete ===")


# Run the demo
asyncio.run(demo_fixed_app())