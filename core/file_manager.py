import shutil
from pathlib import Path
from fastapi import UploadFile, HTTPException
from config.settings import settings

async def save_upload_file_securely(file: UploadFile, destination: Path) -> int:
    """
    2. THE SCALE METHOD: Reads file in chunks and saves to disk.
    If size exceeds limit during upload, it stops and deletes the partial file.
    """
    file_size = 0
    MAX_SIZE = settings.files.max_file_size * 1024 * 1024  # 10MB

    try:
        with destination.open("wb") as buffer:
            while True:
                # Read in small 1MB chunks (low memory usage)
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                
                file_size += len(chunk)
                if file_size > MAX_SIZE:
                    raise HTTPException(status_code=413, detail="File too large (stopped reading)")
                
                buffer.write(chunk)
    except Exception as e:
        # If anything goes wrong, clean up the partial file
        if destination.exists():
            destination.unlink()
        raise e

    return file_size