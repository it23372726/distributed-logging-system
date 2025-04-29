# utils/ntp_sync.py
import ntplib
from time import ctime
from datetime import datetime


def sync_time(ntp_server="pool.ntp.org"):
    """
    Synchronizes the system's time with an NTP server.

    :param ntp_server: The NTP server to sync with (default is 'pool.ntp.org')
    :return: Synchronized timestamp as a datetime object or None if synchronization fails
    """

    try:
        # Create an NTP client
        client = ntplib.NTPClient()
        # Request time from the specified NTP server
        response = client.request(ntp_server, version=3)

        # Convert the NTP time (UNIX timestamp) to a datetime object
        synchronized_time = datetime.utcfromtimestamp(response.tx_time)

        print(f"System time synchronized to: {synchronized_time}")
        return synchronized_time
    except ntplib.NTPException as e:
        print(f"Failed to sync time due to NTP issue: {e}")
    except Exception as e:
        print(f"Unexpected error occurred while syncing time: {e}")

    return None
