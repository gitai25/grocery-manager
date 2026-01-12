"""Amazon Singapore adapter using Product Advertising API and web scraping."""

import asyncio
import re
import hashlib
import hmac
from datetime import datetime
from typing import Optional, List
from urllib.parse import quote_plus, urlencode

import httpx
from playwright.async_api import async_playwright, Browser, Page

from .base import PlatformAdapter, Product, PriceInfo, SearchResult


class AmazonSGAdapter(PlatformAdapter):
    """
    Adapter for Amazon Singapore.

    Supports two modes:
    1. Product Advertising API (requires Associate account)
    2. Web scraping fallback (no account needed)
    """

    platform_name = "amazon_sg"
    base_url = "https://www.amazon.sg"
    api_endpoint = "webservices.amazon.sg"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self._browser: Optional[Browser] = None
        self._playwright = None

        # API credentials (optional)
        self.access_key = config.get("access_key", "") if config else ""
        self.secret_key = config.get("secret_key", "") if config else ""
        self.associate_tag = config.get("associate_tag", "") if config else ""
        self.use_api = bool(self.access_key and self.secret_key and self.associate_tag)

    async def _get_browser(self) -> Browser:
        """Get or create browser instance for scraping."""
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
        page = await context.new_page()
        return page

    async def search_products(
        self,
        query: str,
        limit: int = 20,
        page: int = 1,
        sort_by: str = "relevance"
    ) -> SearchResult:
        """Search for products on Amazon SG."""
        # Always use scraping for search (API has limited free tier)
        return await self._search_via_scraping(query, limit, page, sort_by)

    async def _search_via_scraping(
        self,
        query: str,
        limit: int,
        page_num: int,
        sort_by: str
    ) -> SearchResult:
        """Search products via web scraping."""
        products = []
        total_count = 0

        try:
            browser_page = await self._get_page()

            # Build search URL
            encoded_query = quote_plus(query)
            sort_param = {
                "relevance": "relevanceblender",
                "price_asc": "price-asc-rank",
                "price_desc": "price-desc-rank",
                "popularity": "review-rank"
            }.get(sort_by, "relevanceblender")

            url = f"{self.base_url}/s?k={encoded_query}&s={sort_param}&page={page_num}"
            await browser_page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait for search results
            await browser_page.wait_for_selector('[data-component-type="s-search-result"]', timeout=10000)

            # Extract products
            product_cards = await browser_page.query_selector_all('[data-component-type="s-search-result"]')

            for card in product_cards[:limit]:
                try:
                    product = await self._parse_amazon_product_card(card)
                    if product:
                        products.append(product)
                except Exception as e:
                    continue

            # Try to get total count
            try:
                count_elem = await browser_page.query_selector('.s-breadcrumb .a-text-bold')
                if count_elem:
                    count_text = await count_elem.inner_text()
                    match = re.search(r"([\d,]+)", count_text.replace(",", ""))
                    if match:
                        total_count = int(match.group(1))
            except Exception:
                total_count = len(products)

            await browser_page.context.close()

        except Exception as e:
            print(f"Error searching Amazon SG: {e}")

        return SearchResult(
            platform=self.platform_name,
            query=query,
            products=products,
            total_count=total_count,
            page=page_num,
            has_more=len(products) >= limit
        )

    async def _parse_amazon_product_card(self, card) -> Optional[Product]:
        """Parse an Amazon product card element."""
        try:
            # Get ASIN (product ID)
            asin = await card.get_attribute("data-asin")
            if not asin:
                return None

            # Get product name
            name_elem = await card.query_selector("h2 a span")
            name = await name_elem.inner_text() if name_elem else ""

            # Get price
            price = 0.0
            original_price = None

            # Try whole price
            whole_elem = await card.query_selector(".a-price .a-price-whole")
            fraction_elem = await card.query_selector(".a-price .a-price-fraction")

            if whole_elem:
                whole = await whole_elem.inner_text()
                whole = re.sub(r"[^\d]", "", whole)
                fraction = "00"
                if fraction_elem:
                    fraction = await fraction_elem.inner_text()
                    fraction = re.sub(r"[^\d]", "", fraction)
                price = float(f"{whole}.{fraction}")

            # Get original price (if discounted)
            orig_elem = await card.query_selector(".a-price.a-text-price .a-offscreen")
            if orig_elem:
                orig_text = await orig_elem.inner_text()
                match = re.search(r"\$?([\d,.]+)", orig_text)
                if match:
                    original_price = float(match.group(1).replace(",", ""))

            # Get image
            img_elem = await card.query_selector(".s-image")
            image_url = await img_elem.get_attribute("src") if img_elem else ""

            # Get URL
            link_elem = await card.query_selector("h2 a")
            href = await link_elem.get_attribute("href") if link_elem else ""
            product_url = f"{self.base_url}{href}" if href and not href.startswith("http") else href

            # Get rating
            rating = None
            rating_elem = await card.query_selector(".a-icon-star-small .a-icon-alt")
            if rating_elem:
                rating_text = await rating_elem.inner_text()
                match = re.search(r"([\d.]+)", rating_text)
                if match:
                    rating = float(match.group(1))

            # Get review count
            review_count = None
            review_elem = await card.query_selector('[aria-label*="stars"] + span')
            if review_elem:
                review_text = await review_elem.inner_text()
                match = re.search(r"([\d,]+)", review_text.replace(",", ""))
                if match:
                    review_count = int(match.group(1))

            # Check Prime availability (usually means in stock)
            prime_elem = await card.query_selector('[aria-label="Amazon Prime"]')
            in_stock = prime_elem is not None or price > 0

            return Product(
                product_id=asin,
                name=name.strip(),
                price=price,
                original_price=original_price,
                in_stock=in_stock,
                url=product_url,
                image_url=image_url,
                rating=rating,
                review_count=review_count
            )

        except Exception as e:
            print(f"Error parsing Amazon product: {e}")
            return None

    async def get_product_details(self, product_id: str) -> Optional[Product]:
        """Get detailed product information by ASIN."""
        try:
            browser_page = await self._get_page()
            url = f"{self.base_url}/dp/{product_id}"
            await browser_page.goto(url, wait_until="networkidle", timeout=30000)

            # Get product title
            title_elem = await browser_page.query_selector("#productTitle")
            name = await title_elem.inner_text() if title_elem else ""

            # Get price
            price = 0.0
            price_elem = await browser_page.query_selector(".a-price .a-offscreen")
            if price_elem:
                price_text = await price_elem.inner_text()
                match = re.search(r"\$?([\d,.]+)", price_text)
                if match:
                    price = float(match.group(1).replace(",", ""))

            # Get image
            img_elem = await browser_page.query_selector("#landingImage")
            image_url = await img_elem.get_attribute("src") if img_elem else ""

            # Check availability
            in_stock = True
            avail_elem = await browser_page.query_selector("#availability")
            if avail_elem:
                avail_text = await avail_elem.inner_text()
                in_stock = "in stock" in avail_text.lower()

            # Get rating
            rating = None
            rating_elem = await browser_page.query_selector("#acrPopover")
            if rating_elem:
                rating_text = await rating_elem.get_attribute("title") or ""
                match = re.search(r"([\d.]+)", rating_text)
                if match:
                    rating = float(match.group(1))

            await browser_page.context.close()

            return Product(
                product_id=product_id,
                name=name.strip(),
                price=price,
                in_stock=in_stock,
                url=url,
                image_url=image_url,
                rating=rating
            )

        except Exception as e:
            print(f"Error getting Amazon product details: {e}")
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
        """Generate product URL from ASIN."""
        return f"{self.base_url}/dp/{product_id}"

    async def close(self):
        """Close browser and cleanup."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None
