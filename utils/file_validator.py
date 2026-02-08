from fastapi import UploadFile, HTTPException, Header
import pandas as pd
from typing import Tuple, Optional
import mimetypes
from config.settings import settings

MAX_FILE_SIZE = settings.files.max_file_size * 1024 * 1024  # Convert MB into Bytes
ALLOWED_MIME_TYPES = settings.files.allowed_file_types

async def valid_content_length(content_length: int = Header(..., lt=MAX_FILE_SIZE)):
    """
    Checks the ccontent header before accepting the body.
    FastAPI will automatically reject requests where Content-Length > Maximum File Size
    returns 422 Validation Error if too large.
    """
    return content_length

async def validate_csv_file(file: UploadFile) -> Tuple[UploadFile, pd.DataFrame]:
    """
    Validate CSV file and return file with DataFrame
    """
    # Check file size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Max size is {MAX_FILE_SIZE/1024/1024}MB")
    
    # Reset file pointer
    await file.seek(0)
    
    # Check MIME type
    mime_type, _ = mimetypes.guess_type(file.filename)
    if mime_type not in ALLOWED_MIME_TYPES and not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Invalid file type. Only CSV files are allowed")
    
    # Read CSV with pandas for validation
    try:
        df = pd.read_csv(file.file)
        await file.seek(0)  # Reset file pointer
        
        # Basic validation
        if df.empty:
            raise HTTPException(status_code=400, detail="CSV file is empty")
        
        if len(df.columns) < 1:
            raise HTTPException(status_code=400, detail="CSV file has no columns")
        
        return file, df
        
    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="CSV file appears to be empty")
    except pd.errors.ParserError:
        raise HTTPException(status_code=400, detail="Invalid CSV format")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading CSV: {str(e)}")