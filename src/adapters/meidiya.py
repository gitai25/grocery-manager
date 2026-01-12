"""Meidi-Ya adapter for Japanese specialty foods in Singapore."""

import re
from typing import Optional, List
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, Browser, Page

from .base import PlatformAdapter, Product, PriceInfo, SearchResult


class MeidiYaAdapter(PlatformAdapter):
    """
    Adapter for Meidi-Ya - Japanese supermarket and specialty foods in Singapore.
    Known for: Japanese groceries, sake, wagyu beef, sashimi, bento, Japanese snacks.
    """

    platform_name = "meidiya"
    base_url = "https://www.meidi-ya.com.sg"

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
        """Search for products on Meidi-Ya."""
        products = []
        total_count = 0

        try:
            browser_page = await self._get_page()

            # Build search URL
            encoded_query = quote_plus(query)
            sort_param = {
                "relevance": "relevance",
                "price_asc": "price-ascending",
                "price_desc": "price-descending",
                "popularity": "best-selling"
            }.get(sort_by, "relevance")

            url = f"{self.base_url}/search?q={encoded_query}&sort_by={sort_param}&page={page}"
            await browser_page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait for products to load
            try:
                await browser_page.wait_for_selector('.product-card, .product-item, .grid__item', timeout=10000)
            except Exception:
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
            product_cards = await browser_page.query_selector_all('.product-card, .product-item, .grid__item .card')

            for card in product_cards[:limit]:
                try:
                    product = await self._parse_product_card(card)
                    if product:
                        products.append(product)
                except Exception:
                    continue

            # Get total count
            try:
                count_elem = await browser_page.query_selector('.results-count, .collection-product-count')
                if count_elem:
                    count_text = await count_elem.inner_text()
                    match = re.search(r"(\d+)", count_text)
                    if match:
                        total_count = int(match.group(1))
            except Exception:
                total_count = len(products)

            await browser_page.context.close()

        except Exception as e:
            print(f"Error searching Meidi-Ya: {e}")

        return SearchResult(
            platform=self.platform_name,
            query=query,
            products=products,
            total_count=total_count,
            page=page,
            has_more=len(products) >= limit
        )

    async def _parse_product_card(self, card) -> Optional[Product]:
        """Parse a Meidi-Ya product card."""
        try:
            # Get product link
            link_elem = await card.query_selector('a[href*="/products/"]')
            if not link_elem:
                link_elem = await card.query_selector('a.card__link, a.product-link')

            if not link_elem:
                return None

            href = await link_elem.get_attribute("href")
            product_id = ""
            if href and "/products/" in href:
                product_id = href.split("/products/")[-1].split("?")[0]
            elif href:
                product_id = href.split("/")[-1].split("?")[0]

            if not product_id:
                return None

            # Get name
            name_elem = await card.query_selector('.card__heading, .product-card__title, .product-title, h3')
            name = await name_elem.inner_text() if name_elem else ""

            # Get price
            price = 0.0
            price_elem = await card.query_selector('.price-item, .product-price, .money')
            if price_elem:
                price_text = await price_elem.inner_text()
                match = re.search(r"\$?([\d.]+)", price_text)
                if match:
                    price = float(match.group(1))

            # Get original price if on sale
            original_price = None
            compare_elem = await card.query_selector('.price-item--regular, .compare-price, s .money')
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
            sold_out = await card.query_selector('.sold-out, .badge--sold-out')
            if sold_out:
                in_stock = False

            # Build URL
            product_url = href
            if href and not href.startswith("http"):
                product_url = f"{self.base_url}{href}"

            # Get vendor/brand
            brand = None
            vendor_elem = await card.query_selector('.card__vendor, .product-vendor')
            if vendor_elem:
                brand = await vendor_elem.inner_text()

            return Product(
                product_id=product_id,
                name=name.strip(),
                price=price,
                original_price=original_price,
                in_stock=in_stock,
                url=product_url,
                image_url=image_url,
                brand=brand,
                category="japanese"
            )

        except Exception as e:
            print(f"Error parsing Meidi-Ya product: {e}")
            return None

    async def get_product_details(self, product_id: str) -> Optional[Product]:
        """Get detailed product information."""
        try:
            browser_page = await self._get_page()
            url = f"{self.base_url}/products/{product_id}"
            await browser_page.goto(url, wait_until="networkidle", timeout=30000)

            # Get title
            title_elem = await browser_page.query_selector('.product__title, h1')
            name = await title_elem.inner_text() if title_elem else ""

            # Get price
            price = 0.0
            price_elem = await browser_page.query_selector('.price-item--regular, .product__price .money')
            if price_elem:
                price_text = await price_elem.inner_text()
                match = re.search(r"\$?([\d.]+)", price_text)
                if match:
                    price = float(match.group(1))

            # Get image
            img_elem = await browser_page.query_selector('.product__media img, .product-single__photo img')
            image_url = ""
            if img_elem:
                image_url = await img_elem.get_attribute("src") or ""
                if image_url.startswith("//"):
                    image_url = "https:" + image_url

            # Get description
            desc_elem = await browser_page.query_selector('.product__description')
            description = await desc_elem.inner_text() if desc_elem else ""

            # Check stock
            in_stock = True
            add_btn = await browser_page.query_selector('button[name="add"]:not([disabled])')
            if not add_btn:
                in_stock = False

            # Get vendor
            vendor_elem = await browser_page.query_selector('.product__vendor')
            brand = await vendor_elem.inner_text() if vendor_elem else None

            await browser_page.context.close()

            return Product(
                product_id=product_id,
                name=name.strip(),
                price=price,
                in_stock=in_stock,
                url=url,
                image_url=image_url,
                brand=brand
            )

        except Exception as e:
            print(f"Error getting Meidi-Ya product details: {e}")
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
