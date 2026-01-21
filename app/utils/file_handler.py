import os
import uuid
import shutil
from typing import Tuple, Dict, List, Any
from fastapi import UploadFile, HTTPException
from pathlib import Path
import pandas as pd
import numpy as np
import json
from datetime import datetime
from app.core.config import settings


class FileHandler:
    def __init__(self):
        self.upload_dir = Path(settings.UPLOAD_DIR)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Allowed file types and their extensions
        self.allowed_extensions = {
            '.csv': 'csv',
            '.xlsx': 'excel',
            '.xls': 'excel',
            '.json': 'json',
            '.parquet': 'parquet'
        }
        
        # Max file size in bytes
        self.max_file_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    
    def validate_file(self, file: UploadFile) -> Tuple[bool, str]:
        """Validate uploaded file"""
        # Check file extension
        file_extension = Path(file.filename).suffix.lower()
        if file_extension not in self.allowed_extensions:
            allowed = ', '.join(self.allowed_extensions.keys())
            return False, f"File type not allowed. Allowed types: {allowed}"
        
        # Check file size
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()
        file.file.seek(0)  # Reset pointer
        
        if file_size > self.max_file_size:
            return False, f"File size exceeds {settings.MAX_FILE_SIZE_MB}MB limit"
        
        if file_size == 0:
            return False, "File is empty"
        
        return True, ""
    
    def save_file(self, file: UploadFile) -> Tuple[str, str]:
        """Save uploaded file and return path and unique filename"""
        # Generate unique filename
        original_filename = file.filename
        file_extension = Path(original_filename).suffix.lower()
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        
        # Save file
        file_path = self.upload_dir / unique_filename
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        return str(file_path), unique_filename
    
    def read_file(self, file_path: str, file_type: str) -> pd.DataFrame:
        """Read file into pandas DataFrame"""
        try:
            if file_type == 'csv':
                # Try different encodings
                encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
                for encoding in encodings:
                    try:
                        return pd.read_csv(file_path, encoding=encoding)
                    except UnicodeDecodeError:
                        continue
                # If all encodings fail, try without specifying encoding
                return pd.read_csv(file_path)
            
            elif file_type == 'excel':
                return pd.read_excel(file_path)
            
            elif file_type == 'json':
                return pd.read_json(file_path)
            
            elif file_type == 'parquet':
                return pd.read_parquet(file_path)
            
            else:
                raise ValueError(f"Unsupported file type: {file_type}")
        
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Error reading file: {str(e)}"
            )
    
    def analyze_dataframe(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze dataframe and extract metadata"""
        # Basic info
        row_count = len(df)
        column_count = len(df.columns)
        
        # Column information
        columns_info = []
        for col in df.columns:
            col_info = {
                "name": col,
                "dtype": str(df[col].dtype),
                "nullable": df[col].isnull().any(),
                "unique_values": int(df[col].nunique()),
                "sample_values": df[col].dropna().head(5).tolist() if df[col].nunique() > 0 else []
            }
            columns_info.append(col_info)
        
        # Sample data (first 10 rows)
        sample_data = df.head(10).replace({np.nan: None}).to_dict(orient='records')
        
        # Basic statistics for numeric columns
        numeric_stats = {}
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            numeric_stats[col] = {
                "mean": float(df[col].mean()),
                "std": float(df[col].std()),
                "min": float(df[col].min()),
                "max": float(df[col].max()),
                "median": float(df[col].median())
            }
        
        return {
            "row_count": row_count,
            "column_count": column_count,
            "columns_info": columns_info,
            "sample_data": sample_data,
            "numeric_stats": numeric_stats,
            "data_types": {
                "numeric": len(numeric_cols),
                "categorical": len(df.select_dtypes(include=['object', 'category']).columns),
                "datetime": len(df.select_dtypes(include=['datetime']).columns),
                "boolean": len(df.select_dtypes(include=['bool']).columns)
            }
        }
    
    def clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean dataframe - handle missing values, etc."""
        # Make a copy
        df_clean = df.copy()
        
        # Fill numeric missing values with median
        numeric_cols = df_clean.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            if df_clean[col].isnull().any():
                df_clean[col] = df_clean[col].fillna(df_clean[col].median())
        
        # Fill categorical missing values with mode
        categorical_cols = df_clean.select_dtypes(include=['object', 'category']).columns
        for col in categorical_cols:
            if df_clean[col].isnull().any():
                df_clean[col] = df_clean[col].fillna(df_clean[col].mode().iloc[0] if not df_clean[col].mode().empty else "Unknown")
        
        return df_clean
    
    def delete_file(self, file_path: str) -> bool:
        """Delete file from storage"""
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                return True
            return False
        except Exception:
            return False


# Create a singleton instance
file_handler = FileHandler()