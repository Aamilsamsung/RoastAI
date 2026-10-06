from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    environment: Literal["development", "production", "test"] = "development"
    database_url: str = "sqlite:///./roastbot.db"
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = ""
    admin_token: str = ""
    google_client_id: str = ""
    facebook_page_access_token: str = ""
    facebook_page_id: str = ""
    facebook_api_version: str = "v23.0"
    snapchat_access_token: str = ""
    snapchat_profile_id: str = ""
    instagram_api_version: str = "v23.0"
    instagram_login_type: Literal["instagram", "facebook"] = "instagram"
    ai_timeout_seconds: int = Field(30,ge=1,le=120)
    rate_limit_per_minute: int = Field(20,ge=1,le=1000)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    ai_provider: Literal["gemini", "ollama"] = "gemini"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma4:4b"
    bot_enabled: bool = False
    dry_run: bool = True
    roast_mode: str = "savage"
    roast_intensity: int = 7
    profanity_level: str = "light"
    custom_instructions: str = ""
    reply_delay_seconds: float = 1
    cooldown_seconds: int = 10
    max_reply_length: int = 300
    input_language: str = "auto"
    reply_language: str = "same"
    script_mode: str = "roman"
    meta_verify_token: str = ""
    meta_app_secret: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_api_version: str = "v23.0"
    instagram_access_token: str = ""
    instagram_account_id: str = ""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
