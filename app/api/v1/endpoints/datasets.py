from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import asyncio

from app.api.deps import get_db, get_current_user
from app.models import User, Dataset
from app.schemas.dataset import (
    DatasetCreate, DatasetCreateResponse, DatasetResponse, 
    DatasetUpdate, DatasetListResponse, FileUploadRequest
)
from app.services.dataset_service import DatasetService

router = APIRouter()


@router.post("/upload", response_model=DatasetCreateResponse)
async def upload_dataset(
    file: UploadFile = File(...),
    dataset_data: str = Query(...),  # JSON string of DatasetCreate
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a dataset file (CSV, Excel, etc.)
    """
    # Parse dataset data
    import json
    try:
        dataset_dict = json.loads(dataset_data)
        dataset_create = DatasetCreate(**dataset_dict)
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid dataset data: {str(e)}"
        )
    
    try:
        # Create dataset
        dataset = DatasetService.create(db, current_user, file, dataset_create)
        
        # Process dataset asynchronously
        asyncio.create_task(
            process_dataset_async(db, dataset.id)
        )
        
        return dataset
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading file: {str(e)}"
        )


async def process_dataset_async(db: Session, dataset_id: int):
    """Async task to process dataset"""
    # We need to create a new session for async operation
    from app.core.database import SessionLocal
    async_db = SessionLocal()
    
    try:
        DatasetService.process_dataset(async_db, dataset_id)
    except Exception as e:
        print(f"Error processing dataset {dataset_id}: {str(e)}")
    finally:
        async_db.close()


@router.get("/", response_model=DatasetListResponse)
def list_datasets(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """
    List all datasets for current user
    """
    datasets = DatasetService.get_user_datasets(
        db, current_user.id, skip, limit, search
    )
    total = DatasetService.count_user_datasets(db, current_user.id, search)
    
    return DatasetListResponse(
        datasets=datasets,
        total=total,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        total_pages=(total + limit - 1) // limit if limit > 0 else 1
    )


@router.get("/{dataset_id}", response_model=DatasetResponse)
def get_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get dataset by ID
    """
    dataset = DatasetService.get_by_id(db, dataset_id)
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    if dataset.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    return dataset


@router.put("/{dataset_id}", response_model=DatasetResponse)
def update_dataset(
    dataset_id: int,
    dataset_update: DatasetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update dataset metadata
    """
    # Check ownership
    dataset = DatasetService.get_by_id(db, dataset_id)
    if not dataset or dataset.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    updated = DatasetService.update(db, dataset_id, dataset_update)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    return updated


@router.delete("/{dataset_id}")
def delete_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete dataset
    """
    success = DatasetService.delete(db, dataset_id, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    return {"message": "Dataset deleted successfully"}


@router.post("/{dataset_id}/reprocess")
def reprocess_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Reprocess dataset (re-analyze file)
    """
    dataset = DatasetService.get_by_id(db, dataset_id)
    if not dataset or dataset.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found"
        )
    
    try:
        DatasetService.process_dataset(db, dataset_id)
        return {"message": "Dataset reprocessing started"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reprocessing dataset: {str(e)}"
        )