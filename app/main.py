from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import LogDB
from typing import List
from pathlib import Path
import uuid

app = FastAPI()

# Setup templates and static files
BASE_DIR = Path(__file__).parent.parent  # Go up one level to project root
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Data models
class Log(BaseModel):
    name: str
    password: str

    class Config:
        orm_mode = True

class LogCreate(Log):
    pass

class LogRead(Log):
    id: str

# Frontend route
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
    log_id = str(uuid.uuid4())
    db_log = LogDB(id=log_id, name=log.name, password=log.password)
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log

@app.delete("/logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_log(log_id: str, db: Session = Depends(get_db)):
    db_log = db.query(LogDB).filter(LogDB.id == log_id).first()
    if not db_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Log with id {log_id} not found"
        )
    db.delete(db_log)
    db.commit()
    return None

@app.put("/logs/{log_id}", response_model=LogRead)
async def update_log(log_id: str, updated_log: LogCreate, db: Session = Depends(get_db)):
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)