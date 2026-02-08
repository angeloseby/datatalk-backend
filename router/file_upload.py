from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks
import pandas as pd
import uuid
import os
from datetime import datetime
from typing import Dict, Any

from core.file_manager import save_upload_file_securely
from utils.file_validator import valid_content_length, validate_csv_file
from core.data_processor import DataProcessor
from schemas.upload import UploadResponse, FileMetadata
from config.settings import get_settings

router = APIRouter(prefix="/upload", tags=["upload"])
settings = get_settings()

# In-memory storage for demo (replace with DB in production)
uploaded_files: Dict[str, Dict[str, Any]] = {}

@router.post("/csv", response_model=UploadResponse)
async def upload_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    file_size_header: int = Depends(valid_content_length)
):
    """
    Upload a CSV file for analysis
    
    - **file**: CSV file to upload
    - Returns: Upload metadata and file ID for future queries
    """
    file_id = str(uuid.uuid4())
    
    # Setup paths
    temp_dir = Path("storage/temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    file_path = temp_dir / f"{file_id}_{file.filename}"

    # 2. Step 2: Stream Save & Verify Size (Secure Reject)
    # We do NOT use 'await file.read()' here. We let the helper handle chunks.
    real_file_size = await save_upload_file_securely(file, file_path)

    # 3. Step 3: Validate CSV Content (Post-Save)
    # Now that file is safely on disk, we let Pandas read it from there.
    # This is much faster than reading from memory buffers.
    try:
        # Read only the first few rows to validate format (efficient)
        df_preview = pd.read_csv(file_path, nrows=5)
        
        if len(df_preview.columns) < 1:
            raise ValueError("CSV has no columns")
            
    except Exception as e:
        # If invalid CSV, delete the file and error out
        os.remove(file_path)
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {str(e)}")

    # 4. Success - Queue Background Task
    # Note: We don't pass 'df' anymore because that's heavy. 
    # We pass the file_path. Let the worker load the full DF.
    background_tasks.add_task(
        process_uploaded_file,
        file_id=file_id,
        file_path=str(file_path),
        original_filename=file.filename
    )
    
    return UploadResponse(
        success=True,
        message="File uploaded successfully. Processing started.",
        file_id=file_id,
    )

@router.get("/status/{file_id}")
async def get_upload_status(file_id: str):
    """
    Check the processing status of an uploaded file
    """
    if file_id not in uploaded_files:
        raise HTTPException(status_code=404, detail="File not found")
    
    return uploaded_files[file_id]["metadata"]

async def process_uploaded_file(
    file_id: str,
    file_path: str,
    df: pd.DataFrame,
    original_filename: str
):
    """
    Background task to process uploaded CSV file
    """
    try:
        processor = DataProcessor()
        
        # 1. Clean and validate data
        cleaned_df = processor.clean_data(df)
        
        # 2. Generate data profile
        profile = processor.generate_profile(cleaned_df)
        
        # 3. Save processed data
        processed_path = f"storage/processed/{file_id}.parquet"
        cleaned_df.to_parquet(processed_path)
        
        # 4. Update metadata
        uploaded_files[file_id]["df"] = cleaned_df
        uploaded_files[file_id]["profiling"] = profile
        uploaded_files[file_id]["metadata"]["status"] = "completed"
        uploaded_files[file_id]["metadata"]["processed_path"] = processed_path
        uploaded_files[file_id]["metadata"]["profile"] = profile
        
        # 5. Cleanup temp file
        os.remove(file_path)
        
    except Exception as e:
        uploaded_files[file_id]["metadata"]["status"] = "failed"
        uploaded_files[file_id]["metadata"]["error"] = str(e)