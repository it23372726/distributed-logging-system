import logging
import asyncio
import random
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum, auto
import httpx
import json


class RaftRole(Enum):
    FOLLOWER = auto()
    CANDIDATE = auto()
    LEADER = auto()


@dataclass
class RaftParams:
    election_timeout_min: int = 1500  # ms
    election_timeout_max: int = 3000  # ms
    heartbeat_interval: int = 500  # ms
    rpc_timeout: int = 300  # ms


@dataclass
class LogEntry:
    term: int
    index: int
    data: dict


class LogStorage:
    def __init__(self):
        self.logs: Dict[int, LogEntry] = {}
        self.last_index = 0

    def append(self, entry: LogEntry):
        """Append a new log entry"""
        self.logs[entry.index] = entry
        if entry.index > self.last_index:
            self.last_index = entry.index

    def get(self, index: int) -> Optional[LogEntry]:
        """Get a log entry by index"""
        return self.logs.get(index)

    def get_all(self) -> List[dict]:
        """Get all log entries in order"""
        return [
            {
                "term": self.logs[i].term,
                "index": self.logs[i].index,
                "data": self.logs[i].data
            }
            for i in sorted(self.logs.keys())
        ]


class RaftNode:
    def __init__(self, node_id: int, peers: List[str], params: RaftParams):
        self.node_id = node_id
        self.peers = peers
        self.params = params

        # Persistent state
        self.current_term = 0
        self.voted_for: Optional[int] = None
        self.log: List[LogEntry] = []

        # Volatile state
        self.commit_index = 0
        self.last_applied = 0
        self.role = RaftRole.FOLLOWER

        # Leader state
        self.next_index: Dict[str, int] = {}
        self.match_index: Dict[str, int] = {}

        # Networking
        self.peer_clients: Dict[str, httpx.AsyncClient] = {}
        self.election_timer = None
        self.heartbeat_timer = None

        # Logger setup
        self.logger = logging.getLogger(f"raft_node_{node_id}")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            ch = logging.StreamHandler()
            ch.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)

    async def start(self):
        self.logger.info(f"Node {self.node_id} starting with peers: {self.peers}")

        # Initialize HTTP clients for peer communication
        self.peer_clients = {
            peer: httpx.AsyncClient(
                base_url=f"http://{peer}",
                timeout=10.0
            )
            for peer in self.peers
        }

        self.role = RaftRole.FOLLOWER
        self._reset_election_timer()
        self.logger.info(f"Node {self.node_id} started as {self.role.name} (term {self.current_term})")

    def _reset_election_timer(self):
        if self.election_timer:
            self.election_timer.cancel()

        timeout = random.uniform(
            self.params.election_timeout_min / 1000,
            self.params.election_timeout_max / 1000
        )
        self.election_timer = asyncio.create_task(self._election_timeout(timeout))

    async def _election_timeout(self, timeout: float):
        try:
            await asyncio.sleep(timeout)

            if self.role == RaftRole.LEADER:
                return

            self.logger.info(f"Election timeout, becoming candidate (term {self.current_term + 1})")
            self.role = RaftRole.CANDIDATE
            self.current_term += 1
            self.voted_for = self.node_id

            votes_received = 1  # vote for self
            tasks = []

            for peer in self.peers:
                tasks.append(self._request_vote(peer))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            votes_received += sum(
                1 for result in results if isinstance(result, dict) and result.get("vote_granted", False)
            )

            if votes_received > (len(self.peers) + 1) / 2:
                await self._become_leader()
            else:
                self.role = RaftRole.FOLLOWER
                self._reset_election_timer()

        except Exception as e:
            self.logger.error(f"Error in election timeout: {e}")
            self.role = RaftRole.FOLLOWER
            self._reset_election_timer()

    async def _request_vote(self, peer: str) -> Dict[str, Any]:
        try:
            client = self.peer_clients[peer]
            data = {
                "term": self.current_term,
                "candidate_id": self.node_id,
                "last_log_index": len(self.log),
                "last_log_term": self.log[-1].term if self.log else 0
            }

            response = await client.post("/consensus/request_vote", json=data)
            return response.json()
        except Exception as e:
            self.logger.warning(f"Failed to request vote from node {peer}: {e}")
            return {"vote_granted": False, "term": self.current_term}

    async def _become_leader(self):
        self.role = RaftRole.LEADER
        self.logger.info(f"Node {self.node_id} became leader for term {self.current_term}")

        for peer in self.peers:
            self.next_index[peer] = len(self.log) + 1
            self.match_index[peer] = 0

        self._start_heartbeat_timer()

    def _start_heartbeat_timer(self):
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()

        interval = self.params.heartbeat_interval / 1000
        self.heartbeat_timer = asyncio.create_task(self._send_heartbeats(interval))

    async def _send_heartbeats(self, interval: float):
        while self.role == RaftRole.LEADER:
            try:
                await self._send_append_entries_to_all()
                await asyncio.sleep(interval)
            except Exception as e:
                self.logger.error(f"Error sending heartbeats: {e}")
                await asyncio.sleep(interval)

    async def _send_append_entries_to_all(self):
        if self.role != RaftRole.LEADER:
            return

        for peer in self.peers:
            try:
                await self._send_append_entries(peer)
            except Exception as e:
                self.logger.warning(f"Failed to send AppendEntries to {peer}: {e}")

    async def _send_append_entries(self, peer: str):
        try:
            client = self.peer_clients[peer]
            prev_log_index = self.next_index[peer] - 1
            prev_log_term = self.log[prev_log_index - 1].term if prev_log_index > 0 else 0

            # Get entries to send
            entries = []
            if len(self.log) >= self.next_index[peer]:
                entries = [
                    {
                        "term": entry.term,
                        "index": entry.index,
                        "data": entry.data
                    }
                    for entry in self.log[self.next_index[peer] - 1:]
                ]

            data = {
                "term": self.current_term,
                "leader_id": self.node_id,
                "prev_log_index": prev_log_index,
                "prev_log_term": prev_log_term,
                "entries": entries,
                "leader_commit": self.commit_index
            }

            response = await client.post("/consensus/append_entries", json=data)
            result = response.json()

            if result.get("success", False):
                if entries:
                    self.match_index[peer] = entries[-1]["index"]
                    self.next_index[peer] = self.match_index[peer] + 1
            else:
                # Decrement next_index and retry
                self.next_index[peer] = max(1, self.next_index[peer] - 1)

        except Exception as e:
            self.logger.warning(f"Failed to send AppendEntries to {peer}: {e}")

    async def replicate_log(self, entry_data: dict) -> bool:
        """Replicate a log entry to followers"""
        if self.role != RaftRole.LEADER:
            return False

        new_entry = LogEntry(
            term=self.current_term,
            index=len(self.log) + 1,
            data=entry_data
        )
        self.log.append(new_entry)

        # Send to all followers
        success_count = 1  # self
        for peer in self.peers:
            try:
                await self._send_append_entries(peer)
                success_count += 1
            except Exception as e:
                self.logger.warning(f"Failed to replicate to {peer}: {e}")

        # Check if majority accepted
        if success_count > (len(self.peers) + 1) / 2:
            self.commit_index = len(self.log)
            return True

        return False

    async def handle_request_vote(self, data: dict) -> dict:
        """Handle RequestVote RPC"""
        term = data.get("term", 0)
        candidate_id = data.get("candidate_id")
        last_log_index = data.get("last_log_index", 0)
        last_log_term = data.get("last_log_term", 0)

        # Update term if necessary
        if term > self.current_term:
            self.current_term = term
            self.voted_for = None
            self.role = RaftRole.FOLLOWER

        vote_granted = False

        # Grant vote if:
        # 1. Haven't voted in this term OR already voted for this candidate
        # 2. Candidate's log is at least as up-to-date as ours
        if (term >= self.current_term and
                (self.voted_for is None or self.voted_for == candidate_id)):

            our_last_log_term = self.log[-1].term if self.log else 0
            our_last_log_index = len(self.log)

            log_ok = (last_log_term > our_last_log_term or
                      (last_log_term == our_last_log_term and last_log_index >= our_last_log_index))

            if log_ok:
                vote_granted = True
                self.voted_for = candidate_id
                self._reset_election_timer()

        return {
            "term": self.current_term,
            "vote_granted": vote_granted
        }

    async def handle_append_entries(self, data: dict) -> dict:
        """Handle AppendEntries RPC"""
        term = data.get("term", 0)
        leader_id = data.get("leader_id")
        prev_log_index = data.get("prev_log_index", 0)
        prev_log_term = data.get("prev_log_term", 0)
        entries = data.get("entries", [])
        leader_commit = data.get("leader_commit", 0)

        # Update term if necessary
        if term > self.current_term:
            self.current_term = term
            self.voted_for = None

        self.role = RaftRole.FOLLOWER
        self._reset_election_timer()

        success = False

        if term >= self.current_term:
            # Check if log contains entry at prev_log_index with matching term
            if prev_log_index == 0 or (
                    prev_log_index <= len(self.log) and
                    self.log[prev_log_index - 1].term == prev_log_term
            ):
                success = True

                # Append new entries
                for i, entry_data in enumerate(entries):
                    entry_index = prev_log_index + i + 1
                    entry = LogEntry(
                        term=entry_data["term"],
                        index=entry_index,
                        data=entry_data["data"]
                    )

                    # Replace conflicting entries
                    if entry_index <= len(self.log):
                        self.log[entry_index - 1] = entry
                    else:
                        self.log.append(entry)

                # Update commit index
                if leader_commit > self.commit_index:
                    self.commit_index = min(leader_commit, len(self.log))

        return {
            "term": self.current_term,
            "success": success
        }

    async def stop(self):
        if self.election_timer:
            self.election_timer.cancel()
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()

        for client in self.peer_clients.values():
            await client.aclose()


