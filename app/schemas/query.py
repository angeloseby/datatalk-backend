from pydantic import BaseModel, ConfigDict
from typing import Optional, Any, List, Dict
from datetime import datetime
from enum import Enum


class QueryType(str, Enum):
    ANALYSIS = "analysis"
    VISUALIZATION = "visualization"
    SUMMARY = "summary"
    PREDICTION = "prediction"


# Base schemas
class QueryBase(BaseModel):
    question: str
    query_type: Optional[QueryType] = QueryType.ANALYSIS


# Create schemas
class QueryCreate(QueryBase):
    dataset_id: int


class QueryCreateResponse(QueryBase):
    id: int
    dataset_id: int
    user_id: int
    status: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Update schemas (for AI response)
class QueryUpdate(BaseModel):
    answer: Optional[str] = None
    sql_generated: Optional[str] = None
    visualization_data: Optional[Dict] = None
    confidence_score: Optional[int] = None
    status: Optional[str] = None
    error_message: Optional[str] = None


# Response schemas
class QueryResponse(QueryBase):
    id: int
    dataset_id: int
    user_id: int
    answer: Optional[str] = None
    sql_generated: Optional[str] = None
    visualization_data: Optional[Dict] = None
    confidence_score: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


# For batch operations
class BatchQueryRequest(BaseModel):
    questions: List[str]
    dataset_id: int


class BatchQueryResponse(BaseModel):
    queries: List[QueryResponse]
    total: int
    successful: int
    failed: int