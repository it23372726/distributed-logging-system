import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import asyncio
from enum import Enum, auto


class RaftRole(Enum):
    FOLLOWER = auto()
    CANDIDATE = auto()
    LEADER = auto()


@dataclass
class RaftParams:
    election_timeout: int = 1000  # ms
    heartbeat_interval: int = 500  # ms
    rpc_timeout: int = 300  # ms


@dataclass
class LogEntry:
    term: int
    index: int
    data: dict


class RaftNode:
    def __init__(self, node_id: int, peers: List[int], params: RaftParams):
        self.node_id = node_id
        self.peers = peers
        self.params = params

        self.current_term = 0
        self.voted_for: Optional[int] = None
        self.role = RaftRole.FOLLOWER
        self.log: List[LogEntry] = []

        self.commit_index = 0
        self.last_applied = 0

        # Leader state
        self.next_index: Dict[int, int] = {}
        self.match_index: Dict[int, int] = {}

        self.election_timer = None
        self.heartbeat_timer = None
        self.logger = logging.getLogger(f"raft_node_{node_id}")

    async def start(self):
        """Start the Raft node"""
        self._reset_election_timer()
        self.logger.info(f"Node {self.node_id} started as follower")

    def _reset_election_timer(self):
        """Reset the election timeout"""
        if self.election_timer:
            self.election_timer.cancel()

        timeout = self.params.election_timeout / 1000
        self.election_timer = asyncio.create_task(self._election_timeout(timeout))

    async def _election_timeout(self, timeout: float):
        """Handle election timeout"""
        await asyncio.sleep(timeout)

        if self.role == RaftRole.LEADER:
            return

        self.logger.info(f"Election timeout, becoming candidate (term {self.current_term + 1})")
        self.role = RaftRole.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id

        # Request votes from peers
        votes = 1  # vote for self
        for peer in self.peers:
            # In a real implementation, send RPC to peers
            pass

        # If we get majority votes, become leader
        if votes > len(self.peers) / 2:
            await self._become_leader()

    async def _become_leader(self):
        """Transition to leader state"""
        self.role = RaftRole.LEADER
        self.logger.info(f"Node {self.node_id} became leader for term {self.current_term}")

        # Initialize leader state
        for peer in self.peers:
            self.next_index[peer] = len(self.log) + 1
            self.match_index[peer] = 0

        # Start sending heartbeats
        self._start_heartbeat_timer()

    def _start_heartbeat_timer(self):
        """Start periodic heartbeats"""
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()

        interval = self.params.heartbeat_interval / 1000
        self.heartbeat_timer = asyncio.create_task(self._send_heartbeats(interval))

    async def _send_heartbeats(self, interval: float):
        """Send periodic heartbeats to followers"""
        while self.role == RaftRole.LEADER:
            # In a real implementation, send AppendEntries RPC to all peers
            await asyncio.sleep(interval)

    async def replicate_log(self, entry: dict) -> bool:
        """Attempt to replicate a log entry to majority of nodes"""
        if self.role != RaftRole.LEADER:
            return False

        # In a real implementation, send AppendEntries RPC to all peers
        # and wait for majority to acknowledge

        # For this simplified version, we'll just append locally
        new_entry = LogEntry(
            term=self.current_term,
            index=len(self.log) + 1,
            data=entry
        )
        self.log.append(new_entry)
        return True