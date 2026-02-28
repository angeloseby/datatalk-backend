from pathlib import Path
from tempfile import gettempdir
from time import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

from config.settings import get_settings
from core.data_processor import DataProcessor
from core.status_tracker import JobStatus, tracker
from schemas.upload import FileMetadata, UploadResponse
from utils.file_validator import SupportedFileType, read_tabular_data, valid_content_length, validate_tabular_upload

router = APIRouter(prefix="/upload", tags=["upload"])
settings = get_settings()

TMP_BASE_DIR = Path(gettempdir()) / "datatalk_backend"
TMP_PROCESSED_DIR = TMP_BASE_DIR / "processed"
TMP_FILE_TTL_SECONDS = 60 * 60  # 1 hour
TMP_MAX_PROCESSED_FILES = 128


def _prepare_tmp_processed_dir() -> None:
    TMP_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def _cleanup_tmp_processed_files() -> None:
    if not TMP_PROCESSED_DIR.exists():
        return

    now = time()
    files = [file for file in TMP_PROCESSED_DIR.iterdir() if file.is_file()]

    for file_path in files:
        try:
            if (now - file_path.stat().st_mtime) > TMP_FILE_TTL_SECONDS:
                file_path.unlink(missing_ok=True)
        except OSError:
            continue

    remaining_files = sorted(
        [file for file in TMP_PROCESSED_DIR.iterdir() if file.is_file()],
        key=lambda item: item.stat().st_mtime,
    )

    while len(remaining_files) > TMP_MAX_PROCESSED_FILES:
        oldest = remaining_files.pop(0)
        try:
            oldest.unlink(missing_ok=True)
        except OSError:
            pass


@router.post("/csv", response_model=UploadResponse)
async def upload_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    _content_length: int | None = Depends(valid_content_length),
):
    """
    Upload a CSV or XLSX file for analysis.
    """
    file_id = str(uuid.uuid4())
    await tracker.create_job(file_id)

    safe_filename = Path(file.filename or "upload.csv").name

    try:
        file_bytes, file_type, df_preview = await validate_tabular_upload(file, preview_rows=5)
        real_file_size = len(file_bytes)
    except HTTPException as exc:
        await tracker.set_error(file_id, str(exc.detail))
        raise
    except Exception as exc:
        await tracker.set_error(file_id, str(exc))
        raise HTTPException(status_code=400, detail=f"Upload failed: {str(exc)}")
    finally:
        await file.close()

    background_tasks.add_task(
        process_uploaded_file,
        file_id=file_id,
        file_bytes=file_bytes,
        file_type=file_type,
        original_filename=safe_filename,
    )

    job = await tracker.get_status(file_id)

    return UploadResponse(
        success=True,
        message="File uploaded successfully. Processing started.",
        file_id=file_id,
        metadata=FileMetadata(
            file_id=file_id,
            filename=safe_filename,
            size_bytes=real_file_size,
            columns=list(df_preview.columns),
            rows=0,
            upload_time=job.created_at,
            status=job.status,
        ),
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
    file_bytes: bytes,
    file_type: SupportedFileType,
    original_filename: str,
):
    """
    Background task that updates the StatusTracker at every step.
    """
    processed_path: Path | None = None

    try:
        processor = DataProcessor()

        await tracker.update_status(file_id, JobStatus.PROCESSING, "Loading data...", 10)
        df = read_tabular_data(file_bytes, file_type=file_type)

        await tracker.update_status(file_id, JobStatus.PROCESSING, "Cleaning data...", 30)
        cleaned_df = processor.clean_data(df)

        await tracker.update_status(file_id, JobStatus.PROCESSING, "Generating profile...", 60)
        profile = processor.generate_profile(cleaned_df)

        await tracker.update_status(file_id, JobStatus.PROCESSING, "Saving results...", 90)
        _prepare_tmp_processed_dir()
        _cleanup_tmp_processed_files()
        processed_path = TMP_PROCESSED_DIR / f"{file_id}.parquet"
        cleaned_df.to_parquet(processed_path)

        result_data = {
            "processed_path": str(processed_path),
            "profile": profile,
            "columns": list(cleaned_df.columns),
            "rows": len(cleaned_df),
            "file_type": file_type,
            "filename": original_filename,
        }
        await tracker.set_result(file_id, result_data)

    except Exception as exc:
        if processed_path and processed_path.exists():
            processed_path.unlink(missing_ok=True)
        await tracker.set_error(file_id, str(exc))
