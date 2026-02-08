from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks
import pandas as pd
import uuid
import os
from datetime import datetime
from typing import Dict, Any

# --- IMPORTS FOR SECURE UPLOAD ---
from core.file_manager import save_upload_file_securely
from utils.file_validator import valid_content_length, validate_csv_file
from core.data_processor import DataProcessor
from schemas.upload import UploadResponse, FileMetadata
from config.settings import get_settings

# --- IMPORT STATUS TRACKER ---
from core.status_tracker import tracker, JobStatus

router = APIRouter(prefix="/upload", tags=["upload"])
settings = get_settings()

# REMOVED: uploaded_files = {}  <-- We don't need this memory dict anymore

@router.post("/csv", response_model=UploadResponse)
async def upload_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    file_size_header: int = Depends(valid_content_length) # Validates size before upload
):
    """
    Upload a CSV file for analysis.
    Uses 'Stream Saving' to prevent memory crashes.
    """
    file_id = str(uuid.uuid4())
    
    # 1. Initialize the Status Tracker immediately
    await tracker.create_job(file_id)

    # Setup paths
    temp_dir = Path("storage/temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    file_path = temp_dir / f"{file_id}_{file.filename}"

    try:
        # 2. Secure Stream Save (Writes to disk in chunks)
        real_file_size = await save_upload_file_securely(file, file_path)

        # 3. Quick Validation (Read first 5 rows only)
        # We read from DISK now, not memory
        df_preview = pd.read_csv(file_path, nrows=5)
        
        if len(df_preview.columns) < 1:
            raise ValueError("CSV has no columns")

    except Exception as e:
        # If upload/validation fails, mark job as failed and clean up
        if file_path.exists():
            os.remove(file_path)
        await tracker.set_error(file_id, str(e))
        raise HTTPException(status_code=400, detail=f"Upload failed: {str(e)}")

    # 4. Queue Background Processing
    background_tasks.add_task(
        process_uploaded_file,
        file_id=file_id,
        file_path=str(file_path),
        original_filename=file.filename
    )
    
    # 5. Return Initial Response
    # Note: We fetch the fresh job status from the tracker
    job = await tracker.get_status(file_id)
    
    return UploadResponse(
        success=True,
        message="File uploaded successfully. Processing started.",
        file_id=file_id,
        # We map the JobData to your FileMetadata schema
        metadata=FileMetadata(
            file_id=file_id,
            filename=file.filename,
            size_bytes=real_file_size,
            columns=list(df_preview.columns),
            rows=0, # Unknown yet, will be updated in background
            upload_time=job.created_at,
            status=job.status
        )
    )

@router.get("/status/{file_id}")
async def get_upload_status(file_id: str):
    """
    Check the processing status of an uploaded file via the Tracker
    """
    job = await tracker.get_status(file_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="File processing job not found")
    
    return job

async def process_uploaded_file(
    file_id: str,
    file_path: str,
    original_filename: str
):
    """
    Background task that updates the StatusTracker at every step
    """
    try:
        processor = DataProcessor()
        
        # UPDATE STATUS: Loading
        await tracker.update_status(file_id, JobStatus.PROCESSING, "Loading data...", 10)
        
        # Load full dataframe
        df = pd.read_csv(file_path)
        
        # UPDATE STATUS: Cleaning
        await tracker.update_status(file_id, JobStatus.PROCESSING, "Cleaning data...", 30)
        cleaned_df = processor.clean_data(df)
        
        # UPDATE STATUS: Profiling
        await tracker.update_status(file_id, JobStatus.PROCESSING, "Generating profile...", 60)
        profile = processor.generate_profile(cleaned_df)
        
        # Save processed data
        await tracker.update_status(file_id, JobStatus.PROCESSING, "Saving results...", 90)
        
        os.makedirs("storage/processed", exist_ok=True)
        processed_path = f"storage/processed/{file_id}.parquet"
        cleaned_df.to_parquet(processed_path)
        
        # FINAL SUCCESS: Store the result in the tracker
        result_data = {
            "processed_path": processed_path,
            "profile": profile,
            "columns": list(cleaned_df.columns),
            "rows": len(cleaned_df)
        }
        await tracker.set_result(file_id, result_data)
        
        # Cleanup temp file
        if os.path.exists(file_path):
            os.remove(file_path)
        
    except Exception as e:
        # FINAL FAILURE: Report error to tracker
        await tracker.set_error(file_id, str(e))
        if os.path.exists(file_path):
            os.remove(file_path)