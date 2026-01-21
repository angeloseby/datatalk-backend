from sqlalchemy.orm import Session
from typing import List, Optional
from app.models import Query, Dataset, User
from app.schemas.query import QueryCreate, QueryUpdate


class QueryService:
    @staticmethod
    def create(db: Session, user_id: int, query_data: QueryCreate) -> Query:
        """Create a new query"""
        # Check if dataset exists and belongs to user
        dataset = db.query(Dataset).filter(
            Dataset.id == query_data.dataset_id,
            Dataset.owner_id == user_id
        ).first()
        
        if not dataset:
            raise ValueError("Dataset not found or access denied")
        
        # Create query
        db_query = Query(
            dataset_id=query_data.dataset_id,
            user_id=user_id,
            question=query_data.question,
            query_type=query_data.query_type.value if query_data.query_type else None,
            status="pending"
        )
        
        db.add(db_query)
        db.commit()
        db.refresh(db_query)
        
        return db_query
    
    @staticmethod
    def get_by_id(db: Session, query_id: int) -> Optional[Query]:
        return db.query(Query).filter(Query.id == query_id).first()
    
    @staticmethod
    def get_user_queries(
        db: Session, 
        user_id: int, 
        dataset_id: Optional[int] = None,
        skip: int = 0, 
        limit: int = 100
    ) -> List[Query]:
        query = db.query(Query).filter(Query.user_id == user_id)
        
        if dataset_id:
            query = query.filter(Query.dataset_id == dataset_id)
        
        return query.order_by(Query.created_at.desc()).offset(skip).limit(limit).all()
    
    @staticmethod
    def count_user_queries(db: Session, user_id: int, dataset_id: Optional[int] = None) -> int:
        query = db.query(Query).filter(Query.user_id == user_id)
        
        if dataset_id:
            query = query.filter(Query.dataset_id == dataset_id)
        
        return query.count()
    
    @staticmethod
    def update(db: Session, query_id: int, update_data: QueryUpdate) -> Optional[Query]:
        query = QueryService.get_by_id(db, query_id)
        if not query:
            return None
        
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(query, field, value)
        
        db.commit()
        db.refresh(query)
        return query
    
    @staticmethod
    def delete(db: Session, query_id: int, user_id: int) -> bool:
        query = db.query(Query).filter(
            Query.id == query_id,
            Query.user_id == user_id
        ).first()
        
        if not query:
            return False
        
        db.delete(query)
        db.commit()
        return True