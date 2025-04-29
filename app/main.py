# app/main.py

from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import SessionLocal, create_tables
from app.models import LogDB
from typing import List
from pathlib import Path
from utils.ntp_sync import sync_time  # Import NTP sync function
from app.replication import replicate_log # Import replication function

app = FastAPI()

# Create the tables at the startup
create_tables()

# Synchronize system time at startup
sync_time()

# Setup templates and static directories
BASE_DIR = Path(__file__).resolve().parent.parent  # distributed-logging-system/

STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"

# Check if static directory exists, else create it
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Dependency to get a database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic models
class Log(BaseModel):
    name: str
    password: str

    class Config:
        orm_mode = True

class LogCreate(Log):
    pass

class LogRead(Log):
    id: int
    timestamp: datetime

# Frontend
@app.get("/", include_in_schema=False)
async def read_root(request: Request):
    return templates.TemplateResponse("logs.html", {"request": request})

# API endpoints
@app.get("/logs/", response_model=List[LogRead])
async def get_logs_api(db: Session = Depends(get_db)):
    logs = db.query(LogDB).all()
    return logs

@app.post("/logs/", response_model=LogRead)
async def create_log(log: LogCreate, db: Session = Depends(get_db)):
    synchronized_time = sync_time()
    timestamp = synchronized_time if synchronized_time else datetime.utcnow()

    db_log = LogDB(name=log.name, password=log.password, timestamp=timestamp)
    db.add(db_log)
    db.commit()
    db.refresh(db_log)

     # Replicate the log to backup servers
    replication_success = replicate_log(db_log)

    if not replication_success:
        raise HTTPException(
            status_code=500,
            detail="Log replication failed. Some replicas may not have received the log."
        )

    return db_log


@app.put("/logs/{log_id}", response_model=LogRead)
async def update_log(log_id: int, updated_log: LogCreate, db: Session = Depends(get_db)):
    db_log = db.query(LogDB).filter(LogDB.id == log_id).first()
    if not db_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Log with id {log_id} not found"
        )

    db_log.name = updated_log.name
    db_log.password = updated_log.password
    db.commit()
    db.refresh(db_log)
    return db_log




@app.delete("/logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_log(log_id: int, db: Session = Depends(get_db)):
    db_log = db.query(LogDB).filter(LogDB.id == log_id).first()
    if not db_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Log with id {log_id} not found"
        )
    db.delete(db_log)
    db.commit()
    return None




if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
