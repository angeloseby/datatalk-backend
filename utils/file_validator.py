from io import BytesIO
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import Header, HTTPException, UploadFile

from config.settings import settings

SupportedFileType = Literal["csv", "xlsx"]

CSV_MIME_TYPES = {
    "text/csv",
    "application/csv",
    "text/plain",
    "application/vnd.ms-excel",
}
XLSX_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}


def _max_file_size_bytes() -> int:
    return settings.files.max_file_size_bytes


def _normalize_mime(content_type: str | None) -> str:
    if not content_type:
        return ""
    return content_type.split(";", 1)[0].strip().lower()


def detect_supported_file_type(filename: str, content_type: str | None = None) -> SupportedFileType:
    suffix = Path(filename or "").suffix.lower()
    normalized_mime = _normalize_mime(content_type)

    if suffix == ".csv":
        if normalized_mime and normalized_mime not in CSV_MIME_TYPES and normalized_mime != "application/octet-stream":
            raise HTTPException(status_code=400, detail="Invalid CSV MIME type")
        return "csv"

    if suffix == ".xlsx":
        if normalized_mime and normalized_mime not in XLSX_MIME_TYPES and normalized_mime != "application/octet-stream":
            raise HTTPException(status_code=400, detail="Invalid XLSX MIME type")
        return "xlsx"

    raise HTTPException(status_code=400, detail="Invalid file type. Only CSV and XLSX files are allowed")


def read_tabular_data(file_bytes: bytes, file_type: SupportedFileType, nrows: int | None = None) -> pd.DataFrame:
    try:
        if file_type == "csv":
            return pd.read_csv(BytesIO(file_bytes), nrows=nrows)

        # XLSX files are parsed with openpyxl.
        return pd.read_excel(BytesIO(file_bytes), nrows=nrows, engine="openpyxl")
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="Excel support requires the 'openpyxl' package") from exc
    except pd.errors.EmptyDataError as exc:
        raise HTTPException(status_code=400, detail="Uploaded file appears to be empty") from exc
    except pd.errors.ParserError as exc:
        raise HTTPException(status_code=400, detail="Invalid tabular file format") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unable to parse uploaded file: {str(exc)}") from exc


async def valid_content_length(content_length: int | None = Header(default=None)):
    """
    Validate Content-Length before reading request body.
    """
    if content_length is None:
        return None
    if content_length > _max_file_size_bytes():
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size is {settings.files.max_file_size}MB.",
        )
    return content_length


async def validate_tabular_upload(
    file: UploadFile,
    preview_rows: int = 5,
) -> tuple[bytes, SupportedFileType, pd.DataFrame]:
    file_bytes = await file.read()

    if len(file_bytes) > _max_file_size_bytes():
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size is {settings.files.max_file_size}MB.",
        )

    file_type = detect_supported_file_type(file.filename or "", file.content_type)
    preview_df = read_tabular_data(file_bytes, file_type, nrows=preview_rows)

    if len(preview_df.columns) < 1:
        raise HTTPException(status_code=400, detail="Uploaded file has no columns")
    if preview_df.empty:
        raise HTTPException(status_code=400, detail="Uploaded file has no data rows")

    return file_bytes, file_type, preview_df