# Demo usage
async def demo_raft_node():
    """Demonstrate the fixed Raft node implementation"""
    print("=== Raft Node Implementation Demo ===")

    # Create a simple 3-node cluster configuration
    peers = ["localhost:8001", "localhost:8002"]  # Other nodes
    params = RaftParams(
        election_timeout_min=1500,
        election_timeout_max=3000,
        heartbeat_interval=500
    )

    # Create node 1
    node = RaftNode(node_id=1, peers=peers, params=params)

    print(f"Created Raft node {node.node_id}")
    print(f"Initial role: {node.role.name}")
    print(f"Initial term: {node.current_term}")

    # Simulate starting the node (without actual network)
    print("\n=== Testing RPC Handlers ===")

    # Test RequestVote handler
    vote_request = {
        "term": 2,
        "candidate_id": 2,
        "last_log_index": 0,
        "last_log_term": 0
    }

    vote_response = await node.handle_request_vote(vote_request)
    print(f"Vote request response: {vote_response}")

    # Test AppendEntries handler
    append_request = {
        "term": 2,
        "leader_id": 2,
        "prev_log_index": 0,
        "prev_log_term": 0,
        "entries": [
            {
                "term": 2,
                "index": 1,
                "data": {"name": "test_user", "password": "test123"}
            }
        ],
        "leader_commit": 1
    }

    append_response = await node.handle_append_entries(append_request)
    print(f"Append entries response: {append_response}")
    print(f"Node log after append: {len(node.log)} entries")

    if node.log:
        print(f"First log entry: {node.log[0].data}")

    print(f"Updated role: {node.role.name}")
    print(f"Updated term: {node.current_term}")
    print(f"Commit index: {node.commit_index}")

    print("\n=== Log Storage Demo ===")
    log_storage = LogStorage()

    # Add some test entries
    for i in range(3):
        entry = LogEntry(
            term=1,
            index=i + 1,
            data={"user": f"user_{i}", "action": f"action_{i}"}
        )
        log_storage.append(entry)

    print(f"Log storage has {log_storage.last_index} entries")
    print("All logs:", json.dumps(log_storage.get_all(), indent=2))

    print("\n=== Demo Complete ===")


# Run the demo
asyncio.run(demo_raft_node())