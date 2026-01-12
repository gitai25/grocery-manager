"""iHerb adapter for health supplements and vitamins."""

import re
from typing import Optional, List
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, Browser, Page

from .base import PlatformAdapter, Product, PriceInfo, SearchResult


class iHerbAdapter(PlatformAdapter):
    """
    Adapter for iHerb - Health supplements, vitamins, and wellness products.
    Uses web scraping as iHerb's affiliate API has limited functionality.
    """

    platform_name = "iherb"
    base_url = "https://sg.iherb.com"  # Singapore site

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
            viewport={"width": 1920, "height": 1080},
            locale="en-SG"
        )
        # Set currency to SGD
        await context.add_cookies([{
            "name": "iher-pref1",
            "value": "ctd=SGD&sccode=SG&lan=en-US",
            "domain": ".iherb.com",
            "path": "/"
        }])
        page = await context.new_page()
        return page

    async def search_products(
        self,
        query: str,
        limit: int = 20,
        page: int = 1,
        sort_by: str = "relevance"
    ) -> SearchResult:
        """Search for products on iHerb."""
        products = []
        total_count = 0

        try:
            browser_page = await self._get_page()

            # Build search URL
            encoded_query = quote_plus(query)
            sort_param = {
                "relevance": "0",
                "price_asc": "3",
                "price_desc": "4",
                "popularity": "2"
            }.get(sort_by, "0")

            url = f"{self.base_url}/search?kw={encoded_query}&srt={sort_param}&p={page}"
            await browser_page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait for product grid
            await browser_page.wait_for_selector('[data-ga-product-tile]', timeout=10000)

            # Extract products
            product_cards = await browser_page.query_selector_all('[data-ga-product-tile]')

            for card in product_cards[:limit]:
                try:
                    product = await self._parse_iherb_product_card(card)
                    if product:
                        products.append(product)
                except Exception:
                    continue

            # Get total count
            try:
                count_elem = await browser_page.query_selector('.sub-header-title span')
                if count_elem:
                    count_text = await count_elem.inner_text()
                    match = re.search(r"([\d,]+)", count_text.replace(",", ""))
                    if match:
                        total_count = int(match.group(1))
            except Exception:
                total_count = len(products)

            await browser_page.context.close()

        except Exception as e:
            print(f"Error searching iHerb: {e}")

        return SearchResult(
            platform=self.platform_name,
            query=query,
            products=products,
            total_count=total_count,
            page=page,
            has_more=len(products) >= limit
        )

    async def _parse_iherb_product_card(self, card) -> Optional[Product]:
        """Parse an iHerb product card element."""
        try:
            # Get product ID
            product_id = await card.get_attribute("data-product-id")
            if not product_id:
                # Try from link
                link = await card.query_selector("a.absolute-link-wrapper")
                if link:
                    href = await link.get_attribute("href")
                    if href:
                        match = re.search(r"/([A-Z]{3}\d+)", href)
                        if match:
                            product_id = match.group(1)

            if not product_id:
                return None

            # Get name
            name_elem = await card.query_selector('[data-ga="productTileProductNameLink"]')
            name = await name_elem.inner_text() if name_elem else ""

            # Get brand
            brand_elem = await card.query_selector('[data-ga="productTileBrandLink"]')
            brand = await brand_elem.inner_text() if brand_elem else ""

            # Get price (SGD)
            price = 0.0
            price_elem = await card.query_selector('[data-ga="product-tile-price"]')
            if price_elem:
                price_text = await price_elem.inner_text()
                match = re.search(r"S?\$?([\d.]+)", price_text)
                if match:
                    price = float(match.group(1))

            # Get original price
            original_price = None
            orig_elem = await card.query_selector('.price-olp')
            if orig_elem:
                orig_text = await orig_elem.inner_text()
                match = re.search(r"S?\$?([\d.]+)", orig_text)
                if match:
                    original_price = float(match.group(1))

            # Get discount percentage
            discount = None
            discount_elem = await card.query_selector('.discount-badge, .product-discount')
            if discount_elem:
                discount_text = await discount_elem.inner_text()
                match = re.search(r"(\d+)%", discount_text)
                if match:
                    discount = float(match.group(1))

            # Get image
            img_elem = await card.query_selector('img')
            image_url = await img_elem.get_attribute("src") if img_elem else ""

            # Get rating
            rating = None
            rating_elem = await card.query_selector('[itemprop="ratingValue"]')
            if rating_elem:
                rating_text = await rating_elem.get_attribute("content")
                if rating_text:
                    rating = float(rating_text)

            # Get review count
            review_count = None
            review_elem = await card.query_selector('[itemprop="reviewCount"]')
            if review_elem:
                review_text = await review_elem.get_attribute("content")
                if review_text:
                    review_count = int(review_text)

            # Check stock
            in_stock = True
            oos_elem = await card.query_selector('.out-of-stock-text')
            if oos_elem:
                in_stock = False

            # Get URL
            link_elem = await card.query_selector('a.absolute-link-wrapper')
            href = await link_elem.get_attribute("href") if link_elem else ""
            product_url = f"{self.base_url}{href}" if href and not href.startswith("http") else href

            return Product(
                product_id=product_id,
                name=f"{brand} - {name}".strip(" -") if brand else name.strip(),
                price=price,
                original_price=original_price,
                in_stock=in_stock,
                url=product_url,
                image_url=image_url,
                rating=rating,
                review_count=review_count,
                brand=brand,
                promo_info=f"{discount}% off" if discount else None
            )

        except Exception as e:
            print(f"Error parsing iHerb product: {e}")
            return None

    async def get_product_details(self, product_id: str) -> Optional[Product]:
        """Get detailed product information."""
        try:
            browser_page = await self._get_page()
            url = f"{self.base_url}/pr/{product_id}"
            await browser_page.goto(url, wait_until="networkidle", timeout=30000)

            # Get title
            title_elem = await browser_page.query_selector('#name')
            name = await title_elem.inner_text() if title_elem else ""

            # Get brand
            brand_elem = await browser_page.query_selector('[itemprop="brand"]')
            brand = await brand_elem.inner_text() if brand_elem else ""

            # Get price
            price = 0.0
            price_elem = await browser_page.query_selector('#price')
            if price_elem:
                price_text = await price_elem.inner_text()
                match = re.search(r"S?\$?([\d.]+)", price_text)
                if match:
                    price = float(match.group(1))

            # Get image
            img_elem = await browser_page.query_selector('#iherb-product-image')
            image_url = await img_elem.get_attribute("src") if img_elem else ""

            # Check stock
            in_stock = True
            oos_elem = await browser_page.query_selector('.out-of-stock')
            if oos_elem:
                in_stock = False

            # Get rating
            rating = None
            rating_elem = await browser_page.query_selector('[itemprop="ratingValue"]')
            if rating_elem:
                rating_text = await rating_elem.get_attribute("content")
                if rating_text:
                    rating = float(rating_text)

            await browser_page.context.close()

            return Product(
                product_id=product_id,
                name=f"{brand} - {name}".strip(" -") if brand else name.strip(),
                price=price,
                in_stock=in_stock,
                url=url,
                image_url=image_url,
                rating=rating,
                brand=brand
            )

        except Exception as e:
            print(f"Error getting iHerb product details: {e}")
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
        return f"{self.base_url}/pr/{product_id}"

    async def close(self):
        """Close browser and cleanup."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None
