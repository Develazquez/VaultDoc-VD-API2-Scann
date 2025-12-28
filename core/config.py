from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # API Settings
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    DEBUG: bool = True
    ALLOWED_ORIGINS: List[str] = ["*"]
    
    # Database Settings
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str

    NEXTCLOUD_BASE_URL: str
    NEXTCLOUD_USERNAME: str
    NEXTCLOUD_PASSWORD: str

    
    # Go API Settings
    GO_API_URL: str
    GO_API_TIMEOUT: int
    
    # File Processing Settings
    MAX_FILE_SIZE: int = 20 * 1024 * 1024  # 20MB
    ALLOWED_EXTENSIONS: List[str] = ["jpg", "jpeg", "png", "pdf"]
    TEMP_DIR: str = "/tmp/scanner"
    
    # Image Processing Settings
    MAX_IMAGE_HEIGHT: int = 1500
    SCAN_QUALITY: int = 95
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra= "ignore"

settings = Settings()