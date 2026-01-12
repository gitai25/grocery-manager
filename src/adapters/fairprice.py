"""FairPrice adapter using web scraping."""

import asyncio
import re
from typing import Optional, List
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, Browser, Page

from .base import PlatformAdapter, Product, PriceInfo, SearchResult


class FairPriceAdapter(PlatformAdapter):
    """Adapter for NTUC FairPrice Online."""

    platform_name = "fairprice"
    base_url = "https://www.fairprice.com.sg"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self._browser: Optional[Browser] = None
        self._playwright = None

    async def _get_browser(self) -> Browser:
        """Get or create browser instance."""
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
        return self._browser

    async def _get_page(self) -> Page:
        """Create a new page with proper settings."""
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
        sort_by: str = "relevance"
    ) -> SearchResult:
        """Search for products on FairPrice."""
        products = []
        total_count = 0

        try:
            browser_page = await self._get_page()

            # Build search URL
            encoded_query = quote_plus(query)
            sort_param = {
                "relevance": "relevance",
                "price_asc": "price_asc",
                "price_desc": "price_desc",
                "popularity": "popularity"
            }.get(sort_by, "relevance")

            url = f"{self.base_url}/search?query={encoded_query}&sort={sort_param}&page={page}"
            await browser_page.goto(url, wait_until="domcontentloaded", timeout=45000)

            # Wait for product grid to load - try multiple selectors
            try:
                await browser_page.wait_for_selector('[data-testid="product-card"], .product-card, .sc-product-card', timeout=15000)
            except Exception:
                # Try waiting for any product link
                await browser_page.wait_for_selector('a[href*="/product/"]', timeout=10000)

            # Extract products using product links
            product_links = await browser_page.query_selector_all('a[href*="/product/"]')

            seen_ids = set()
            for link in product_links:
                if len(products) >= limit:
                    break
                try:
                    href = await link.get_attribute('href')
                    if not href or '/product/' not in href:
                        continue

                    product_id = href.split('/product/')[-1].split('?')[0].rstrip('-')
                    if product_id in seen_ids:
                        continue
                    seen_ids.add(product_id)

                    # Get text content which includes price and name
                    text = await link.inner_text()
                    lines = [l.strip() for l in text.split('\n') if l.strip()]

                    # Parse price and name from text
                    price = 0.0
                    name = ""
                    for line in lines:
                        if line.startswith('$'):
                            match = re.search(r'\$([\d.]+)', line)
                            if match and price == 0:
                                price = float(match.group(1))
                        elif len(line) > 5 and not line.startswith('$'):
                            if not name:
                                name = line

                    if name and price > 0:
                        products.append(Product(
                            product_id=product_id,
                            name=name,
                            price=price,
                            in_stock=True,
                            url=f"{self.base_url}{href}" if not href.startswith('http') else href
                        ))
                except Exception:
                    continue

            # Try to get total count
            try:
                count_elem = await browser_page.query_selector('[data-testid="search-results-count"]')
                if count_elem:
                    count_text = await count_elem.inner_text()
                    match = re.search(r"(\d+)", count_text.replace(",", ""))
                    if match:
                        total_count = int(match.group(1))
            except Exception:
                total_count = len(products)

            await browser_page.context.close()

        except Exception as e:
            print(f"Error searching FairPrice: {e}")

        return SearchResult(
            platform=self.platform_name,
            query=query,
            products=products,
            total_count=total_count,
            page=page,
            has_more=len(products) >= limit
        )

    async def _parse_product_card(self, card) -> Optional[Product]:
        """Parse a product card element."""
        try:
            # Get product ID from link
            link_elem = await card.query_selector("a[href*='/product/']")
            if not link_elem:
                return None

            href = await link_elem.get_attribute("href")
            product_id = href.split("/product/")[-1].split("?")[0] if href else ""

            # Get name
            name_elem = await card.query_selector('[data-testid="product-name"]')
            name = await name_elem.inner_text() if name_elem else ""

            # Get price
            price = 0.0
            original_price = None

            price_elem = await card.query_selector('[data-testid="product-price"]')
            if price_elem:
                price_text = await price_elem.inner_text()
                price_match = re.search(r"\$?([\d.]+)", price_text)
                if price_match:
                    price = float(price_match.group(1))

            # Get original price if discounted
            orig_price_elem = await card.query_selector('[data-testid="original-price"]')
            if orig_price_elem:
                orig_text = await orig_price_elem.inner_text()
                orig_match = re.search(r"\$?([\d.]+)", orig_text)
                if orig_match:
                    original_price = float(orig_match.group(1))

            # Get image
            img_elem = await card.query_selector("img")
            image_url = await img_elem.get_attribute("src") if img_elem else ""

            # Check stock status
            in_stock = True
            oos_elem = await card.query_selector('[data-testid="out-of-stock"]')
            if oos_elem:
                in_stock = False

            # Get unit size
            unit_elem = await card.query_selector('[data-testid="product-size"]')
            unit_size = await unit_elem.inner_text() if unit_elem else None

            # Calculate unit price
            unit_price = None
            if price and unit_size:
                unit_price = self._calculate_unit_price(price, unit_size)

            return Product(
                product_id=product_id,
                name=name.strip(),
                price=price,
                original_price=original_price,
                unit_price=unit_price,
                unit_size=unit_size,
                in_stock=in_stock,
                url=f"{self.base_url}{href}" if href else "",
                image_url=image_url
            )

        except Exception as e:
            print(f"Error parsing product card: {e}")
            return None

    def _calculate_unit_price(self, price: float, size_str: str) -> Optional[float]:
        """Calculate unit price from size string."""
        size_str = size_str.lower().strip()

        # Parse quantity and unit
        match = re.match(r"(\d+(?:\.\d+)?)\s*(kg|g|l|ml|pcs?|pieces?|pack|each)", size_str)
        if not match:
            return None

        quantity = float(match.group(1))
        unit = match.group(2)

        if quantity == 0:
            return None

        # Convert to standard units (per kg or per L)
        if unit == "g":
            return (price / quantity) * 1000  # per kg
        elif unit == "kg":
            return price / quantity  # per kg
        elif unit == "ml":
            return (price / quantity) * 1000  # per L
        elif unit == "l":
            return price / quantity  # per L
        elif unit in ("pc", "pcs", "piece", "pieces", "pack", "each"):
            return price / quantity  # per piece

        return None

    async def get_product_details(self, product_id: str) -> Optional[Product]:
        """Get detailed product information."""
        try:
            browser_page = await self._get_page()
            url = f"{self.base_url}/product/{product_id}"
            await browser_page.goto(url, wait_until="networkidle", timeout=30000)

            # Extract product details
            name_elem = await browser_page.query_selector("h1[data-testid='product-title']")
            name = await name_elem.inner_text() if name_elem else ""

            price_elem = await browser_page.query_selector('[data-testid="product-price"]')
            price = 0.0
            if price_elem:
                price_text = await price_elem.inner_text()
                match = re.search(r"\$?([\d.]+)", price_text)
                if match:
                    price = float(match.group(1))

            img_elem = await browser_page.query_selector('[data-testid="product-image"] img')
            image_url = await img_elem.get_attribute("src") if img_elem else ""

            # Check stock
            in_stock = True
            add_btn = await browser_page.query_selector('[data-testid="add-to-cart"]')
            if not add_btn:
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
            print(f"Error getting product details: {e}")
            return None

    async def get_price(self, product_id: str) -> Optional[PriceInfo]:
        """Get current price for a product."""
        product = await self.get_product_details(product_id)
        if product:
            return PriceInfo(
                product_id=product_id,
                price=product.price,
                original_price=product.original_price,
                in_stock=product.in_stock,
                promo_info=product.promo_info
            )
        return None

    def get_product_url(self, product_id: str) -> str:
        """Generate product URL from ID."""
        return f"{self.base_url}/product/{product_id}"

    async def close(self):
        """Close browser and cleanup."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None
