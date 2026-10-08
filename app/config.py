from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str | None = None
    app_name: str = "Fusion Backend"
    api_v1_prefix: str = "/api/v1"
    frontend_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-nano"
    openai_extraction_model: str = "gpt-5.4-mini"
    brevo_api_key: str | None = None
    brevo_sender_email: str | None = None
    brevo_sender_name: str = "Fusion Backend"
    jwt_secret: str | None = None
    jwt_access_token_minutes: int = 45       # refresh token handles longevity
    jwt_refresh_token_days: int = 30         # how long a refresh token lives
    portfolio_upload_max_mb: int = 100
    portfolio_batch_size: int = 250
    portfolio_email_max_mb: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
