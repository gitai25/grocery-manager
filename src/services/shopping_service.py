"""Shopping list and order management service."""

from datetime import datetime
from typing import List, Optional, Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.shopping import ShoppingList, ShoppingListItem
from ..models.inventory import InventoryItem
from .inventory_service import InventoryService
from .price_service import PriceService


class ShoppingService:
    """Service for managing shopping lists and orders."""

    def __init__(
        self,
        db: AsyncSession,
        inventory_service: InventoryService = None,
        price_service: PriceService = None
    ):
        self.db = db
        self.inventory_service = inventory_service or InventoryService(db)
        self.price_service = price_service

    async def create_shopping_list(self, name: str = None) -> ShoppingList:
        """Create a new shopping list."""
        shopping_list = ShoppingList(
            name=name or f"Shopping List {datetime.now().strftime('%Y-%m-%d')}",
            status="draft"
        )
        self.db.add(shopping_list)
        await self.db.flush()
        await self.db.refresh(shopping_list)
        return shopping_list

    async def get_shopping_list(self, list_id: int) -> Optional[ShoppingList]:
        """Get a shopping list by ID."""
        result = await self.db.execute(
            select(ShoppingList).where(ShoppingList.id == list_id)
        )
        return result.scalar_one_or_none()

    async def get_active_lists(self) -> List[ShoppingList]:
        """Get all non-completed shopping lists."""
        result = await self.db.execute(
            select(ShoppingList)
            .where(ShoppingList.status.in_(["draft", "pending"]))
            .order_by(ShoppingList.created_at.desc())
        )
        return list(result.scalars().all())

    async def add_item_to_list(
        self,
        list_id: int,
        inventory_item_id: int = None,
        product_name: str = None,
        quantity: float = 1,
        unit: str = None
    ) -> ShoppingListItem:
        """Add an item to a shopping list."""
        # Get inventory item details if linked
        if inventory_item_id:
            inv_item = await self.inventory_service.get_item_by_id(inventory_item_id)
            if inv_item:
                product_name = product_name or inv_item.name
                unit = unit or inv_item.unit

        item = ShoppingListItem(
            shopping_list_id=list_id,
            inventory_item_id=inventory_item_id,
            product_name=product_name,
            quantity_needed=quantity,
            unit=unit
        )
        self.db.add(item)
        await self.db.flush()
        return item

    async def remove_item_from_list(self, item_id: int) -> bool:
        """Remove an item from a shopping list."""
        result = await self.db.execute(
            select(ShoppingListItem).where(ShoppingListItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if item:
            await self.db.delete(item)
            await self.db.flush()
            return True
        return False

    async def generate_list_from_inventory(self) -> ShoppingList:
        """Auto-generate shopping list based on inventory levels."""
        suggestions = await self.inventory_service.get_shopping_suggestions()

        if not suggestions:
            return None

        # Create new list
        shopping_list = await self.create_shopping_list(
            name=f"Auto-generated {datetime.now().strftime('%Y-%m-%d')}"
        )

        # Add suggested items
        for suggestion in suggestions:
            item = suggestion["item"]
            await self.add_item_to_list(
                list_id=shopping_list.id,
                inventory_item_id=item.id,
                quantity=suggestion["quantity_needed"],
                unit=item.unit
            )

        # Update total estimate
        await self.update_list_total(shopping_list.id)

        return shopping_list

    async def find_best_prices_for_list(self, list_id: int) -> ShoppingList:
        """Find best prices for all items in a shopping list."""
        shopping_list = await self.get_shopping_list(list_id)
        if not shopping_list or not self.price_service:
            return shopping_list

        for item in shopping_list.items:
            search_query = item.product_name

            # Get comparison results
            comparisons = await self.price_service.compare_prices(search_query, limit=5)

            if comparisons:
                # Set best option as selected
                best = comparisons[0]
                item.selected_platform = best["platform"]
                item.selected_price = best["price"]
                item.selected_product_id = best["product"].product_id
                item.selected_url = best["product"].url

                # Store alternatives
                item.alternatives = [
                    {
                        "platform": c["platform"],
                        "price": c["price"],
                        "product_id": c["product"].product_id,
                        "url": c["product"].url,
                        "name": c["product"].name
                    }
                    for c in comparisons[1:5]
                ]

        await self.db.flush()
        await self.update_list_total(list_id)

        return shopping_list

    async def update_list_total(self, list_id: int):
        """Update the total estimated cost of a shopping list."""
        shopping_list = await self.get_shopping_list(list_id)
        if shopping_list:
            total = sum(
                (item.selected_price or 0) * item.quantity_needed
                for item in shopping_list.items
            )
            shopping_list.total_estimated_cost = total
            await self.db.flush()

    async def mark_item_purchased(self, item_id: int) -> bool:
        """Mark an item as purchased."""
        result = await self.db.execute(
            select(ShoppingListItem).where(ShoppingListItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if item:
            item.is_purchased = 1
            await self.db.flush()
            return True
        return False

    async def complete_list(self, list_id: int, update_inventory: bool = True):
        """Complete a shopping list and optionally update inventory."""
        shopping_list = await self.get_shopping_list(list_id)
        if not shopping_list:
            return None

        if update_inventory:
            for item in shopping_list.items:
                if item.inventory_item_id and item.is_purchased:
                    await self.inventory_service.update_quantity(
                        item.inventory_item_id,
                        item.quantity_needed,
                        log_consumption=False
                    )
                    # Update last purchase date
                    inv_item = await self.inventory_service.get_item_by_id(
                        item.inventory_item_id
                    )
                    if inv_item:
                        inv_item.last_purchase_date = datetime.now().date()

        shopping_list.status = "completed"
        shopping_list.completed_at = datetime.utcnow()
        await self.db.flush()

        return shopping_list

    async def get_list_summary(self, list_id: int) -> Dict:
        """Get summary of a shopping list."""
        shopping_list = await self.get_shopping_list(list_id)
        if not shopping_list:
            return {}

        # Group by platform
        by_platform = {}
        for item in shopping_list.items:
            platform = item.selected_platform or "unassigned"
            if platform not in by_platform:
                by_platform[platform] = {
                    "items": [],
                    "subtotal": 0
                }
            by_platform[platform]["items"].append(item)
            if item.selected_price:
                by_platform[platform]["subtotal"] += item.selected_price * item.quantity_needed

        return {
            "list": shopping_list,
            "item_count": len(shopping_list.items),
            "total_estimated": shopping_list.total_estimated_cost,
            "by_platform": by_platform,
            "purchased_count": sum(1 for i in shopping_list.items if i.is_purchased)
        }
