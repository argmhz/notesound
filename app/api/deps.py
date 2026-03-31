from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.repositories.jobs import JobRepository


def get_job_repository(db: Session = Depends(get_db)) -> JobRepository:
    return JobRepository(db)

