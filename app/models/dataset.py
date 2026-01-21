from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # File information
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)  # in bytes
    file_type = Column(String(10), nullable=False)  # csv, xlsx, etc.
    
    # Data information
    row_count = Column(Integer, default=0)
    column_count = Column(Integer, default=0)
    columns_info = Column(JSON, nullable=True)  # Store column names and types
    sample_data = Column(JSON, nullable=True)  # First few rows for preview
    
    # User relation
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Processing status
    is_processed = Column(Boolean, default=False)
    processing_error = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    owner = relationship("User", back_populates="datasets")
    queries = relationship("Query", back_populates="dataset", cascade="all, delete-orphan")


class Query(Base):
    __tablename__ = "queries"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Query information
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    query_type = Column(String(50), nullable=True)  # analysis, visualization, etc.
    
    # AI response metadata
    sql_generated = Column(Text, nullable=True)
    visualization_data = Column(JSON, nullable=True)
    confidence_score = Column(Integer, nullable=True)
    
    # Processing status
    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    dataset = relationship("Dataset", back_populates="queries")
    user = relationship("User", back_populates="queries")