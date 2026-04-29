from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Window of Light"
    DEBUG: bool = False
    
    # Database
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "window_of_light"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    
    # Telegram (MTProto)
    TELEGRAM_API_ID: str = ""
    TELEGRAM_API_HASH: str = ""
    TELEGRAM_PHONE: str = ""
    TELEGRAM_SESSION: str = "wol_session"
    
    # Redis channels
    RAW_MESSAGES_CHANNEL: str = "raw_messages"
    PARSED_PRODUCTS_CHANNEL: str = "parsed_products"
    
    # API
    API_V1_PREFIX: str = "/api/v1"
    API_KEY_HEADER: str = "X-API-Key"
    
    # Cache TTL (seconds)
    CACHE_TTL: int = 600  # 10 minutes
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
