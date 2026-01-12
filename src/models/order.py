"""Order models."""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship

from ..core.database import Base


class Order(Base):
    """Model for orders placed on platforms."""

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shopping_list_id = Column(Integer, ForeignKey("shopping_lists.id"))

    platform = Column(String(50), nullable=False)
    platform_order_id = Column(String(100))  # Order ID from the platform
    platform_order_url = Column(Text)

    status = Column(String(50), default="pending")
    # Status: pending/paid/processing/shipped/delivered/cancelled

    subtotal = Column(Float)
    delivery_fee = Column(Float)
    discount_amount = Column(Float)
    total_amount = Column(Float)

    delivery_address = Column(Text)
    delivery_slot = Column(String(100))  # e.g., "2024-01-15 10:00-12:00"

    payment_method = Column(String(50))
    payment_status = Column(String(50))

    notes = Column(Text)
    platform_response = Column(JSON)  # Store raw API response

    ordered_at = Column(DateTime)
    paid_at = Column(DateTime)
    shipped_at = Column(DateTime)
    delivered_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    shopping_list = relationship("ShoppingList", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Order(id={self.id}, platform='{self.platform}', status='{self.status}')>"

    @property
    def is_completed(self) -> bool:
        """Check if order is delivered."""
        return self.status == "delivered"

    @property
    def is_active(self) -> bool:
        """Check if order is still in progress."""
        return self.status in ("pending", "paid", "processing", "shipped")


class OrderItem(Base):
    """Model for items in an order."""

    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id"))

    platform_product_id = Column(String(100))
    product_name = Column(String(500))
    product_url = Column(Text)

    quantity = Column(Float, default=1)
    unit_price = Column(Float)
    total_price = Column(Float)

    notes = Column(Text)

    # Relationships
    order = relationship("Order", back_populates="items")
    inventory_item = relationship("InventoryItem")

    def __repr__(self):
        return f"<OrderItem(product='{self.product_name[:30] if self.product_name else 'N/A'}', qty={self.quantity})>"
