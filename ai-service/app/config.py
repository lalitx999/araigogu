from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    # Required: shared secret that the Django web app sends in X-Internal-Token.
    ai_internal_token: str
    request_timeout: float = 25.0
    max_concurrency: int = 8  # simultaneous OpenAI calls


@lru_cache
def get_settings() -> Settings:
    return Settings()
