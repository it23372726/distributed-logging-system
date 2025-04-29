# app/models.py
from sqlalchemy import Column, Integer, String, DateTime
from app.database import Base
from datetime import datetime

class LogDB(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    password = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
