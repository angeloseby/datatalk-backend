import pandas as pd
import numpy as np
from typing import Dict, Any, List
import json

class DataProcessor:
    """Handle CSV data processing and profiling"""
    
    def clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean the uploaded CSV data
        """
        # Make a copy
        cleaned_df = df.copy()
        
        # Remove duplicate rows
        cleaned_df = cleaned_df.drop_duplicates()
        
        # Strip whitespace from string columns
        string_columns = cleaned_df.select_dtypes(include=['object']).columns
        for col in string_columns:
            cleaned_df[col] = cleaned_df[col].str.strip()
        
        # Convert date columns if possible
        for col in cleaned_df.columns:
            if cleaned_df[col].dtype == 'object':
                try:
                    cleaned_df[col] = pd.to_datetime(cleaned_df[col])
                except (ValueError, TypeError):
                    pass
        
        return cleaned_df
    
    def generate_profile(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Generate comprehensive data profile
        """
        # FIX 1: Wrap numpy sums in int()
        profile = {
            "summary": {
                "total_rows": int(len(df)),
                "total_columns": int(len(df.columns)),
                "memory_usage": int(df.memory_usage(deep=True).sum()),
                "duplicate_rows": int(df.duplicated().sum())
            },
            "columns": {},
            "missing_values": {},
            "statistics": {}
        }
        
        for column in df.columns:
            col_data = df[column]
            dtype = str(col_data.dtype)
            
            # FIX 2: Wrap isnull().sum() and nunique() in int()
            column_info = {
                "dtype": dtype,
                "total": int(len(col_data)),
                "missing": int(col_data.isnull().sum()),
                "missing_percentage": round((float(col_data.isnull().sum()) / len(col_data)) * 100, 2),
                "unique": int(col_data.nunique())
            }
            
            # Numerical columns
            if pd.api.types.is_numeric_dtype(col_data):
                column_info.update({
                    "mean": float(col_data.mean()) if not col_data.isnull().all() else None,
                    "std": float(col_data.std()) if not col_data.isnull().all() else None,
                    "min": float(col_data.min()) if not col_data.isnull().all() else None,
                    "max": float(col_data.max()) if not col_data.isnull().all() else None,
                    "percentiles": {
                        "25": float(col_data.quantile(0.25)) if not col_data.isnull().all() else None,
                        "50": float(col_data.quantile(0.50)) if not col_data.isnull().all() else None,
                        "75": float(col_data.quantile(0.75)) if not col_data.isnull().all() else None
                    }
                })
            
            # Categorical/string columns
            elif pd.api.types.is_string_dtype(col_data) or pd.api.types.is_categorical_dtype(col_data):
                top_values = col_data.value_counts().head(5).to_dict()
                column_info.update({
                    # FIX 3: Ensure keys and values are standard types
                    "top_values": {str(k): int(v) for k, v in top_values.items()}
                })
            
            # Datetime columns
            elif pd.api.types.is_datetime64_any_dtype(col_data):
                column_info.update({
                    "min_date": col_data.min().isoformat() if not col_data.isnull().all() else None,
                    "max_date": col_data.max().isoformat() if not col_data.isnull().all() else None
                })
            
            profile["columns"][column] = column_info
            profile["missing_values"][column] = column_info["missing"]
        
        return profile