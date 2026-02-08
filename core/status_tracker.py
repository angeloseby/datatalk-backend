import asyncio
from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime
from pydantic import BaseModel

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
    created_at: datetime = datetime.utcnow()
    updated_at: datetime = datetime.utcnow()
    result: Optional[Dict[str, Any]] = None  # To store final data/profile
    error: Optional[str] = None

class StatusTracker:
    _instance = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        # In-memory storage. In production, replace this with Redis.
        self._jobs: Dict[str, JobData] = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def create_job(self, job_id: str) -> JobData:
        """Initialize a new job tracker"""
        async with self._lock:
            job = JobData(job_id=job_id)
            self._jobs[job_id] = job
            return job

    async def update_status(self, job_id: str, status: JobStatus, message: str = None, progress: int = None):
        """Update the state of a job"""
        async with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                job.status = status
                job.updated_at = datetime.utcnow()
                
                if message:
                    job.message = message
                if progress is not None:
                    job.progress = progress
                
                # Auto-cleanup logic could go here (e.g., remove jobs older than 1 hour)

    async def set_result(self, job_id: str, result: Dict[str, Any]):
        """Store the final result (e.g., pandas profile summary)"""
        async with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                job.result = result
                job.status = JobStatus.COMPLETED
                job.progress = 100
                job.message = "Processing complete"
                job.updated_at = datetime.utcnow()

    async def set_error(self, job_id: str, error_message: str):
        """Mark job as failed"""
        async with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                job.error = error_message
                job.status = JobStatus.FAILED
                job.message = "Processing failed"
                job.updated_at = datetime.utcnow()

    async def get_status(self, job_id: str) -> Optional[JobData]:
        """Get current status for polling"""
        async with self._lock:
            return self._jobs.get(job_id)

    async def list_active_jobs(self) -> List[JobData]:
        """List all jobs (for admin/debug)"""
        async with self._lock:
            return list(self._jobs.values())

# Global instance
tracker = StatusTracker.get_instance()