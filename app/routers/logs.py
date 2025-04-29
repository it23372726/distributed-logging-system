from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import httpx
from app.database import get_db
from app.models import LogDB
from pydantic import BaseModel
from typing import List
from app.consensus.service import ConsensusService

router = APIRouter(
    prefix="/logs",
    tags=["logs"]
)

consensus_service = ConsensusService()


class Log(BaseModel):
    name: str
    password: str

    class Config:
        orm_mode = True


class LogCreate(Log):
    pass


class LogRead(Log):
    id: int


async def find_leader_node():
    """Helper function to find the current leader"""
    nodes = ["http://localhost:8000", "http://localhost:8001", "http://localhost:8002"]
    for url in nodes:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{url}/consensus/status", timeout=2.0)
                if response.json().get("is_leader"):
                    return url
        except (httpx.RequestError, httpx.HTTPStatusError):
            continue
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="No leader node available"
    )


@router.get("/", response_model=List[LogRead])
async def get_logs_api(db: Session = Depends(get_db)):
    if not consensus_service.is_leader():
        try:
            leader_url = await find_leader_node()
            return RedirectResponse(
                url=f"{leader_url}/logs/",
                status_code=status.HTTP_307_TEMPORARY_REDIRECT
            )
        except HTTPException as e:
            raise e

    db_logs = db.query(LogDB).all()
    consensus_logs = consensus_service.get_all_logs()
    return db_logs


@router.post("/", response_model=LogRead)
async def create_log(log: LogCreate, db: Session = Depends(get_db)):
    if not consensus_service.is_leader():
        leader_url = await find_leader_node()
        return RedirectResponse(
            url=f"{leader_url}/logs/",
            status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )

    success = await consensus_service.append_log(log.dict())
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to replicate log to majority of nodes"
        )

    db_log = LogDB(name=log.name, password=log.password)
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log

# Keep your existing PUT and DELETE endpoints with similar redirect logic