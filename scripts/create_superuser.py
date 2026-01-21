import sys
import os
from pathlib import Path

# Add the parent directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.services.user_service import UserService
from app.schemas.user import UserCreate
from app.core.config import settings


def create_initial_superuser():
    db = SessionLocal()
    
    try:
        # Check if superuser already exists
        user = UserService.get_by_email(db, settings.FIRST_SUPERUSER_EMAIL)
        if user:
            print(f"Superuser {settings.FIRST_SUPERUSER_EMAIL} already exists")
            return
        
        # Create superuser
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER_EMAIL,
            username="admin",
            full_name="Admin User",
            password=settings.FIRST_SUPERUSER_PASSWORD,
        )
        
        user = UserService.create(db, user_in)
        user.is_superuser = True
        db.commit()
        db.refresh(user)
        
        print(f"Superuser {settings.FIRST_SUPERUSER_EMAIL} created successfully")
        
    except Exception as e:
        print(f"Error creating superuser: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    create_initial_superuser()