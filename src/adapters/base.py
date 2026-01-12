"""Base adapter class for e-commerce platforms."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class Product:
    """Product data from a platform."""
    product_id: str
    name: str
    price: float
    original_price: Optional[float] = None
    unit_price: Optional[float] = None
    unit_size: Optional[str] = None
    in_stock: bool = True
    stock_quantity: Optional[int] = None
    url: str = ""
    image_url: str = ""
    rating: Optional[float] = None
    review_count: Optional[int] = None
    sold_count: Optional[int] = None
    promo_info: Optional[str] = None
    delivery_fee: Optional[float] = None
    category: Optional[str] = None
    brand: Optional[str] = None


@dataclass
class PriceInfo:
    """Price information for a product."""
    product_id: str
    price: float
    original_price: Optional[float] = None
    in_stock: bool = True
    promo_info: Optional[str] = None
    checked_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SearchResult:
    """Search results from a platform."""
    platform: str
    query: str
    products: List[Product]
    total_count: int
    page: int = 1
    has_more: bool = False


class PlatformAdapter(ABC):
    """Abstract base class for platform adapters."""

    platform_name: str = "unknown"
    base_url: str = ""

    def __init__(self, config: dict = None):
        """Initialize adapter with optional config."""
        self.config = config or {}

    @abstractmethod
    async def search_products(
        self,
        query: str,
        limit: int = 20,
        page: int = 1,
        sort_by: str = "relevance"
    ) -> SearchResult:
        """
        Search for products on the platform.

        Args:
            query: Search query string
            limit: Maximum number of results to return
            page: Page number for pagination
            sort_by: Sort order (relevance, price_asc, price_desc, popularity)

        Returns:
            SearchResult with list of products
        """
        pass

    @abstractmethod
    async def get_product_details(self, product_id: str) -> Optional[Product]:
        """
        Get detailed information about a product.

        Args:
            product_id: Platform-specific product ID

        Returns:
            Product details or None if not found
        """
        pass

    @abstractmethod
    async def get_price(self, product_id: str) -> Optional[PriceInfo]:
        """
        Get current price for a product.

        Args:
            product_id: Platform-specific product ID

        Returns:
            PriceInfo or None if not found
        """
        pass

    async def add_to_cart(self, product_id: str, quantity: int = 1) -> bool:
        """
        Add a product to the cart (if supported).

        Args:
            product_id: Platform-specific product ID
            quantity: Quantity to add

        Returns:
            True if successful, False otherwise
        """
        raise NotImplementedError(f"{self.platform_name} does not support add to cart via API")

    async def create_order(self, items: List[dict]) -> dict:
        """
        Create an order (if supported).

        Args:
            items: List of items with product_id and quantity

        Returns:
            Order details dict
        """
        raise NotImplementedError(f"{self.platform_name} does not support order creation via API")

    def get_product_url(self, product_id: str) -> str:
        """Generate product URL from ID."""
        return f"{self.base_url}/product/{product_id}"

    async def close(self):
        """Cleanup resources (override if needed)."""
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
