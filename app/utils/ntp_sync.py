# utils/ntp_sync.py
import ntplib
from datetime import datetime

def sync_time(ntp_server="pool.ntp.org"):
    """
    Synchronizes with NTP and returns UTC datetime.
    """
    try:
        client = ntplib.NTPClient()
        response = client.request(ntp_server, version=3)
        synchronized_time = datetime.utcfromtimestamp(response.tx_time)
        print(f"[SYNC] Synchronized Time: {synchronized_time}")
        return synchronized_time
    except Exception as e:
        print(f"[SYNC] NTP sync failed: {e}")
        return datetime.utcnow()

def analyze_clock_skew(ntp_server="pool.ntp.org"):
    """
    Returns skew (in seconds) between local system clock and NTP time.
    """
    try:
        client = ntplib.NTPClient()
        response = client.request(ntp_server, version=3)
        ntp_time = datetime.utcfromtimestamp(response.tx_time)
        local_time = datetime.utcnow()
        skew = (ntp_time - local_time).total_seconds()
        print(f"[SKEW] Local: {local_time}, NTP: {ntp_time}, Skew: {skew:.6f} sec")
        return skew
    except Exception as e:
        print(f"[SKEW] Failed to analyze skew: {e}")
        return None
