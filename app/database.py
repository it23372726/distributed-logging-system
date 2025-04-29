# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

# Correct Database URL
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:docker@localhost:5432/distributed_logging_db"

# Create engine
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all models
Base = declarative_base()


def create_tables():
    Base.metadata.create_all(bind=engine)

# This will only run when this file is executed directly, not when imported
if __name__ == "__main__":
    create_tables()
