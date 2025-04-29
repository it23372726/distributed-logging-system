from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

# Update this URL if needed
SQLALCHEMY_DATABASE_URL = "postgresql+asyncpg://postgres:docker@localhost:5432/distributed_logging_db"

engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=True)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()



def create_tables():
    Base.metadata.create_all(bind=engine)

# This will only run when this file is executed directly, not when imported
if __name__ == "__main__":
    create_tables()
