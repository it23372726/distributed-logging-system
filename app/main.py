from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime
from pathlib import Path
from typing import List
import os
from utils.ntp_sync import analyze_clock_skew

from utils.ntp_sync import sync_time
from app.models import LogDB
from app.database import Base, engine, SessionLocal
from app.time_sync_service import TimeSyncService

app = FastAPI()
sync_service = TimeSyncService()

# Dependency to get DB session
async def get_db():
    async with SessionLocal() as session:
        yield session

# Ensure tables are created on startup
@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[STARTUP] Tables created and system synced.")

# Setup templates and static directories
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

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

@app.get("/logs/", response_model=List[LogRead])
async def get_logs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LogDB).order_by(LogDB.timestamp))
    return result.scalars().all()

@app.post("/logs/", response_model=LogRead)
async def create_log(log: Log, db: AsyncSession = Depends(get_db)):
    ts = sync_time() or datetime.utcnow()
    new_log = LogDB(name=log.name, password=log.password, timestamp=ts)
    db.add(new_log)
    await db.commit()
    await db.refresh(new_log)
    return new_log

@app.put("/logs/{log_id}", response_model=LogRead)
async def update_log(log_id: int, updated_log: Log, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LogDB).filter(LogDB.id == log_id))
    db_log = result.scalars().first()
    if not db_log:
        raise HTTPException(status_code=404, detail=f"Log with id {log_id} not found")

    db_log.name = updated_log.name
    db_log.password = updated_log.password
    await db.commit()
    await db.refresh(db_log)
    return db_log

@app.delete("/logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_log(log_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LogDB).filter(LogDB.id == log_id))
    db_log = result.scalars().first()
    if not db_log:
        raise HTTPException(status_code=404, detail=f"Log with id {log_id} not found")
    await db.delete(db_log)
    await db.commit()
    return None

@app.get("/logs/check-order/")
async def check_order(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LogDB).order_by(LogDB.id))
    logs = result.scalars().all()
    timestamps = [log.timestamp for log in logs]
    if timestamps != sorted(timestamps):
        return JSONResponse(content={"warning": "\u26a0 Out-of-order logs detected!"})
    return {"status": "All logs are in order"}

@app.get("/status")
async def index():
    return {"server": os.getenv("SERVER_NAME", "unknown"), "status": "running"}

@app.get("/clock-skew/")
async def get_clock_skew():
    skew = analyze_clock_skew()
    if skew is None:
        raise HTTPException(status_code=500, detail="Failed to analyze clock skew")
    return {"skew_seconds": skew}

@app.post("/flush-delay/")
async def set_flush_delay(seconds: int):
    sync_service.update_flush_delay(seconds)
    return {"message": f"Flush delay updated to {seconds} seconds"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
