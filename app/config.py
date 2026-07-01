from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_workers: int = 2

    database_url: str = "postgresql://aisec:change-me@127.0.0.1:5432/aisec"

    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "meetings"

    whisperx_model: str = "large-v3"

    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"


settings = Settings()
