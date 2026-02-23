from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    TELEGRAM_BOT_TOKEN: str

    # Supabase
    SUPABASE_URL: str
    SUPABASE_KEY: str

    # OpenRouter
    OPENROUTER_API_KEY: str
    LLM_MODEL: str = "google/gemini-2.5-flash"
    VISION_LLM_MODEL: str = "google/gemini-2.5-flash"

    # proverkacheka
    PROVERKACHEKA_TOKEN: str

    model_config = {"env_file": ".env"}


settings = Settings()
