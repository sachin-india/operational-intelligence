from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.config import POSTGRES_DSN
from core.governance.models import Base

engine = create_engine(POSTGRES_DSN, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def create_tables() -> None:
    """Create all governance tables if they do not already exist.

    Safe to call repeatedly — uses CREATE TABLE IF NOT EXISTS semantics.
    Call this once at application startup before any governed actions run.
    """
    Base.metadata.create_all(engine)
