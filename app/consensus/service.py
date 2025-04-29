from fastapi import HTTPException
from app.consensus.raftNode import RaftNode, RaftParams, RaftRole, LogEntry
from app.consensus.logStorage import LogStorage  # Correct import
import os


class ConsensusService:
    def __init__(self):
        # Initialize with node ID and peer IDs from environment
        self.node_id = int(os.getenv("NODE_ID", "1"))
        peer_ids = [int(id) for id in os.getenv("PEERS", "2,3").split(",")]

        # Initialize Raft node
        raft_params = RaftParams(
            election_timeout=1000,
            heartbeat_interval=500,
            rpc_timeout=300
        )
        self.raft_node = RaftNode(self.node_id, peer_ids, raft_params)

        # Initialize log storage
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