"""Lazada Singapore adapter using web scraping."""

import asyncio
import re
from typing import Optional, List
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, Browser, Page

from .base import PlatformAdapter, Product, PriceInfo, SearchResult


class LazadaSGAdapter(PlatformAdapter):
    """Adapter for Lazada Singapore (including LazMall)."""

    platform_name = "lazada_sg"
    base_url = "https://www.lazada.sg"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self._browser: Optional[Browser] = None
        self._playwright = None
        # Config options
        self.lazmall_only = config.get("lazmall_only", False) if config else False

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
        lazmall_only: bool = None
    ) -> SearchResult:
        """
        Search for products on Lazada.

        Args:
            query: Search query
            limit: Max results to return
            page: Page number
            sort_by: Sort method (relevance, price_asc, price_desc, sales)
            lazmall_only: If True, only return LazMall products
        """
        products = []
        use_lazmall = lazmall_only if lazmall_only is not None else self.lazmall_only

        try:
            browser_page = await self._get_page()
            encoded_query = quote_plus(query)

            # Build search URL
            sort_param = {
                "relevance": "",
                "price_asc": "&sort=priceasc",
                "price_desc": "&sort=pricedesc",
                "sales": "&sort=sales"
            }.get(sort_by, "")

            # LazMall filter
            lazmall_param = "&lazmall=1" if use_lazmall else ""

            url = f"{self.base_url}/catalog/?q={encoded_query}&page={page}{sort_param}{lazmall_param}"

            await browser_page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)  # Wait for dynamic content

            # Try to find product cards
            product_cards = await browser_page.query_selector_all('[data-qa-locator="product-item"], .Bm3ON, [data-tracking="product-card"]')

            if not product_cards:
                # Fallback selectors
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

                    # Extract product ID from URL
                    product_id_match = re.search(r'-i(\d+)-s(\d+)', href)
                    if product_id_match:
                        product_id = f"{product_id_match.group(1)}-{product_id_match.group(2)}"
                    else:
                        product_id = href.split('/products/')[-1].split('.')[0].split('?')[0]

                    if product_id in seen_ids:
                        continue
                    seen_ids.add(product_id)

                    # Get text content
                    text = await card.inner_text()
                    lines = [l.strip() for l in text.split('\n') if l.strip()]

                    price = 0.0
                    original_price = None
                    name = ""

                    for line in lines:
                        # Price detection
                        if '$' in line or 'S$' in line:
                            match = re.search(r'S?\$\s*([\d,]+\.?\d*)', line)
                            if match:
                                price_val = float(match.group(1).replace(',', ''))
                                if price == 0:
                                    price = price_val
                                elif price_val > price:
                                    original_price = price_val
                        # Name detection (longer text without price indicators)
                        elif len(line) > 10 and '$' not in line and not line.isdigit():
                            if not name and not any(skip in line.lower() for skip in ['sold', 'rating', 'free', 'shipping']):
                                name = line

                    # Check if LazMall
                    is_lazmall = 'lazmall' in text.lower() or await card.query_selector('[class*="lazmall"], [class*="LazMall"]')

                    if name and price > 0:
                        products.append(Product(
                            product_id=product_id,
                            name=name[:200],  # Truncate long names
                            price=price,
                            original_price=original_price,
                            in_stock=True,
                            url=href if href.startswith('http') else f"{self.base_url}{href}",
                            promo_info="LazMall" if is_lazmall else None
                        ))
                except Exception as e:
                    continue

            await browser_page.context.close()

        except Exception as e:
            print(f"Error searching Lazada: {e}")

        return SearchResult(
            platform=self.platform_name,
            query=query,
            products=products,
            total_count=len(products),
            page=page,
            has_more=len(products) >= limit
        )

    async def search_lazmall(
        self,
        query: str,
        limit: int = 20,
        page: int = 1
    ) -> SearchResult:
        """Search specifically in LazMall stores."""
        return await self.search_products(query, limit, page, lazmall_only=True)

    async def get_product_details(self, product_id: str) -> Optional[Product]:
        try:
            browser_page = await self._get_page()

            # Handle different ID formats
            if '-' in product_id:
                item_id, sku_id = product_id.split('-')
                url = f"{self.base_url}/products/-i{item_id}-s{sku_id}.html"
            else:
                url = f"{self.base_url}/products/{product_id}.html"

            await browser_page.goto(url, wait_until="networkidle", timeout=30000)

            # Get product name
            name_elem = await browser_page.query_selector('h1, .pdp-mod-product-badge-title, [data-spm="title"]')
            name = await name_elem.inner_text() if name_elem else ""

            # Get price
            price = 0.0
            price_elem = await browser_page.query_selector('.pdp-price, [data-spm-anchor-id*="price"], .pdp-product-price')
            if price_elem:
                price_text = await price_elem.inner_text()
                match = re.search(r'S?\$\s*([\d,]+\.?\d*)', price_text)
                if match:
                    price = float(match.group(1).replace(',', ''))

            # Get image
            img_elem = await browser_page.query_selector('.pdp-mod-common-image img, .gallery-preview-panel img')
            image_url = await img_elem.get_attribute('src') if img_elem else ""

            # Check stock
            in_stock = True
            oos_elem = await browser_page.query_selector('[class*="out-of-stock"], [class*="sold-out"]')
            if oos_elem:
                in_stock = False

            await browser_page.context.close()

            return Product(
                product_id=product_id,
                name=name.strip(),
                price=price,
                in_stock=in_stock,
                url=url,
                image_url=image_url
            )
        except Exception as e:
            print(f"Error getting Lazada product details: {e}")
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
