"""Watchlist service for monitoring premium products."""

import asyncio
import json
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.watchlist import WatchlistItem, WatchlistAlert
from ..adapters import get_adapter, ADAPTERS, PLATFORM_DISPLAY_NAMES
from .notification_service import notification_service


class WatchlistService:
    """Service for managing product watchlist and monitoring."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_item(
        self,
        name: str,
        brand: str,
        category: str = "sardines",
        origin_country: str = None,
        size: str = None,
        foodguard_score: int = None,
        search_keywords: List[str] = None,
        target_platforms: List[str] = None,
        platform_products: Dict = None,
        weekly_target_qty: int = 2,
        max_price: float = None,
        preferred_platforms: List[str] = None,
        notify_on_restock: bool = True,
        notify_on_price_drop: bool = True,
        price_drop_threshold: float = 0.1,
        notes: str = None,
    ) -> WatchlistItem:
        """Add a product to the watchlist."""
        item = WatchlistItem(
            name=name,
            brand=brand,
            category=category,
            origin_country=origin_country,
            size=size,
            foodguard_score=foodguard_score,
            search_keywords=search_keywords or [name, brand],
            target_platforms=target_platforms or list(ADAPTERS.keys()),
            platform_products=platform_products or {},
            weekly_target_qty=weekly_target_qty,
            max_price=max_price,
            preferred_platforms=preferred_platforms or [],
            notify_on_restock=notify_on_restock,
            notify_on_price_drop=notify_on_price_drop,
            price_drop_threshold=price_drop_threshold,
            notes=notes,
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def get_all_items(self, active_only: bool = True) -> List[WatchlistItem]:
        """Get all watchlist items."""
        query = select(WatchlistItem)
        if active_only:
            query = query.where(WatchlistItem.is_active == True)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_item(self, item_id: int) -> Optional[WatchlistItem]:
        """Get a specific watchlist item."""
        result = await self.db.execute(
            select(WatchlistItem).where(WatchlistItem.id == item_id)
        )
        return result.scalar_one_or_none()

    async def check_specific_url(self, url: str) -> Dict:
        """Check availability of a specific product URL."""
        from playwright.async_api import async_playwright
        import re

        result = {
            "url": url,
            "in_stock": False,
            "price": None,
            "title": None,
            "checked_at": datetime.utcnow().isoformat(),
        }

        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )
            page = await context.new_page()

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            # Get page content
            content = await page.content()
            text = await page.inner_text("body")

            # Check for out of stock indicators
            oos_indicators = [
                "out of stock", "sold out", "unavailable", "no longer available",
                "缺货", "售罄", "无库存", "Currently unavailable"
            ]
            is_oos = any(ind.lower() in text.lower() for ind in oos_indicators)

            # Check for in stock indicators
            stock_indicators = ["add to cart", "buy now", "in stock", "加入购物车"]
            is_in_stock = any(ind.lower() in text.lower() for ind in stock_indicators)

            result["in_stock"] = is_in_stock and not is_oos

            # Try to extract price
            price_match = re.search(r'S?\$\s*([\d,]+\.?\d*)', text)
            if price_match:
                result["price"] = float(price_match.group(1).replace(',', ''))

            # Try to get title
            title_elem = await page.query_selector('h1, [data-product-title], .product-title')
            if title_elem:
                result["title"] = await title_elem.inner_text()

            await context.close()
            await browser.close()
            await playwright.stop()

        except Exception as e:
            result["error"] = str(e)

        return result

    async def check_availability(
        self,
        item: WatchlistItem,
        platforms: List[str] = None
    ) -> Dict[str, dict]:
        """Check product availability across platforms."""
        platforms = platforms or item.target_platforms or list(ADAPTERS.keys())
        results = {}

        # First check any specific URLs we have
        if item.platform_products:
            for platform, product_info in item.platform_products.items():
                if isinstance(product_info, dict) and product_info.get("url"):
                    url = product_info["url"]
                    # Skip search URLs, check them via adapter
                    if product_info.get("search_url"):
                        continue
                    try:
                        url_result = await self.check_specific_url(url)
                        results[platform] = {
                            "in_stock": url_result.get("in_stock", False),
                            "price": url_result.get("price"),
                            "url": url,
                            "name": url_result.get("title", item.name),
                            "checked_at": url_result.get("checked_at"),
                            "direct_check": True,
                        }
                        if url_result.get("error"):
                            results[platform]["error"] = url_result["error"]
                    except Exception as e:
                        results[platform] = {
                            "in_stock": False,
                            "error": str(e),
                            "url": url,
                            "checked_at": datetime.utcnow().isoformat(),
                        }

        # Build search query
        search_terms = item.search_keywords or [item.name]
        query = " ".join(search_terms[:2])  # Use first 2 keywords

        for platform in platforms:
            try:
                adapter = get_adapter(platform)
                search_result = await adapter.search_products(query, limit=5)

                # Find matching product
                found = None
                for product in search_result.products:
                    # Check if this matches our watchlist item
                    name_lower = product.name.lower()
                    brand_lower = item.brand.lower() if item.brand else ""

                    if brand_lower in name_lower:
                        found = product
                        break

                if found:
                    results[platform] = {
                        "in_stock": found.in_stock,
                        "price": found.price,
                        "product_id": found.product_id,
                        "url": found.url,
                        "name": found.name,
                        "checked_at": datetime.utcnow().isoformat(),
                    }
                else:
                    results[platform] = {
                        "in_stock": False,
                        "price": None,
                        "checked_at": datetime.utcnow().isoformat(),
                        "note": "Product not found",
                    }

                await adapter.close()

            except Exception as e:
                results[platform] = {
                    "in_stock": False,
                    "price": None,
                    "error": str(e),
                    "checked_at": datetime.utcnow().isoformat(),
                }

        # Update item with results
        old_status = item.availability_status or {}
        item.availability_status = results
        item.last_checked_at = datetime.utcnow()

        # Find best deal
        available = [
            (p, s) for p, s in results.items()
            if s.get("in_stock") and s.get("price")
        ]
        if available:
            best = min(available, key=lambda x: x[1].get("price", float("inf")))
            item.current_best_platform = best[0]
            item.current_best_price = best[1].get("price")
            item.last_available_at = datetime.utcnow()

            # Check for alerts
            await self._check_alerts(item, old_status, results)

        await self.db.commit()
        return results

    async def _check_alerts(
        self,
        item: WatchlistItem,
        old_status: Dict,
        new_status: Dict
    ):
        """Check and create alerts for status changes."""
        for platform, status in new_status.items():
            old = old_status.get(platform, {})
            platform_name = PLATFORM_DISPLAY_NAMES.get(platform, platform)

            # Restock alert
            if status.get("in_stock") and not old.get("in_stock"):
                if item.notify_on_restock:
                    alert = WatchlistAlert(
                        watchlist_item_id=item.id,
                        alert_type="restock",
                        platform=platform,
                        message=f"{item.name} is back in stock on {platform_name}!",
                        new_price=status.get("price"),
                    )
                    self.db.add(alert)

                    # Send email notification
                    await notification_service.send_restock_alert(
                        product_name=item.name,
                        brand=item.brand or "",
                        platform=platform_name,
                        price=status.get("price") or 0,
                        url=status.get("url", ""),
                    )

            # Price drop alert
            if status.get("price") and old.get("price"):
                price_change = (old["price"] - status["price"]) / old["price"]
                if price_change >= item.price_drop_threshold:
                    if item.notify_on_price_drop:
                        alert = WatchlistAlert(
                            watchlist_item_id=item.id,
                            alert_type="price_drop",
                            platform=platform,
                            message=f"{item.name} price dropped {price_change*100:.0f}% on {platform_name}!",
                            old_price=old["price"],
                            new_price=status["price"],
                        )
                        self.db.add(alert)

                        # Send email notification
                        await notification_service.send_price_drop_alert(
                            product_name=item.name,
                            brand=item.brand or "",
                            platform=platform_name,
                            old_price=old["price"],
                            new_price=status["price"],
                            url=status.get("url", ""),
                        )

    async def check_all_items(self) -> Dict[int, Dict]:
        """Check availability for all active watchlist items."""
        items = await self.get_all_items(active_only=True)
        results = {}

        for item in items:
            print(f"Checking: {item.brand} - {item.name}...")
            results[item.id] = await self.check_availability(item)
            await asyncio.sleep(2)  # Rate limiting

        return results

    async def get_weekly_shopping_list(self) -> List[Dict]:
        """Generate weekly shopping recommendations based on watchlist."""
        items = await self.get_all_items(active_only=True)
        recommendations = []

        for item in items:
            if not item.is_available_anywhere:
                recommendations.append({
                    "item": item,
                    "status": "unavailable",
                    "message": f"{item.brand} {item.name} - 全渠道缺货",
                    "alternatives": [],
                })
                continue

            best_deal = item.get_best_deal()
            if best_deal:
                # Check if within max price
                if item.max_price and best_deal["price"] > item.max_price:
                    recommendations.append({
                        "item": item,
                        "status": "over_budget",
                        "message": f"{item.brand} {item.name} - S${best_deal['price']:.2f} 超出预算 (max: S${item.max_price:.2f})",
                        "best_deal": best_deal,
                    })
                else:
                    recommendations.append({
                        "item": item,
                        "status": "available",
                        "quantity": item.weekly_target_qty,
                        "platform": best_deal["platform"],
                        "platform_name": PLATFORM_DISPLAY_NAMES.get(best_deal["platform"], best_deal["platform"]),
                        "price": best_deal["price"],
                        "total": best_deal["price"] * item.weekly_target_qty,
                        "url": best_deal.get("url", ""),
                        "message": f"{item.brand} {item.name} x{item.weekly_target_qty} @ S${best_deal['price']:.2f}",
                    })

        return recommendations

    async def get_unread_alerts(self) -> List[WatchlistAlert]:
        """Get unread alerts."""
        result = await self.db.execute(
            select(WatchlistAlert)
            .where(WatchlistAlert.is_read == False)
            .order_by(WatchlistAlert.created_at.desc())
        )
        return result.scalars().all()

    async def mark_alert_read(self, alert_id: int):
        """Mark an alert as read."""
        result = await self.db.execute(
            select(WatchlistAlert).where(WatchlistAlert.id == alert_id)
        )
        alert = result.scalar_one_or_none()
        if alert:
            alert.is_read = True
            await self.db.commit()


# Pre-defined premium sardine products from FoodGuard reports
FOODGUARD_PRODUCTS = [
    {
        "name": "Small Mackerel in Olive Oil",
        "brand": "José Gourmet",
        "category": "mackerel",
        "origin_country": "Portugal",
        "size": "120g",
        "foodguard_score": 10,
        "search_keywords": ["Jose Gourmet", "Small Mackerel", "Olive Oil"],
        "target_platforms": ["amazon_sg", "little_farms"],
        "platform_products": {
            "fossa": {"url": "https://www.fossaprovisions.com/collections/jose-gourmet"},
            "morning_market": {"url": "https://morning.market/products/jose-gourmet-sardines", "price": 11.50},
        },
        "weekly_target_qty": 2,
        "max_price": 15.0,
        "notes": "Fair Trade认证，艺术包装，适合鲭鱼入门",
    },
    {
        "name": "MSC Sardines in Organic EVOO",
        "brand": "The Stock Merchant",
        "category": "sardines",
        "origin_country": "Australia/Portugal",
        "size": "120g",
        "foodguard_score": 10,
        "search_keywords": ["Stock Merchant", "Sardines", "Organic", "EVOO"],
        "target_platforms": ["little_farms", "amazon_sg"],
        "platform_products": {
            "little_farms": {"url": "https://littlefarms.com/sardines-evoo-120g-607434", "price": 9.48},
        },
        "weekly_target_qty": 3,
        "max_price": 12.0,
        "notes": "MSC+有机双认证，MTHFR最佳选择，目前Little Farms缺货",
    },
    {
        "name": "Sardines in Organic EVOO",
        "brand": "Good Fish",
        "category": "sardines",
        "origin_country": "Australia",
        "size": "120g/195g",
        "foodguard_score": 10,
        "search_keywords": ["Good Fish", "Sardines", "Organic", "EVOO"],
        "target_platforms": ["amazon_sg", "little_farms"],
        "platform_products": {
            "scoop": {"url": "https://scoopwholefoodsshop.com/products/sardines-extra-virgin-org-olive-oil-jar"},
        },
        "weekly_target_qty": 2,
        "max_price": 25.0,
        "notes": "35%有机EVOO，BPA-Free，夜捕晨加工",
    },
    {
        "name": "Spiced Sardines in Olive Oil",
        "brand": "NURI",
        "category": "sardines",
        "origin_country": "Portugal",
        "size": "125g",
        "foodguard_score": 10,
        "search_keywords": ["NURI", "Sardines", "Spiced", "Olive Oil", "Nuri"],
        "target_platforms": ["lazada_sg", "amazon_sg", "redmart"],
        "platform_products": {
            "lazada_sg": {
                "url": "https://www.lazada.sg/products/nuri-spiced-sardines-in-olive-oil-125g-i1224956803.html",
                "product_id": "1224956803",
                "in_stock": False,
                "last_checked": "2026-01-12",
            },
            "amazon_sg": {
                "url": "https://www.amazon.sg/nuri-sardines/s?k=nuri+sardines",
                "search_url": True,
                "in_stock": False,
                "last_checked": "2026-01-12",
            },
        },
        "weekly_target_qty": 2,
        "max_price": 15.0,
        "notify_on_restock": True,
        "notes": "绿色包装香料版是入坑必选，37道手工工序，BPA-Free。Lazada/Amazon均缺货，需监控补货。",
    },
    {
        "name": "Sardinas a la Antigua",
        "brand": "Ortiz",
        "category": "sardines",
        "origin_country": "Spain",
        "size": "140g/190g",
        "foodguard_score": 9,
        "search_keywords": ["Ortiz", "Sardines", "Sardinas", "Olive Oil"],
        "target_platforms": ["amazon_sg", "little_farms", "lazada_sg"],
        "platform_products": {
            "amazon_fresh": {"url": "https://www.amazon.sg/dp/B0076ZQLH8", "price": 18.0},
            "little_farms": {"url": "https://littlefarms.com/ortiz-sardines-old-style-140g-604794"},
        },
        "weekly_target_qty": 2,
        "max_price": 25.0,
        "preferred_platforms": ["amazon_sg"],
        "notes": "西班牙顶级品牌1896年，Amazon Fresh有超值价S$18",
    },
    {
        "name": "Sardines in Olive Oil Gold Line",
        "brand": "Ramón Peña",
        "category": "sardines",
        "origin_country": "Spain",
        "size": "130g",
        "foodguard_score": 9,
        "search_keywords": ["Ramon Pena", "Sardines", "Gold Line", "Olive Oil"],
        "target_platforms": ["amazon_sg", "little_farms"],
        "platform_products": {
            "lata_shop": {"url": "https://lata.shop/collections/ramon-pena"},
            "la_tienda": {"url": "https://www.tienda.com/products/sardinillas-olive-oil-ramon-pena-se-171.html"},
        },
        "weekly_target_qty": 2,
        "max_price": 30.0,
        "notes": "沙丁鱼罐头的终极形态，新加坡渠道有限，需特订或国际配送",
    },
]


async def init_foodguard_watchlist(db: AsyncSession) -> List[WatchlistItem]:
    """Initialize watchlist with FoodGuard recommended products."""
    service = WatchlistService(db)
    items = []

    for product in FOODGUARD_PRODUCTS:
        # Check if already exists
        result = await db.execute(
            select(WatchlistItem).where(
                WatchlistItem.brand == product["brand"],
                WatchlistItem.name == product["name"],
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"Already exists: {product['brand']} - {product['name']}")
            items.append(existing)
            continue

        item = await service.add_item(**product)
        print(f"Added: {product['brand']} - {product['name']}")
        items.append(item)

    return items
