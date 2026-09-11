from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    osrm_url: str = "https://router.project-osrm.org"
    osm_user_agent: str = "RoamlyApp/1.0 (roamly-app-dev@outlook.com)"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/roamly"
    cors_origins: str = "http://localhost:5173"
    ai_provider: str = "heuristic"
    ai_fallback_provider: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o"
    openrouter_app_url: str = "http://localhost:5173"
    openrouter_app_name: str = "Roamly"
    embedding_provider: str = "gemini"
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 1536
    weather_provider: str = "open_meteo"
    model_config = SettingsConfigDict(env_file=(".env", "backend/.env"), extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
