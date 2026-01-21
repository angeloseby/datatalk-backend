from pydantic import BaseModel, ConfigDict, Field, validator
from typing import Optional, Any, List, Dict
from datetime import datetime
from enum import Enum


# Enums
class FileType(str, Enum):
    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"


class QueryStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# Base schemas
class DatasetBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


# Create schemas
class DatasetCreate(DatasetBase):
    pass


class DatasetCreateResponse(DatasetBase):
    id: int
    filename: str
    file_size: int
    is_processed: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Update schemas
class DatasetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


# Response schemas
class ColumnInfo(BaseModel):
    name: str
    dtype: str
    nullable: bool
    unique_values: Optional[int] = None


class DatasetResponse(DatasetBase):
    id: int
    filename: str
    original_filename: str
    file_size: int
    file_type: str
    row_count: int
    column_count: int
    columns_info: Optional[List[ColumnInfo]] = None
    sample_data: Optional[List[Dict]] = None
    is_processed: bool
    processing_error: Optional[str] = None
    owner_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


# File upload schemas
class FileUploadRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


# List response
class DatasetListResponse(BaseModel):
    datasets: List[DatasetResponse]
    total: int
    page: int
    page_size: int
    total_pages: int