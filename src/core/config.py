"""Configuration management for Grocery Manager."""

from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from pydantic_settings import BaseSettings
import yaml


class DatabaseConfig(BaseModel):
    url: str = "sqlite+aiosqlite:///./data/grocery.db"


class PlatformCredentials(BaseModel):
    enabled: bool = False
    base_url: str = ""
    partner_id: str = ""
    partner_key: str = ""
    shop_id: str = ""
    app_key: str = ""
    app_secret: str = ""
    access_token: str = ""
    associate_tag: str = ""
    access_key: str = ""
    secret_key: str = ""


class SchedulerConfig(BaseModel):
    enabled: bool = True
    interval_hours: int = 6
    cron_hour: int = 8
    cron_day: str = "sun"


class NotificationConfig(BaseModel):
    enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    email_smtp_server: str = ""
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""
    email_to_address: str = ""


class InventoryConfig(BaseModel):
    default_min_quantity: float = 1.0
    expiry_warning_days: int = 7
    low_stock_alert: bool = True


class PriceMonitorConfig(BaseModel):
    track_history: bool = True
    history_retention_days: int = 90
    alert_on_price_drop: bool = True
    price_drop_threshold_percent: float = 10.0


class Settings(BaseSettings):
    """Application settings loaded from config.yaml and environment."""

    app_name: str = "Grocery Manager"
    app_version: str = "0.1.0"
    debug: bool = True

    database: DatabaseConfig = DatabaseConfig()
    inventory: InventoryConfig = InventoryConfig()
    price_monitor: PriceMonitorConfig = PriceMonitorConfig()
    notifications: NotificationConfig = NotificationConfig()

    # Platform configs
    platforms: dict = {}

    class Config:
        env_prefix = "GROCERY_"
        env_file = ".env"


def load_config(config_path: Optional[Path] = None) -> Settings:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config.yaml"

    config_data = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}

    # Flatten the config for Settings
    settings_data = {
        "app_name": config_data.get("app", {}).get("name", "Grocery Manager"),
        "app_version": config_data.get("app", {}).get("version", "0.1.0"),
        "debug": config_data.get("app", {}).get("debug", True),
        "database": config_data.get("database", {}),
        "inventory": config_data.get("inventory", {}),
        "price_monitor": config_data.get("price_monitor", {}),
        "platforms": config_data.get("platforms", {}),
    }

    return Settings(**settings_data)


# Global settings instance
settings = load_config()
