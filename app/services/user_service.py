from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from typing import Optional
from app.core.security import (
    verify_password, 
    get_password_hash, 
    create_access_token,
    create_refresh_token,
    verify_token,
)
from app.models import User, RefreshToken
from app.schemas.user import UserCreate, UserUpdate
from app.core.config import settings


class UserService:
    @staticmethod
    def get_by_email(db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email).first()
    
    @staticmethod
    def get_by_username(db: Session, username: str) -> Optional[User]:
        return db.query(User).filter(User.username == username).first()
    
    @staticmethod
    def get_by_id(db: Session, user_id: int) -> Optional[User]:
        return db.query(User).filter(User.id == user_id).first()
    
    @staticmethod
    def create(db: Session, user_data: UserCreate) -> User:
        hashed_password = get_password_hash(user_data.password)
        
        db_user = User(
            email=user_data.email,
            username=user_data.username,
            full_name=user_data.full_name,
            hashed_password=hashed_password,
        )
        
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    
    @staticmethod
    def update(db: Session, user_id: int, user_data: UserUpdate) -> Optional[User]:
        db_user = UserService.get_by_id(db, user_id)
        if not db_user:
            return None
        
        update_data = user_data.model_dump(exclude_unset=True)
        
        if "password" in update_data:
            update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
        
        for field, value in update_data.items():
            setattr(db_user, field, value)
        
        db.commit()
        db.refresh(db_user)
        return db_user
    
    @staticmethod
    def authenticate(db: Session, username: str, password: str) -> Optional[User]:
        user = UserService.get_by_username(db, username)
        if not user:
            user = UserService.get_by_email(db, username)
        
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user
    
    @staticmethod
    def create_tokens(db: Session, user: User):
        access_token = create_access_token(subject=user.id)
        refresh_token = create_refresh_token(subject=user.id)
        
        # Store refresh token in database
        refresh_token_expires = datetime.utcnow() + timedelta(
            minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES
        )
        
        db_refresh_token = RefreshToken(
            user_id=user.id,
            token=refresh_token,
            expires_at=refresh_token_expires,
        )
        
        db.add(db_refresh_token)
        db.commit()
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }
    
    @staticmethod
    def verify_refresh_token(db: Session, refresh_token: str) -> Optional[User]:
        # Verify JWT
        payload = verify_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return None
        
        user_id = payload.get("sub")
        if not user_id:
            return None
        
        # Check if token exists in database and is not revoked
        db_token = db.query(RefreshToken).filter(
            RefreshToken.token == refresh_token,
            RefreshToken.is_revoked == False,
            RefreshToken.expires_at > datetime.utcnow(),
        ).first()
        
        if not db_token:
            return None
        
        # Get user
        return UserService.get_by_id(db, int(user_id))
    
    @staticmethod
    def revoke_refresh_token(db: Session, refresh_token: str) -> bool:
        db_token = db.query(RefreshToken).filter(
            RefreshToken.token == refresh_token
        ).first()
        
        if db_token:
            db_token.is_revoked = True
            db.commit()
            return True
        
        return False