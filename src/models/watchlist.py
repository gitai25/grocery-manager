"""Watchlist models for premium product monitoring."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON, Boolean

from ..core.database import Base


class WatchlistItem(Base):
    """Model for products to monitor across platforms."""

    __tablename__ = "watchlist_items"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Product identification
    name = Column(String(500), nullable=False, index=True)
    brand = Column(String(200), index=True)
    origin_country = Column(String(100))  # e.g., "Portugal", "Spain", "Australia"

    # Product details
    category = Column(String(100), index=True)  # sardines, mackerel, etc.
    size = Column(String(50))  # e.g., "120g", "190g"
    foodguard_score = Column(Integer)  # 1-10 rating

    # Search configuration
    search_keywords = Column(JSON, default=list)  # Keywords to search on platforms
    target_platforms = Column(JSON, default=list)  # Platforms to monitor

    # Known product URLs/IDs on each platform
    platform_products = Column(JSON, default=dict)
    # Format: {"amazon_sg": {"product_id": "...", "url": "..."}, "little_farms": {...}}

    # Purchasing preferences
    weekly_target_qty = Column(Integer, default=2)  # Target purchase per week
    max_price = Column(Float)  # Maximum acceptable price (SGD)
    preferred_platforms = Column(JSON, default=list)  # Ordered preference

    # Monitoring status
    is_active = Column(Boolean, default=True)
    last_checked_at = Column(DateTime)
    last_available_at = Column(DateTime)
    current_best_price = Column(Float)
    current_best_platform = Column(String(100))

    # Availability tracking
    availability_status = Column(JSON, default=dict)
    # Format: {"amazon_sg": {"in_stock": true, "price": 18.0, "checked_at": "..."}, ...}

    # Alerts
    notify_on_restock = Column(Boolean, default=True)
    notify_on_price_drop = Column(Boolean, default=True)
    price_drop_threshold = Column(Float, default=0.1)  # 10% drop triggers alert

    notes = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<WatchlistItem(id={self.id}, name='{self.name}', brand='{self.brand}')>"

    @property
    def is_available_anywhere(self) -> bool:
        """Check if product is in stock on any platform."""
        if not self.availability_status:
            return False
        return any(
            status.get("in_stock", False)
            for status in self.availability_status.values()
        )

    @property
    def available_platforms(self) -> List[str]:
        """Get list of platforms where product is in stock."""
        if not self.availability_status:
            return []
        return [
            platform for platform, status in self.availability_status.items()
            if status.get("in_stock", False)
        ]

    def get_best_deal(self) -> Optional[dict]:
        """Get the best available deal."""
        if not self.availability_status:
            return None

        available = [
            {"platform": p, **s}
            for p, s in self.availability_status.items()
            if s.get("in_stock", False) and s.get("price")
        ]

        if not available:
            return None

        return min(available, key=lambda x: x.get("price", float("inf")))


class WatchlistAlert(Base):
    """Alerts for watchlist items."""

    __tablename__ = "watchlist_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    watchlist_item_id = Column(Integer, index=True)

    alert_type = Column(String(50))  # restock, price_drop, out_of_stock
    platform = Column(String(100))
    message = Column(Text)

    old_price = Column(Float)
    new_price = Column(Float)

    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<WatchlistAlert(type='{self.alert_type}', platform='{self.platform}')>"
