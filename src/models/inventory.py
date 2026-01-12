"""Inventory models."""

from datetime import date, datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship

from ..core.database import Base


class InventoryItem(Base):
    """Model for inventory items."""

    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    category = Column(String(100), index=True)  # 食品/日用品/清洁用品/保健品
    subcategory = Column(String(100))  # 子分类

    current_quantity = Column(Float, default=0)
    unit = Column(String(50))  # 个/瓶/kg/L/盒
    min_quantity = Column(Float, default=1)  # 最低库存警戒线
    preferred_quantity = Column(Float)  # 理想库存量

    expiry_date = Column(Date)  # 过期日期
    last_purchase_date = Column(Date)
    avg_consumption_rate = Column(Float)  # 每日平均消耗量

    preferred_brands = Column(JSON, default=list)  # 偏好品牌列表
    search_keywords = Column(JSON, default=list)  # 搜索关键词
    barcode = Column(String(50))  # 条形码

    notes = Column(Text)
    is_active = Column(Integer, default=1)  # 1=活跃, 0=停用

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    consumption_logs = relationship("ConsumptionLog", back_populates="item")
    price_records = relationship("PriceRecord", back_populates="inventory_item")

    def __repr__(self):
        return f"<InventoryItem(id={self.id}, name='{self.name}', qty={self.current_quantity})>"

    @property
    def is_low_stock(self) -> bool:
        """Check if item is below minimum quantity."""
        return self.current_quantity < self.min_quantity

    @property
    def days_until_expiry(self) -> Optional[int]:
        """Calculate days until expiry."""
        if self.expiry_date:
            delta = self.expiry_date - date.today()
            return delta.days
        return None

    @property
    def is_expiring_soon(self) -> bool:
        """Check if item is expiring within 7 days."""
        days = self.days_until_expiry
        return days is not None and days <= 7

    def quantity_to_buy(self) -> float:
        """Calculate quantity needed to reach preferred level."""
        if self.preferred_quantity:
            needed = self.preferred_quantity - self.current_quantity
            return max(0, needed)
        elif self.min_quantity:
            needed = self.min_quantity * 2 - self.current_quantity
            return max(0, needed)
        return 0


class ConsumptionLog(Base):
    """Log of item consumption for calculating usage patterns."""

    __tablename__ = "consumption_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=False)
    quantity_consumed = Column(Float, nullable=False)
    logged_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text)

    # Relationships
    item = relationship("InventoryItem", back_populates="consumption_logs")

    def __repr__(self):
        return f"<ConsumptionLog(item_id={self.inventory_item_id}, qty={self.quantity_consumed})>"
