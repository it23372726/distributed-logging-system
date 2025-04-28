from sqlalchemy import Column, Integer, String
from app.database import Base

class LogDB(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String)
    password = Column(String)
