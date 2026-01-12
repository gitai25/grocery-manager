"""Shopping list models."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship

from ..core.database import Base


class ShoppingList(Base):
    """Model for shopping lists."""

    __tablename__ = "shopping_lists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200))  # Optional name for the list
    status = Column(String(50), default="draft")  # draft/pending/ordered/completed

    total_estimated_cost = Column(Float)
    actual_cost = Column(Float)

    notes = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime)

    # Relationships
    items = relationship("ShoppingListItem", back_populates="shopping_list", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="shopping_list")

    def __repr__(self):
        return f"<ShoppingList(id={self.id}, status='{self.status}', items={len(self.items) if self.items else 0})>"

    @property
    def item_count(self) -> int:
        """Get number of items in list."""
        return len(self.items) if self.items else 0

    def calculate_total(self) -> float:
        """Calculate total estimated cost."""
        if not self.items:
            return 0.0
        return sum(item.selected_price * item.quantity_needed for item in self.items if item.selected_price)


class ShoppingListItem(Base):
    """Model for items in a shopping list."""

    __tablename__ = "shopping_list_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shopping_list_id = Column(Integer, ForeignKey("shopping_lists.id"), nullable=False)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id"))

    product_name = Column(String(500))  # Can be custom if not linked to inventory
    quantity_needed = Column(Float, default=1)
    unit = Column(String(50))

    # Selected purchase option
    selected_platform = Column(String(50))
    selected_product_id = Column(String(100))
    selected_price = Column(Float)
    selected_url = Column(Text)

    # Alternative options stored as JSON
    alternatives = Column(JSON, default=list)
    # Format: [{"platform": "...", "price": ..., "url": "...", "product_id": "..."}]

    is_purchased = Column(Integer, default=0)
    notes = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    shopping_list = relationship("ShoppingList", back_populates="items")
    inventory_item = relationship("InventoryItem")

    def __repr__(self):
        name = self.product_name or f"Item#{self.inventory_item_id}"
        return f"<ShoppingListItem(name='{name}', qty={self.quantity_needed})>"

    @property
    def total_price(self) -> Optional[float]:
        """Calculate total price for this item."""
        if self.selected_price:
            return self.selected_price * self.quantity_needed
        return None

    def get_best_alternative(self) -> Optional[dict]:
        """Get the cheapest alternative."""
        if not self.alternatives:
            return None
        return min(self.alternatives, key=lambda x: x.get("price", float("inf")))
