from fastapi import APIRouter, HTTPException, Depends
from app.consensus.service import ConsensusService
from fastapi import status

router = APIRouter(
    prefix="/consensus",
    tags=["consensus"]
)

# Initialize the consensus service
consensus_service = ConsensusService()

@router.on_event("startup")
async def startup_event():
    await consensus_service.start()

@router.get("/status")
async def get_status():
    return {
        "node_id": consensus_service.node_id,
        "role": consensus_service.raft_node.role.name,
        "term": consensus_service.raft_node.current_term,
        "log_length": consensus_service.log_storage.last_index,
        "is_leader": consensus_service.is_leader()
    }

@router.get("/logs")
async def get_consensus_logs():
    return consensus_service.get_all_logs()

@router.get("/logs/{index}")
async def get_consensus_log(index: int):
    log = consensus_service.get_log(index)
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log entry not found"
        )
    return log