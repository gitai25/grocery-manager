"""RedMart (Lazada Grocery) adapter using web scraping."""

import asyncio
import re
from typing import Optional, List
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, Browser, Page

from .base import PlatformAdapter, Product, PriceInfo, SearchResult


class RedMartAdapter(PlatformAdapter):
    """Adapter for RedMart (Lazada's grocery platform)."""

    platform_name = "redmart"
    base_url = "https://www.lazada.sg"
    redmart_base = "https://www.lazada.sg/shop/redmart"

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
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()
        return page

    async def search_products(
        self,
        query: str,
        limit: int = 20,
        page: int = 1,
        sort_by: str = "relevance",
        category: str = None
    ) -> SearchResult:
        """
        Search for products on RedMart.

        Args:
            query: Search query
            limit: Max results to return
            page: Page number
            sort_by: Sort method
            category: Optional category filter (fresh, pantry, beverages, etc.)
        """
        products = []

        try:
            browser_page = await self._get_page()
            encoded_query = quote_plus(query)

            # RedMart search URL (part of Lazada)
            # Filter by RedMart seller
            url = f"{self.base_url}/catalog/?q={encoded_query}&from=suggest&seller=redmart&page={page}"

            await browser_page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)

            # Find product cards
            product_cards = await browser_page.query_selector_all('[data-qa-locator="product-item"], .Bm3ON, [data-tracking="product-card"]')

            if not product_cards:
                product_cards = await browser_page.query_selector_all('div[data-item-id], .qmXQo, a[href*="/products/"]')

            seen_ids = set()
            for card in product_cards:
                if len(products) >= limit:
                    break
                try:
                    # Get product link
                    link = await card.query_selector('a[href*="/products/"]')
                    if not link:
                        link = card if await card.get_attribute('href') else None

                    if not link:
                        continue

                    href = await link.get_attribute('href')
                    if not href or '/products/' not in href:
                        continue

                    # Extract product ID
                    product_id_match = re.search(r'-i(\d+)-s(\d+)', href)
                    if product_id_match:
                        product_id = f"{product_id_match.group(1)}-{product_id_match.group(2)}"
                    else:
                        product_id = href.split('/products/')[-1].split('.')[0].split('?')[0]

                    if product_id in seen_ids:
                        continue
                    seen_ids.add(product_id)

                    # Parse text content
                    text = await card.inner_text()
                    lines = [l.strip() for l in text.split('\n') if l.strip()]

                    price = 0.0
                    original_price = None
                    name = ""
                    unit_size = None

                    for line in lines:
                        if '$' in line or 'S$' in line:
                            match = re.search(r'S?\$\s*([\d,]+\.?\d*)', line)
                            if match:
                                price_val = float(match.group(1).replace(',', ''))
                                if price == 0:
                                    price = price_val
                                elif price_val > price:
                                    original_price = price_val
                        elif len(line) > 5 and '$' not in line:
                            # Check for unit size
                            size_match = re.search(r'(\d+(?:\.\d+)?)\s*(kg|g|ml|l|pcs?|pack)', line.lower())
                            if size_match:
                                unit_size = f"{size_match.group(1)}{size_match.group(2)}"
                            # Name detection
                            if not name and len(line) > 10 and not any(skip in line.lower() for skip in ['sold', 'rating', 'free']):
                                name = line

                    if name and price > 0:
                        products.append(Product(
                            product_id=product_id,
                            name=name[:200],
                            price=price,
                            original_price=original_price,
                            unit_size=unit_size,
                            in_stock=True,
                            url=href if href.startswith('http') else f"{self.base_url}{href}",
                            promo_info="RedMart"
                        ))
                except Exception:
                    continue

            await browser_page.context.close()

        except Exception as e:
            print(f"Error searching RedMart: {e}")

        return SearchResult(
            platform=self.platform_name,
            query=query,
            products=products,
            total_count=len(products),
            page=page,
            has_more=len(products) >= limit
        )

    async def browse_category(
        self,
        category: str,
        limit: int = 20,
        page: int = 1
    ) -> SearchResult:
        """
        Browse products by RedMart category.

        Categories: fresh, pantry, beverages, snacks, frozen, dairy, baby, household, personal-care
        """
        products = []

        try:
            browser_page = await self._get_page()

            # Category URL mapping
            category_urls = {
                "fresh": f"{self.redmart_base}/?spm=a2o42.home.cate_1",
                "pantry": f"{self.redmart_base}/?spm=a2o42.home.cate_2",
                "beverages": f"{self.redmart_base}/?spm=a2o42.home.cate_3",
                "snacks": f"{self.redmart_base}/?spm=a2o42.home.cate_4",
                "frozen": f"{self.redmart_base}/?spm=a2o42.home.cate_5",
            }

            url = category_urls.get(category.lower(), self.redmart_base)

            await browser_page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)

            product_cards = await browser_page.query_selector_all('[data-qa-locator="product-item"], .Bm3ON, a[href*="/products/"]')

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

                    product_id_match = re.search(r'-i(\d+)-s(\d+)', href)
                    if product_id_match:
                        product_id = f"{product_id_match.group(1)}-{product_id_match.group(2)}"
                    else:
                        continue

                    if product_id in seen_ids:
                        continue
                    seen_ids.add(product_id)

                    text = await card.inner_text()
                    lines = [l.strip() for l in text.split('\n') if l.strip()]

                    price = 0.0
                    name = ""

                    for line in lines:
                        if '$' in line:
                            match = re.search(r'S?\$\s*([\d,]+\.?\d*)', line)
                            if match and price == 0:
                                price = float(match.group(1).replace(',', ''))
                        elif len(line) > 5 and '$' not in line and not name:
                            name = line

                    if name and price > 0:
                        products.append(Product(
                            product_id=product_id,
                            name=name[:200],
                            price=price,
                            in_stock=True,
                            url=href if href.startswith('http') else f"{self.base_url}{href}"
                        ))
                except Exception:
                    continue

            await browser_page.context.close()

        except Exception as e:
            print(f"Error browsing RedMart category: {e}")

        return SearchResult(
            platform=self.platform_name,
            query=f"category:{category}",
            products=products,
            total_count=len(products),
            page=page,
            has_more=len(products) >= limit
        )

    async def get_product_details(self, product_id: str) -> Optional[Product]:
        try:
            browser_page = await self._get_page()

            if '-' in product_id:
                item_id, sku_id = product_id.split('-')
                url = f"{self.base_url}/products/-i{item_id}-s{sku_id}.html"
            else:
                url = f"{self.base_url}/products/{product_id}.html"

            await browser_page.goto(url, wait_until="networkidle", timeout=30000)

            name_elem = await browser_page.query_selector('h1, .pdp-mod-product-badge-title')
            name = await name_elem.inner_text() if name_elem else ""

            price = 0.0
            price_elem = await browser_page.query_selector('.pdp-price, .pdp-product-price')
            if price_elem:
                price_text = await price_elem.inner_text()
                match = re.search(r'S?\$\s*([\d,]+\.?\d*)', price_text)
                if match:
                    price = float(match.group(1).replace(',', ''))

            # Get unit size from product info
            unit_size = None
            spec_elem = await browser_page.query_selector('.pdp-product-desc, [data-spm="specifications"]')
            if spec_elem:
                spec_text = await spec_elem.inner_text()
                size_match = re.search(r'(\d+(?:\.\d+)?)\s*(kg|g|ml|l|pcs?|pack)', spec_text.lower())
                if size_match:
                    unit_size = f"{size_match.group(1)}{size_match.group(2)}"

            img_elem = await browser_page.query_selector('.pdp-mod-common-image img')
            image_url = await img_elem.get_attribute('src') if img_elem else ""

            in_stock = True
            oos_elem = await browser_page.query_selector('[class*="out-of-stock"]')
            if oos_elem:
                in_stock = False

            await browser_page.context.close()

            return Product(
                product_id=product_id,
                name=name.strip(),
                price=price,
                unit_size=unit_size,
                in_stock=in_stock,
                url=url,
                image_url=image_url
            )
        except Exception as e:
            print(f"Error getting RedMart product details: {e}")
            return None

    async def get_price(self, product_id: str) -> Optional[PriceInfo]:
        product = await self.get_product_details(product_id)
        if product:
            return PriceInfo(
                product_id=product_id,
                price=product.price,
                original_price=product.original_price,
                in_stock=product.in_stock
            )
        return None

    def get_product_url(self, product_id: str) -> str:
        if '-' in product_id:
            item_id, sku_id = product_id.split('-')
            return f"{self.base_url}/products/-i{item_id}-s{sku_id}.html"
        return f"{self.base_url}/products/{product_id}.html"

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None
