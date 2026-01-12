"""The Meatery (Halal) adapter using web scraping."""

import asyncio
import re
from typing import Optional, List
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, Browser, Page

from .base import PlatformAdapter, Product, PriceInfo, SearchResult


class MeateryAdapter(PlatformAdapter):
    """Adapter for The Meatery (Halal)."""

    platform_name = "meatery"
    base_url = "https://www.themeatery.sg"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self._browser: Optional[Browser] = None
        self._playwright = None

    async def _get_browser(self) -> Browser:
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
        return self._browser

    async def _get_page(self) -> Page:
        browser = await self._get_browser()
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        return await context.new_page()

    async def search_products(
        self,
        query: str,
        limit: int = 20,
        page: int = 1,
        sort_by: str = "relevance"
    ) -> SearchResult:
        products = []
        try:
            browser_page = await self._get_page()
            encoded_query = quote_plus(query)
            url = f"{self.base_url}/search?q={encoded_query}"

            await browser_page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(2)

            product_cards = await browser_page.query_selector_all('.product-card, .grid-product, .product-item, a[href*="/products/"]')

            seen_ids = set()
            for card in product_cards:
                if len(products) >= limit:
                    break
                try:
                    href = await card.get_attribute('href')
                    if not href:
                        link = await card.query_selector('a[href*="/products/"]')
                        if link:
                            href = await link.get_attribute('href')

                    if not href or '/products/' not in href:
                        continue

                    product_id = href.split('/products/')[-1].split('?')[0]
                    if product_id in seen_ids:
                        continue
                    seen_ids.add(product_id)

                    text = await card.inner_text()
                    lines = [l.strip() for l in text.split('\n') if l.strip()]

                    price = 0.0
                    name = ""
                    for line in lines:
                        if '$' in line:
                            match = re.search(r'\$\s*([\d.]+)', line)
                            if match and price == 0:
                                price = float(match.group(1))
                        elif len(line) > 3 and '$' not in line and not name:
                            name = line

                    if name:
                        products.append(Product(
                            product_id=product_id,
                            name=name,
                            price=price,
                            in_stock=True,
                            url=f"{self.base_url}{href}" if not href.startswith('http') else href
                        ))
                except Exception:
                    continue

            await browser_page.context.close()

        except Exception as e:
            print(f"Error searching Meatery: {e}")

        return SearchResult(
            platform=self.platform_name,
            query=query,
            products=products,
            total_count=len(products),
            page=page,
            has_more=len(products) >= limit
        )

    async def get_product_details(self, product_id: str) -> Optional[Product]:
        try:
            browser_page = await self._get_page()
            url = f"{self.base_url}/products/{product_id}"
            await browser_page.goto(url, wait_until="networkidle", timeout=30000)

            name_elem = await browser_page.query_selector('h1, .product-title')
            name = await name_elem.inner_text() if name_elem else ""

            price = 0.0
            price_elem = await browser_page.query_selector('.product-price, .price')
            if price_elem:
                price_text = await price_elem.inner_text()
                match = re.search(r'\$?([\d.]+)', price_text)
                if match:
                    price = float(match.group(1))

            await browser_page.context.close()

            return Product(
                product_id=product_id,
                name=name.strip(),
                price=price,
                in_stock=True,
                url=url
            )
        except Exception as e:
            print(f"Error getting product details: {e}")
            return None

    async def get_price(self, product_id: str) -> Optional[PriceInfo]:
        product = await self.get_product_details(product_id)
        if product:
            return PriceInfo(
                product_id=product_id,
                price=product.price,
                in_stock=product.in_stock
            )
        return None

    def get_product_url(self, product_id: str) -> str:
        return f"{self.base_url}/products/{product_id}"

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None
