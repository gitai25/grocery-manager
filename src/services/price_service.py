"""Price monitoring and comparison service."""

from datetime import datetime, timedelta
from typing import List, Optional, Dict
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.price import PriceRecord
from ..models.inventory import InventoryItem
from ..adapters.base import PlatformAdapter, Product


class PriceService:
    """Service for monitoring and comparing prices across platforms."""

    def __init__(self, db: AsyncSession, adapters: Dict[str, PlatformAdapter] = None):
        self.db = db
        self.adapters = adapters or {}

    def register_adapter(self, name: str, adapter: PlatformAdapter):
        """Register a platform adapter."""
        self.adapters[name] = adapter

    async def search_all_platforms(
        self,
        query: str,
        limit: int = 10
    ) -> Dict[str, List[Product]]:
        """Search for a product across all registered platforms."""
        results = {}

        for platform_name, adapter in self.adapters.items():
            try:
                result = await adapter.search_products(query, limit=limit)
                results[platform_name] = result.products
            except Exception as e:
                print(f"Error searching {platform_name}: {e}")
                results[platform_name] = []

        return results

    async def compare_prices(
        self,
        query: str,
        limit: int = 5
    ) -> List[Dict]:
        """Compare prices across platforms and return sorted results."""
        all_results = await self.search_all_platforms(query, limit)

        # Flatten and sort by price
        all_products = []
        for platform, products in all_results.items():
            for product in products:
                all_products.append({
                    "platform": platform,
                    "product": product,
                    "price": product.price,
                    "unit_price": product.unit_price,
                })

        # Sort by unit price if available, otherwise by price
        all_products.sort(
            key=lambda x: x.get("unit_price") or x["price"]
        )

        return all_products

    async def save_price_record(
        self,
        inventory_item_id: Optional[int],
        platform: str,
        product: Product
    ) -> PriceRecord:
        """Save a price record to the database."""
        record = PriceRecord(
            inventory_item_id=inventory_item_id,
            platform=platform,
            platform_product_id=product.product_id,
            product_name=product.name,
            product_url=product.url,
            image_url=product.image_url,
            price=product.price,
            original_price=product.original_price,
            unit_price=product.unit_price,
            unit_size=product.unit_size,
            in_stock=product.in_stock,
            rating=product.rating,
            review_count=product.review_count,
            promo_info=product.promo_info,
            delivery_fee=product.delivery_fee
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def get_price_history(
        self,
        inventory_item_id: int,
        platform: str = None,
        days: int = 30
    ) -> List[PriceRecord]:
        """Get price history for an item."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        query = select(PriceRecord).where(
            and_(
                PriceRecord.inventory_item_id == inventory_item_id,
                PriceRecord.scraped_at >= cutoff
            )
        )

        if platform:
            query = query.where(PriceRecord.platform == platform)

        query = query.order_by(PriceRecord.scraped_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_best_price(
        self,
        inventory_item_id: int
    ) -> Optional[PriceRecord]:
        """Get the best current price for an inventory item."""
        # Get latest prices from each platform
        subquery = (
            select(
                PriceRecord.platform,
                func.max(PriceRecord.scraped_at).label("latest")
            )
            .where(PriceRecord.inventory_item_id == inventory_item_id)
            .group_by(PriceRecord.platform)
            .subquery()
        )

        query = (
            select(PriceRecord)
            .join(
                subquery,
                and_(
                    PriceRecord.platform == subquery.c.platform,
                    PriceRecord.scraped_at == subquery.c.latest
                )
            )
            .where(
                and_(
                    PriceRecord.inventory_item_id == inventory_item_id,
                    PriceRecord.in_stock == True
                )
            )
            .order_by(PriceRecord.price)
        )

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_price_alerts(
        self,
        threshold_percent: float = 10
    ) -> List[Dict]:
        """Get alerts for significant price drops."""
        alerts = []

        # Get all inventory items
        items_result = await self.db.execute(
            select(InventoryItem).where(InventoryItem.is_active == 1)
        )
        items = items_result.scalars().all()

        for item in items:
            history = await self.get_price_history(item.id, days=7)
            if len(history) >= 2:
                latest = history[0]
                previous = history[1]

                if previous.price > 0:
                    change = ((latest.price - previous.price) / previous.price) * 100

                    if change <= -threshold_percent:
                        alerts.append({
                            "item": item,
                            "platform": latest.platform,
                            "current_price": latest.price,
                            "previous_price": previous.price,
                            "change_percent": change,
                            "url": latest.product_url
                        })

        return alerts

    async def update_prices_for_item(
        self,
        item: InventoryItem
    ) -> List[PriceRecord]:
        """Update prices for a specific inventory item from all platforms."""
        records = []

        # Use item name and preferred brands as search queries
        search_queries = [item.name]
        if item.preferred_brands:
            for brand in item.preferred_brands[:2]:  # Limit to top 2 brands
                search_queries.append(f"{brand} {item.name}")

        for query in search_queries:
            for platform_name, adapter in self.adapters.items():
                try:
                    result = await adapter.search_products(query, limit=3)
                    for product in result.products:
                        record = await self.save_price_record(
                            item.id, platform_name, product
                        )
                        records.append(record)
                except Exception as e:
                    print(f"Error updating prices from {platform_name}: {e}")

        return records

    async def cleanup_old_records(self, days: int = 90):
        """Delete price records older than specified days."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        await self.db.execute(
            PriceRecord.__table__.delete().where(
                PriceRecord.scraped_at < cutoff
            )
        )
        await self.db.flush()
