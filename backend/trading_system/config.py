from functools import lru_cache
import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_path(name: str) -> str:
    if os.getenv("VERCEL"):
        return f"/tmp/high-risk-paper-trader/{name}"
    return f"data/{name}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.local", env_file_encoding="utf-8", extra="ignore")

    onboarding_completed: bool = False
    player_persona: Literal["beginner", "player", "expert"] = "beginner"
    risk_level: Literal["conservative", "balanced", "aggressive"] = "conservative"
    allow_options: bool = False
    watch_only_mode: bool = True
    paper_initial_cash: float = Field(default=500.0, ge=1)
    live_min_forward_weeks: int = Field(default=4, ge=1)
    max_single_trade_loss_pct: float = Field(default=50.0, ge=1, le=100)
    max_daily_loss_pct: float = Field(default=20.0, ge=1, le=100)
    max_weekly_loss_pct: float = Field(default=35.0, ge=1, le=100)
    max_position_pct: float = Field(default=82.0, ge=1, le=100)
    max_order_slippage_pct: float = Field(default=15.0, ge=0.1, le=50)
    max_market_data_age_days: int = Field(default=7, ge=0)
    review_weekday: Literal["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"] = "FRI"
    review_hour_local: int = Field(default=17, ge=0, le=23)
    local_timezone: str = "America/Chicago"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    alpaca_paper_api_key: str | None = None
    alpaca_paper_secret_key: str | None = None
    alpaca_paper_base_url: str = "https://paper-api.alpaca.markets"
    massive_api_key: str | None = None
    finnhub_api_key: str | None = None
    benzinga_api_key: str | None = None
    fmp_api_key: str | None = None
    google_translate_api_key: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    coinbase_api_key_name: str | None = None
    coinbase_api_private_key: str | None = None

    database_path: str = Field(default_factory=lambda: _default_data_path("trading.duckdb"))
    report_dir: str = Field(default_factory=lambda: _default_data_path("reports"))

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def settings_from_env(env_path: Path, database_path: Path, report_dir: Path | None = None) -> Settings:
    return Settings(_env_file=env_path, database_path=str(database_path), report_dir=str(report_dir or database_path.parent / "reports"))
