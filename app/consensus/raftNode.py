import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import asyncio
from enum import Enum, auto
import httpx
import random


class RaftRole(Enum):
    FOLLOWER = auto()
    CANDIDATE = auto()
    LEADER = auto()


@dataclass
class RaftParams:
    election_timeout_min: int = 1500  # ms (minimum)
    election_timeout_max: int = 3000  # ms (maximum)
    heartbeat_interval: int = 500  # ms
    rpc_timeout: int = 300  # ms


@dataclass
class LogEntry:
    term: int
    index: int
    data: dict


class RaftNode:
    def __init__(self, node_id: int, peers: List[str], params: RaftParams):
        """
        peers: list of addresses like ["localhost:8001", "localhost:8002"]
        """
        self.node_id = node_id
        self.peers = peers  # now list of strings "host:port"
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

        # Initialize HTTP clients for peer communication using full host:port addresses
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
                self._reset_election_timer()

        except Exception as e:
            self.logger.error(f"Error in election timeout: {e}")
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
            return {"error": str(e)}

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
                await self._send_append_entries(to_all=True)
                await asyncio.sleep(interval)
            except Exception as e:
                self.logger.error(f"Error sending heartbeats: {e}")
                await asyncio.sleep(interval)

    async def _send_append_entries(self, to_all: bool = False, peer: Optional[str] = None):
        if self.role != RaftRole.LEADER:
            return

        targets = self.peers if to_all else [peer]
        for target in targets:
            try:
                client = self.peer_clients[target]
                prev_log_index = self.next_index[target] - 1
                prev_log_term = self.log[prev_log_index - 1].term if prev_log_index > 0 else 0

                data = {
                    "term": self.current_term,
                    "leader_id": self.node_id,
                    "prev_log_index": prev_log_index,
                    "prev_log_term": prev_log_term,
                    "entries": [],
                    "leader_commit": self.commit_index
                }

                await client.post("/consensus/append_entries", json=data)
            except Exception as e:
                self.logger.warning(f"Failed to send AppendEntries to node {target}: {e}")

    async def replicate_log(self, entry: dict) -> bool:
        if self.role != RaftRole.LEADER:
            return False

        new_entry = LogEntry(
            term=self.current_term,
            index=len(self.log) + 1,
            data=entry
        )
        self.log.append(new_entry)

        success_count = 1  # self
        tasks = []

        for peer in self.peers:
            tasks.append(self._send_append_entries(peer=peer))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        success_count += sum(1 for result in results if not isinstance(result, Exception))

        if success_count > (len(self.peers) + 1) / 2:
            self.commit_index = len(self.log)
            return True

        return False

    async def stop(self):
        if self.election_timer:
            self.election_timer.cancel()
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()

        for client in self.peer_clients.values():
            await client.aclose()
