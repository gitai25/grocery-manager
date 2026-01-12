"""Ryan's Grocery adapter for imported specialty foods in Singapore."""

import re
from typing import Optional, List
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, Browser, Page

from .base import PlatformAdapter, Product, PriceInfo, SearchResult


class RyansGroceryAdapter(PlatformAdapter):
    """
    Adapter for Ryan's Grocery - Imported specialty foods in Singapore.
    Known for: Australian beef, imported cheeses, specialty meats, gourmet items.
    """

    platform_name = "ryans_grocery"
    base_url = "https://ryansgrocery.com"

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
        """Search for products on Ryan's Grocery."""
        products = []
        total_count = 0

        try:
            browser_page = await self._get_page()

            # Build search URL
            encoded_query = quote_plus(query)
            url = f"{self.base_url}/search?q={encoded_query}&page={page}"
            await browser_page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait for products
            try:
                await browser_page.wait_for_selector('.product-card, .product-item, .grid-product', timeout=10000)
            except Exception:
                # No products found
                await browser_page.context.close()
                return SearchResult(
                    platform=self.platform_name,
                    query=query,
                    products=[],
                    total_count=0,
                    page=page,
                    has_more=False
                )

            # Extract products
            product_cards = await browser_page.query_selector_all('.product-card, .product-item, .grid-product')

            for card in product_cards[:limit]:
                try:
                    product = await self._parse_product_card(card)
                    if product:
                        products.append(product)
                except Exception:
                    continue

            # Get total count
            try:
                count_elem = await browser_page.query_selector('.results-count')
                if count_elem:
                    count_text = await count_elem.inner_text()
                    match = re.search(r"(\d+)", count_text)
                    if match:
                        total_count = int(match.group(1))
            except Exception:
                total_count = len(products)

            await browser_page.context.close()

        except Exception as e:
            print(f"Error searching Ryan's Grocery: {e}")

        return SearchResult(
            platform=self.platform_name,
            query=query,
            products=products,
            total_count=total_count,
            page=page,
            has_more=len(products) >= limit
        )

    async def _parse_product_card(self, card) -> Optional[Product]:
        """Parse a Ryan's Grocery product card."""
        try:
            # Get product link and ID
            link_elem = await card.query_selector('a[href*="/products/"]')
            if not link_elem:
                link_elem = await card.query_selector('a')

            if not link_elem:
                return None

            href = await link_elem.get_attribute("href")
            product_id = ""
            if href and "/products/" in href:
                product_id = href.split("/products/")[-1].split("?")[0]
            elif href:
                product_id = href.split("/")[-1].split("?")[0]

            # Get name
            name_elem = await card.query_selector('.product-title, .product-card__title, h3, h2')
            name = await name_elem.inner_text() if name_elem else ""

            # Get price
            price = 0.0
            price_elem = await card.query_selector('.product-price, .price, .money')
            if price_elem:
                price_text = await price_elem.inner_text()
                # Handle "From $X.XX" format
                match = re.search(r"\$?([\d.]+)", price_text)
                if match:
                    price = float(match.group(1))

            # Get original price
            original_price = None
            compare_elem = await card.query_selector('.compare-price, .was-price, s')
            if compare_elem:
                compare_text = await compare_elem.inner_text()
                match = re.search(r"\$?([\d.]+)", compare_text)
                if match:
                    original_price = float(match.group(1))

            # Get image
            img_elem = await card.query_selector('img')
            image_url = ""
            if img_elem:
                image_url = await img_elem.get_attribute("src") or await img_elem.get_attribute("data-src") or ""
                if image_url.startswith("//"):
                    image_url = "https:" + image_url

            # Check stock
            in_stock = True
            sold_out = await card.query_selector('.sold-out, .out-of-stock')
            if sold_out:
                in_stock = False

            # Build URL
            product_url = href
            if href and not href.startswith("http"):
                product_url = f"{self.base_url}{href}"

            # Get weight/size if available
            unit_size = None
            size_elem = await card.query_selector('.product-weight, .product-size, .variant-title')
            if size_elem:
                unit_size = await size_elem.inner_text()

            return Product(
                product_id=product_id,
                name=name.strip(),
                price=price,
                original_price=original_price,
                unit_size=unit_size,
                in_stock=in_stock,
                url=product_url,
                image_url=image_url,
                category="imported"
            )

        except Exception as e:
            print(f"Error parsing Ryan's product: {e}")
            return None

    async def get_product_details(self, product_id: str) -> Optional[Product]:
        """Get detailed product information."""
        try:
            browser_page = await self._get_page()
            url = f"{self.base_url}/products/{product_id}"
            await browser_page.goto(url, wait_until="networkidle", timeout=30000)

            # Get title
            title_elem = await browser_page.query_selector('.product-title, h1')
            name = await title_elem.inner_text() if title_elem else ""

            # Get price
            price = 0.0
            price_elem = await browser_page.query_selector('.product-price .money, .price')
            if price_elem:
                price_text = await price_elem.inner_text()
                match = re.search(r"\$?([\d.]+)", price_text)
                if match:
                    price = float(match.group(1))

            # Get image
            img_elem = await browser_page.query_selector('.product-image img, .product-photo img')
            image_url = ""
            if img_elem:
                image_url = await img_elem.get_attribute("src") or ""
                if image_url.startswith("//"):
                    image_url = "https:" + image_url

            # Check stock
            in_stock = True
            add_btn = await browser_page.query_selector('button[type="submit"]:not([disabled]), .add-to-cart:not(.disabled)')
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
            print(f"Error getting Ryan's product details: {e}")
            return None

    async def get_price(self, product_id: str) -> Optional[PriceInfo]:
        """Get current price for a product."""
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
        """Generate product URL."""
        return f"{self.base_url}/products/{product_id}"

    async def close(self):
        """Close browser and cleanup."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None
