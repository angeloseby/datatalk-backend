from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field
from fastapi import HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

from config.settings import settings

# Define clear states for the frontend to react to
class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

# Define the structure of a single job's status
class JobData(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.PENDING
    progress: int = 0  # 0 to 100 percentage
    message: str = "Initialized"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    result: Optional[Dict[str, Any]] = None  # To store final data/profile
    error: Optional[str] = None

class StatusTracker:
    _instance = None
    
    def __init__(self):
        self._redis: Redis | None = None

    def _key(self, job_id: str) -> str:
        return f"{settings.redis.job_key_prefix}{job_id}"

    def _get_client(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(
                settings.redis.url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=settings.redis.socket_connect_timeout,
                socket_timeout=settings.redis.socket_timeout,
            )
        return self._redis

    def _redis_unavailable(self) -> HTTPException:
        return HTTPException(
            status_code=503,
            detail="Status store unavailable. Please try again shortly.",
        )

    async def _write_job(self, job: JobData) -> None:
        try:
            await self._get_client().set(
                self._key(job.job_id),
                job.model_dump_json(),
                ex=settings.redis.job_ttl_seconds,
            )
        except (RedisTimeoutError, RedisConnectionError, RedisError):
            raise self._redis_unavailable()

    async def _read_job(self, job_id: str) -> Optional[JobData]:
        try:
            raw_value = await self._get_client().get(self._key(job_id))
        except (RedisTimeoutError, RedisConnectionError, RedisError):
            raise self._redis_unavailable()

        if not raw_value:
            return None

        return JobData.model_validate_json(raw_value)

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def create_job(self, job_id: str) -> JobData:
        """Initialize a new job tracker"""
        job = JobData(job_id=job_id)
        await self._write_job(job)
        return job

    async def update_status(self, job_id: str, status: JobStatus, message: str = None, progress: int = None):
        """Update the state of a job"""
        job = await self._read_job(job_id)
        if not job:
            return

        job.status = status
        job.updated_at = datetime.utcnow()

        if message:
            job.message = message
        if progress is not None:
            job.progress = progress

        await self._write_job(job)

    async def set_result(self, job_id: str, result: Dict[str, Any]):
        """Store the final result (e.g., pandas profile summary)"""
        job = await self._read_job(job_id)
        if not job:
            return

        job.result = result
        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.message = "Processing complete"
        job.updated_at = datetime.utcnow()
        await self._write_job(job)

    async def set_error(self, job_id: str, error_message: str):
        """Mark job as failed"""
        job = await self._read_job(job_id)
        if not job:
            return

        job.error = error_message
        job.status = JobStatus.FAILED
        job.message = "Processing failed"
        job.updated_at = datetime.utcnow()
        await self._write_job(job)

    async def get_status(self, job_id: str) -> Optional[JobData]:
        """Get current status for polling"""
        return await self._read_job(job_id)

    async def list_active_jobs(self) -> List[JobData]:
        """List all jobs (for admin/debug)"""
        try:
            keys = []
            async for key in self._get_client().scan_iter(match=f"{settings.redis.job_key_prefix}*"):
                keys.append(key)

            if not keys:
                return []

            values = await self._get_client().mget(keys)
        except (RedisTimeoutError, RedisConnectionError, RedisError):
            raise self._redis_unavailable()

        jobs: List[JobData] = []
        for raw_value in values:
            if raw_value:
                jobs.append(JobData.model_validate_json(raw_value))
        return jobs

# Global instance
tracker = StatusTracker.get_instance()
