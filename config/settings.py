import os
from typing import Optional, List
from functools import lru_cache
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class DatabaseSettings(BaseModel):
    """Database related configuration"""
    host: str = "localhost"
    port: int = 5432
    name: str = "mydatabase"
    user: str = "postgres"
    password: str = ""
    pool_size: int = 20
    max_overflow: int = 10
    echo_sql: bool = False
    
    @property
    def database_url(self) -> str:
        """Construct database URL from settings"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

class FileSettings(BaseModel):
    """File upload related configuration"""
    allowed_file_types: List[str] = Field(
        default_factory=lambda: ['text/csv', 'application/vnd.ms-excel']
    )
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    
class APISettings(BaseModel):
    """API related configuration"""
    title: str = "My FastAPI Application"
    version: str = "1.0.0"
    description: str = ""
    cors_origins: List[str] = ["*"] 

class AISettings(BaseModel):
    """AI Provider configuration"""
    gemini_api_key: str = ""
    

class AppSettings(BaseSettings):
    """Main application settings"""
    # Environment
    environment: str = "development"
    
    # Nested configurations
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    api: APISettings = Field(default_factory=APISettings)    
    files: FileSettings = Field(default_factory=FileSettings)
    ai: AISettings = Field(default=AISettings)
    
    # Pydantic settings configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__", 
        case_sensitive=False, 
        extra="ignore" 
    )
    
    @property
    def is_development(self) -> bool:
        return self.environment == "development"
    
    @property
    def is_production(self) -> bool:
        return self.environment == "production"
    
    @property
    def is_testing(self) -> bool:
        return self.environment == "testing"

@lru_cache()
def get_settings() -> AppSettings:
    """
    Get cached settings instance.
    Using lru_cache ensures settings are loaded only once.
    """
    return AppSettings()

# Create a global settings instance
settings = get_settings()