from .database import Base
from sqlalchemy import Column, String

class LogDB(Base):
    __tablename__ = "logs"
    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    password = Column(String)