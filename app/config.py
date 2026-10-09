from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str | None = None
    app_name: str = "Fusion Backend"
    api_v1_prefix: str = "/api/v1"
    frontend_url: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_extraction_model: str = "gemini-3.8-flash"
    brevo_api_key: str | None = None
    brevo_sender_email: str | None = None
    brevo_sender_name: str = "Fusion Backend"
    jwt_secret: str | None = None
    jwt_access_token_minutes: int = 45       # refresh token handles longevity
    jwt_refresh_token_days: int = 30         # how long a refresh token lives
    portfolio_upload_max_mb: int = 100
    portfolio_batch_size: int = 250
    portfolio_email_max_mb: int = 10
    gemini_document_chunk_chars: int = 100_000
    insurance_per_building_deductible_kes: float = 0.0
    insurance_per_building_limit_kes: float = 1_000_000_000_000.0
    insurance_quota_share: float = 1.0
    catastrophe_excess_attachment_kes: float = 0.0
    catastrophe_excess_limit_kes: float = 1_000_000_000_000.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
