"""Inventory management service."""

from datetime import date, datetime, timedelta
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.inventory import InventoryItem, ConsumptionLog


class InventoryService:
    """Service for managing inventory items."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_items(self, active_only: bool = True) -> List[InventoryItem]:
        """Get all inventory items."""
        query = select(InventoryItem)
        if active_only:
            query = query.where(InventoryItem.is_active == 1)
        query = query.order_by(InventoryItem.category, InventoryItem.name)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_item_by_id(self, item_id: int) -> Optional[InventoryItem]:
        """Get item by ID."""
        result = await self.db.execute(
            select(InventoryItem).where(InventoryItem.id == item_id)
        )
        return result.scalar_one_or_none()

    async def get_item_by_name(self, name: str) -> Optional[InventoryItem]:
        """Get item by name (case-insensitive)."""
        result = await self.db.execute(
            select(InventoryItem).where(InventoryItem.name.ilike(f"%{name}%"))
        )
        return result.scalar_one_or_none()

    async def create_item(
        self,
        name: str,
        category: str = None,
        unit: str = None,
        current_quantity: float = 0,
        min_quantity: float = 1,
        preferred_quantity: float = None,
        expiry_date: date = None,
        preferred_brands: List[str] = None,
        notes: str = None
    ) -> InventoryItem:
        """Create a new inventory item."""
        item = InventoryItem(
            name=name,
            category=category,
            unit=unit,
            current_quantity=current_quantity,
            min_quantity=min_quantity,
            preferred_quantity=preferred_quantity or min_quantity * 2,
            expiry_date=expiry_date,
            preferred_brands=preferred_brands or [],
            notes=notes
        )
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def update_item(self, item_id: int, **kwargs) -> Optional[InventoryItem]:
        """Update an inventory item."""
        item = await self.get_item_by_id(item_id)
        if not item:
            return None

        for key, value in kwargs.items():
            if hasattr(item, key) and value is not None:
                setattr(item, key, value)

        item.updated_at = datetime.utcnow()
        await self.db.flush()
        return item

    async def update_quantity(
        self,
        item_id: int,
        quantity_change: float,
        log_consumption: bool = True
    ) -> Optional[InventoryItem]:
        """Update item quantity (positive for add, negative for consume)."""
        item = await self.get_item_by_id(item_id)
        if not item:
            return None

        item.current_quantity += quantity_change
        if item.current_quantity < 0:
            item.current_quantity = 0

        # Log consumption if it's a decrease
        if quantity_change < 0 and log_consumption:
            log = ConsumptionLog(
                inventory_item_id=item_id,
                quantity_consumed=abs(quantity_change)
            )
            self.db.add(log)

            # Update average consumption rate
            await self._update_consumption_rate(item)

        await self.db.flush()
        return item

    async def _update_consumption_rate(self, item: InventoryItem):
        """Calculate and update average consumption rate."""
        # Get consumption logs from last 30 days
        cutoff = datetime.utcnow() - timedelta(days=30)
        result = await self.db.execute(
            select(ConsumptionLog).where(
                and_(
                    ConsumptionLog.inventory_item_id == item.id,
                    ConsumptionLog.logged_at >= cutoff
                )
            )
        )
        logs = result.scalars().all()

        if logs:
            total_consumed = sum(log.quantity_consumed for log in logs)
            days = 30
            item.avg_consumption_rate = total_consumed / days

    async def delete_item(self, item_id: int) -> bool:
        """Soft delete an inventory item."""
        item = await self.get_item_by_id(item_id)
        if not item:
            return False

        item.is_active = 0
        await self.db.flush()
        return True

    async def get_low_stock_items(self) -> List[InventoryItem]:
        """Get all items below minimum quantity."""
        result = await self.db.execute(
            select(InventoryItem).where(
                and_(
                    InventoryItem.is_active == 1,
                    InventoryItem.current_quantity < InventoryItem.min_quantity
                )
            )
        )
        return list(result.scalars().all())

    async def get_expiring_items(self, days: int = 7) -> List[InventoryItem]:
        """Get items expiring within specified days."""
        cutoff = date.today() + timedelta(days=days)
        result = await self.db.execute(
            select(InventoryItem).where(
                and_(
                    InventoryItem.is_active == 1,
                    InventoryItem.expiry_date.isnot(None),
                    InventoryItem.expiry_date <= cutoff
                )
            ).order_by(InventoryItem.expiry_date)
        )
        return list(result.scalars().all())

    async def get_items_by_category(self, category: str) -> List[InventoryItem]:
        """Get all items in a category."""
        result = await self.db.execute(
            select(InventoryItem).where(
                and_(
                    InventoryItem.is_active == 1,
                    InventoryItem.category.ilike(f"%{category}%")
                )
            ).order_by(InventoryItem.name)
        )
        return list(result.scalars().all())

    async def get_shopping_suggestions(self) -> List[dict]:
        """Generate shopping suggestions based on inventory levels."""
        suggestions = []

        # Get low stock items
        low_stock = await self.get_low_stock_items()
        for item in low_stock:
            qty_needed = item.quantity_to_buy()
            if qty_needed > 0:
                suggestions.append({
                    "item": item,
                    "quantity_needed": qty_needed,
                    "reason": "low_stock",
                    "priority": "high"
                })

        # Get expiring items (might need replacement)
        expiring = await self.get_expiring_items(days=3)
        for item in expiring:
            if item not in [s["item"] for s in suggestions]:
                suggestions.append({
                    "item": item,
                    "quantity_needed": item.min_quantity,
                    "reason": "expiring",
                    "priority": "medium"
                })

        return suggestions

    async def get_categories(self) -> List[str]:
        """Get list of all categories."""
        result = await self.db.execute(
            select(InventoryItem.category)
            .where(InventoryItem.is_active == 1)
            .distinct()
        )
        return [r[0] for r in result.all() if r[0]]

    async def get_inventory_summary(self) -> dict:
        """Get summary statistics of inventory."""
        items = await self.get_all_items()
        low_stock = await self.get_low_stock_items()
        expiring = await self.get_expiring_items()

        return {
            "total_items": len(items),
            "low_stock_count": len(low_stock),
            "expiring_count": len(expiring),
            "categories": await self.get_categories(),
            "total_value": 0,  # Would need price data
        }
