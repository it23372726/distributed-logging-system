import requests
from typing import List
from app.models import LogDB

# List of backup servers to which logs will be replicated
BACKUP_SERVERS = ["http://backup-server-1:8000", "http://backup-server-2:8000"]

def replicate_log(log: LogDB) -> bool:
    success = True
    for server in BACKUP_SERVERS:
        try:
            response = requests.post(f"{server}/logs/", json={
                "name": log.name,
                "password": log.password,
                "timestamp": log.timestamp.isoformat()  # Convert datetime to string
            })
            if response.status_code != 201:
                print(f"Failed to replicate log to {server}")
                success = False
        except requests.exceptions.RequestException as e:
            print(f"Error replicating log to {server}: {e}")
            success = False
    return success


