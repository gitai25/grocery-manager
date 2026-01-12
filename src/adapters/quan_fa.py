"""Quan Fa Organic Farm adapter using web scraping."""

import asyncio
import re
from typing import Optional, List
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, Browser, Page

from .base import PlatformAdapter, Product, PriceInfo, SearchResult


class QuanFaAdapter(PlatformAdapter):
    """Adapter for Quan Fa Organic Farm."""

    platform_name = "quan_fa"
    base_url = "https://quanfaorganic.com.sg"

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
            # WooCommerce search format
            url = f"{self.base_url}/?s={encoded_query}&post_type=product"

            await browser_page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(2)

            # WooCommerce product selectors
            product_cards = await browser_page.query_selector_all('.product, .type-product, li.product')

            seen_ids = set()
            for card in product_cards:
                if len(products) >= limit:
                    break
                try:
                    link = await card.query_selector('a.woocommerce-LoopProduct-link, a[href*="/product/"]')
                    if not link:
                        continue

                    href = await link.get_attribute('href')
                    if not href:
                        continue

                    product_id = href.rstrip('/').split('/')[-1]
                    if product_id in seen_ids:
                        continue
                    seen_ids.add(product_id)

                    name_elem = await card.query_selector('.woocommerce-loop-product__title, h2, .product-title')
                    name = await name_elem.inner_text() if name_elem else ""

                    price = 0.0
                    price_elem = await card.query_selector('.price .amount, .woocommerce-Price-amount')
                    if price_elem:
                        price_text = await price_elem.inner_text()
                        match = re.search(r'\$?([\d.]+)', price_text)
                        if match:
                            price = float(match.group(1))

                    if name:
                        products.append(Product(
                            product_id=product_id,
                            name=name.strip(),
                            price=price,
                            in_stock=True,
                            url=href
                        ))
                except Exception:
                    continue

            await browser_page.context.close()

        except Exception as e:
            print(f"Error searching Quan Fa: {e}")

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
            url = f"{self.base_url}/product/{product_id}/"
            await browser_page.goto(url, wait_until="networkidle", timeout=30000)

            name_elem = await browser_page.query_selector('h1.product_title, .product-title')
            name = await name_elem.inner_text() if name_elem else ""

            price = 0.0
            price_elem = await browser_page.query_selector('.price .amount, .woocommerce-Price-amount')
            if price_elem:
                price_text = await price_elem.inner_text()
                match = re.search(r'\$?([\d.]+)', price_text)
                if match:
                    price = float(match.group(1))

            in_stock = True
            oos = await browser_page.query_selector('.out-of-stock')
            if oos:
                in_stock = False

            await browser_page.context.close()

            return Product(
                product_id=product_id,
                name=name.strip(),
                price=price,
                in_stock=in_stock,
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
        return f"{self.base_url}/product/{product_id}/"

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None
