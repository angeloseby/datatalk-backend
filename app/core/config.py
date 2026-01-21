from pydantic import AnyHttpUrl, EmailStr
from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    # App Configuration
    APP_NAME: str = "Personal AI Data Analyst"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    
    # Server
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:8000",
    ]
    
    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/ai_analyst"
    # Alternative for SQLite: "sqlite:///./app.db"
    # Alternative for MySQL: "mysql://user:password@localhost:3306/ai_analyst"
    
    # Security
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # File Upload
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_FILE_TYPES: List[str] = [".csv", ".xlsx", ".xls"]
    UPLOAD_DIR: str = "uploads"
    
    # First Superuser (for initial setup)
    FIRST_SUPERUSER_EMAIL: EmailStr = "admin@datatalks.com"
    FIRST_SUPERUSER_PASSWORD: str = "admin"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()