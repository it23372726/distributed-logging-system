import heapq
import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LogDB
from utils.ntp_sync import analyze_clock_skew

class TimeSyncService:
    def _init_(self, flush_delay=1):
        self.log_buffer = []
        self.lock = asyncio.Lock()
        self.flush_delay = flush_delay  # Default flush delay in seconds

    def update_flush_delay(self, new_delay: int):
        """
        Update the delay used for flushing logs.
        """
        self.flush_delay = new_delay
        print(f"[CONFIG] Flush delay updated to {new_delay} seconds")

    async def receive_log(self, log_entry: dict):
        """
        Buffer the log entry based on its timestamp (for reordering).
        """
        async with self.lock:
            heapq.heappush(self.log_buffer, (log_entry['timestamp'], log_entry))
            print(f"[BUFFER] Received log with timestamp: {log_entry['timestamp']}")

    async def flush_logs(self, db: AsyncSession):
        """
        Flush all buffered logs to the database in sorted order.
        """
        async with self.lock:
            while self.log_buffer:
                _, log_entry = heapq.heappop(self.log_buffer)
                await self.store_log(log_entry, db)
            print("[FLUSH] Log buffer flushed to DB")

    async def store_log(self, log_entry: dict, db: AsyncSession):
        """
        Persist a single log entry to the database.
        """
        db_log = LogDB(**log_entry)
        db.add(db_log)
        await db.commit()
        await db.refresh(db_log)
        print(f"[STORE] Log stored: {db_log}")

    async def process_incoming_log(self, log_data: dict, db: AsyncSession):
        """
        Process an incoming log by correcting timestamp using clock skew.
        """
        skew = analyze_clock_skew() or 0  # fallback: assume 0 skew if error
        corrected_time = datetime.utcnow() + timedelta(seconds=skew)

        log_entry = {
            'name': log_data['name'],
            'password': log_data['password'],
            'timestamp': corrected_time
        }

        print(f"[PROCESS] Corrected timestamp: {corrected_time} (skew: {skew:.6f} sec)")
        await self.receive_log(log_entry)

        # Trigger delayed flush with configured delay
        asyncio.create_task(self.delayed_flush(db, self.flush_delay))

    async def delayed_flush(self, db: AsyncSession, delay: int):
        """
        Wait for delay seconds before flushing buffered logs.
        """
        print(f"[DELAY] Waiting {delay} seconds before flush")
        await asyncio.sleep(delay)
        await self.flush_logs(db)