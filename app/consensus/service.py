from fastapi import HTTPException
from app.consensus.raftNode import RaftNode, RaftParams, RaftRole, LogEntry
from app.consensus.logStorage import LogStorage  # Correct import
import os


class ConsensusService:
    def __init__(self):
        # Initialize with node ID from environment
        self.node_id = int(os.getenv("NODE_ID", "1"))

        # Parse peers as host:port strings from environment variable
        peer_addresses = [addr.strip() for addr in os.getenv("PEERS", "").split(",") if addr.strip()]

        # Initialize Raft node with peer addresses
        raft_params = RaftParams(
            election_timeout_min=1500,
            election_timeout_max=3000,
            heartbeat_interval=500,
            rpc_timeout=300
        )
        self.raft_node = RaftNode(self.node_id, peer_addresses, raft_params)
        self.log_storage = LogStorage()

    async def start(self):
        """Start the consensus service"""
        await self.raft_node.start()

    def is_leader(self) -> bool:
        """Check if this node is the leader"""
        return self.raft_node.role == RaftRole.LEADER

    async def append_log(self, data: dict) -> bool:
        """Append a log entry with consensus"""
        if not self.is_leader():
            return False

        # Create log entry
        entry = LogEntry(
            term=self.raft_node.current_term,
            index=self.log_storage.last_index + 1,
            data=data
        )

        # Replicate to followers (simplified)
        success = await self.raft_node.replicate_log(entry.data)
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