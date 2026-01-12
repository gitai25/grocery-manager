"""Price monitoring models."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from ..core.database import Base


class PriceRecord(Base):
    """Model for price records from various platforms."""

    __tablename__ = "price_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id"))

    platform = Column(String(50), nullable=False, index=True)  # shopee/lazada/fairprice/etc
    platform_product_id = Column(String(100))  # Platform's product ID
    product_name = Column(String(500))
    product_url = Column(Text)
    image_url = Column(Text)

    price = Column(Float, nullable=False)  # Current price
    original_price = Column(Float)  # Original price before discount
    unit_price = Column(Float)  # Price per unit for comparison
    unit_size = Column(String(50))  # e.g., "1L", "500g"

    in_stock = Column(Boolean, default=True)
    stock_quantity = Column(Integer)

    discount_percent = Column(Float)
    promo_info = Column(Text)  # Promotion details
    delivery_fee = Column(Float)

    rating = Column(Float)
    review_count = Column(Integer)
    sold_count = Column(Integer)

    scraped_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    inventory_item = relationship("InventoryItem", back_populates="price_records")

    def __repr__(self):
        return f"<PriceRecord(platform='{self.platform}', product='{self.product_name[:30]}', price={self.price})>"

    @property
    def has_discount(self) -> bool:
        """Check if product has a discount."""
        return self.original_price is not None and self.price < self.original_price

    @property
    def discount_amount(self) -> Optional[float]:
        """Calculate discount amount."""
        if self.has_discount:
            return self.original_price - self.price
        return None

    @classmethod
    def calculate_unit_price(cls, price: float, size_str: str) -> Optional[float]:
        """Calculate price per standard unit (kg, L, or piece)."""
        import re

        size_str = size_str.lower().strip()

        # Parse quantity and unit
        match = re.match(r"(\d+(?:\.\d+)?)\s*(kg|g|l|ml|pcs?|pieces?|pack)", size_str)
        if not match:
            return None

        quantity = float(match.group(1))
        unit = match.group(2)

        # Convert to standard units
        if unit == "g":
            return price / (quantity / 1000)  # per kg
        elif unit == "kg":
            return price / quantity  # per kg
        elif unit == "ml":
            return price / (quantity / 1000)  # per L
        elif unit == "l":
            return price / quantity  # per L
        elif unit in ("pc", "pcs", "piece", "pieces", "pack"):
            return price / quantity  # per piece

        return None
