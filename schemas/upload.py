from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional, Dict, Any

class FileMetadata(BaseModel):
    """Metadata for uploaded CSV file"""
    file_id: str
    filename: str
    size_bytes: int = Field(..., description="File size in bytes")
    columns: List[str] = Field(..., description="List of column names")
    rows: int = Field(..., description="Number of rows")
    upload_time: datetime
    status: str = Field(..., description="processing/completed/failed")
    processed_path: Optional[str] = None
    profile: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }

class UploadResponse(BaseModel):
    """Response model for upload endpoint"""
    success: bool
    message: str
    file_id: str
    metadata: FileMetadata