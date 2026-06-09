from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost:5432/aisec"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "meetings"
    whisperx_model: str = "base"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    class Config:
        env_file = ".env"


settings = Settings()
