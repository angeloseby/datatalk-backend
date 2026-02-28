from pathlib import Path
from fastapi import UploadFile, HTTPException
from config.settings import settings

async def save_upload_file_securely(file: UploadFile, destination: Path) -> int:
    """
    2. THE SCALE METHOD: Reads file in chunks and saves to disk.
    If size exceeds limit during upload, it stops and deletes the partial file.
    """
    file_size = 0
    max_size = settings.files.max_file_size_bytes

    try:
        with destination.open("wb") as buffer:
            while True:
                # Read in small 1MB chunks (low memory usage)
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                
                file_size += len(chunk)
                if file_size > max_size:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Max size is {settings.files.max_file_size}MB."
                    )
                
                buffer.write(chunk)
    except Exception:
        # If anything goes wrong, clean up the partial file
        if destination.exists():
            destination.unlink()
        raise

    return file_size
