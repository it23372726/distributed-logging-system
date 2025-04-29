from typing import Dict, Optional
from dataclasses import dataclass
from app.consensus.raftNode import LogEntry


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

    def get_all(self) -> list:
        """Get all log entries in order"""
        return [self.logs[i] for i in sorted(self.logs.keys())]