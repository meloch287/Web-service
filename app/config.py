from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    db_user: str = "vtsk"
    db_password: str = "1234"
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "vtsk_db"
    sender_host: str = "0.0.0.0"
    sender_port: int = 5000
    receiver_host: str = "0.0.0.0"
    receiver_port: int = 5001
    receiver_url: str = "http://192.168.20.2:5001"
    sender_callback_url: str = "http://192.168.10.2:5000"
    max_workers: int = 100
    request_timeout: float = 30.0
    
    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    return Settings()
