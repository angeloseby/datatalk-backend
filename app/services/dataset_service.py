from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from app.models import Dataset, User
from app.schemas.dataset import DatasetCreate, DatasetUpdate
from app.utils.file_handler import file_handler
import pandas as pd


class DatasetService:
    @staticmethod
    def create(
        db: Session,
        user: User,
        file: Any,  # FastAPI UploadFile
        dataset_data: DatasetCreate
    ) -> Dataset:
        """Create a new dataset from uploaded file"""
        # Validate file
        is_valid, error = file_handler.validate_file(file)
        if not is_valid:
            raise ValueError(error)
        
        # Save file
        file_path, unique_filename = file_handler.save_file(file)
        
        # Get file metadata
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        
        file_extension = file.filename.split('.')[-1].lower()
        file_type = file_handler.allowed_extensions.get(f'.{file_extension}', 'unknown')
        
        # Create dataset record
        db_dataset = Dataset(
            name=dataset_data.name,
            description=dataset_data.description,
            filename=unique_filename,
            original_filename=file.filename,
            file_path=file_path,
            file_size=file_size,
            file_type=file_type,
            owner_id=user.id,
            is_processed=False
        )
        
        db.add(db_dataset)
        db.commit()
        db.refresh(db_dataset)
        
        return db_dataset
    
    @staticmethod
    def process_dataset(db: Session, dataset_id: int) -> Dataset:
        """Process dataset: read file, analyze, and update metadata"""
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise ValueError("Dataset not found")
        
        try:
            # Read file
            df = file_handler.read_file(dataset.file_path, dataset.file_type)
            
            # Analyze data
            analysis = file_handler.analyze_dataframe(df)
            
            # Update dataset with analysis results
            dataset.row_count = analysis['row_count']
            dataset.column_count = analysis['column_count']
            dataset.columns_info = analysis['columns_info']
            dataset.sample_data = analysis['sample_data']
            dataset.is_processed = True
            dataset.processing_error = None
            
            db.commit()
            db.refresh(dataset)
            
            return dataset
            
        except Exception as e:
            dataset.is_processed = False
            dataset.processing_error = str(e)
            db.commit()
            raise
    
    @staticmethod
    def get_by_id(db: Session, dataset_id: int) -> Optional[Dataset]:
        return db.query(Dataset).filter(Dataset.id == dataset_id).first()
    
    @staticmethod
    def get_user_datasets(
        db: Session, 
        user_id: int, 
        skip: int = 0, 
        limit: int = 100,
        search: Optional[str] = None
    ) -> List[Dataset]:
        query = db.query(Dataset).filter(Dataset.owner_id == user_id)
        
        if search:
            query = query.filter(
                (Dataset.name.ilike(f"%{search}%")) |
                (Dataset.description.ilike(f"%{search}%"))
            )
        
        return query.order_by(Dataset.created_at.desc()).offset(skip).limit(limit).all()
    
    @staticmethod
    def count_user_datasets(db: Session, user_id: int, search: Optional[str] = None) -> int:
        query = db.query(Dataset).filter(Dataset.owner_id == user_id)
        
        if search:
            query = query.filter(
                (Dataset.name.ilike(f"%{search}%")) |
                (Dataset.description.ilike(f"%{search}%"))
            )
        
        return query.count()
    
    @staticmethod
    def update(db: Session, dataset_id: int, update_data: DatasetUpdate) -> Optional[Dataset]:
        dataset = DatasetService.get_by_id(db, dataset_id)
        if not dataset:
            return None
        
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(dataset, field, value)
        
        db.commit()
        db.refresh(dataset)
        return dataset
    
    @staticmethod
    def delete(db: Session, dataset_id: int, user_id: int) -> bool:
        """Delete dataset and associated file"""
        dataset = db.query(Dataset).filter(
            Dataset.id == dataset_id,
            Dataset.owner_id == user_id
        ).first()
        
        if not dataset:
            return False
        
        # Delete file from storage
        file_handler.delete_file(dataset.file_path)
        
        # Delete from database
        db.delete(dataset)
        db.commit()
        
        return True
    
    @staticmethod
    def get_dataset_data(db: Session, dataset_id: int) -> Optional[pd.DataFrame]:
        """Get dataset as pandas DataFrame"""
        dataset = DatasetService.get_by_id(db, dataset_id)
        if not dataset or not dataset.is_processed:
            return None
        
        try:
            return file_handler.read_file(dataset.file_path, dataset.file_type)
        except Exception:
            return None