"""Platform adapters for various e-commerce sites in Singapore."""

from .base import PlatformAdapter, Product, PriceInfo, SearchResult

# Mainstream platforms
from .fairprice import FairPriceAdapter
from .amazon_sg import AmazonSGAdapter
from .lazada_sg import LazadaSGAdapter
from .redmart import RedMartAdapter

# Specialty/Premium stores
from .iherb import iHerbAdapter
from .little_farms import LittleFarmsAdapter
from .ryans_grocery import RyansGroceryAdapter
from .meidiya import MeidiYaAdapter

# Organic supermarkets
from .straits_market import StraitsMarketAdapter
from .zenxin import ZenxinAdapter

# Premium butchers
from .hubers import HubersAdapter
from .meat_club import MeatClubAdapter
from .meatery import MeateryAdapter
from .prime_butchery import PrimeButcheryAdapter

# Seafood specialists
from .greenwood_fish import GreenwoodFishAdapter
from .shiki import ShikiAdapter
from .fisk import FiskAdapter
from .fishwives import FishwivesAdapter
from .kuhlbarra import KuhlbarraAdapter

# Farm direct
from .avo_co import AvoCoAdapter
from .quan_fa import QuanFaAdapter


# Registry of all available adapters
ADAPTERS = {
    # Mainstream
    "fairprice": FairPriceAdapter,
    "amazon_sg": AmazonSGAdapter,
    "lazada_sg": LazadaSGAdapter,
    "redmart": RedMartAdapter,
    # Specialty
    "iherb": iHerbAdapter,
    "little_farms": LittleFarmsAdapter,
    "ryans_grocery": RyansGroceryAdapter,
    "meidiya": MeidiYaAdapter,
    # Organic
    "straits_market": StraitsMarketAdapter,
    "zenxin": ZenxinAdapter,
    # Butchers
    "hubers": HubersAdapter,
    "meat_club": MeatClubAdapter,
    "meatery": MeateryAdapter,
    "prime_butchery": PrimeButcheryAdapter,
    # Seafood
    "greenwood_fish": GreenwoodFishAdapter,
    "shiki": ShikiAdapter,
    "fisk": FiskAdapter,
    "fishwives": FishwivesAdapter,
    "kuhlbarra": KuhlbarraAdapter,
    # Farm direct
    "avo_co": AvoCoAdapter,
    "quan_fa": QuanFaAdapter,
}

# Category mapping for display
PLATFORM_CATEGORIES = {
    "mainstream": ["fairprice", "amazon_sg", "lazada_sg", "redmart"],
    "specialty": ["iherb", "little_farms", "ryans_grocery", "meidiya"],
    "organic": ["straits_market", "zenxin"],
    "butcher": ["hubers", "meat_club", "meatery", "prime_butchery"],
    "seafood": ["greenwood_fish", "shiki", "fisk", "fishwives", "kuhlbarra"],
    "farm": ["avo_co", "quan_fa"],
}

PLATFORM_DISPLAY_NAMES = {
    "fairprice": "FairPrice",
    "amazon_sg": "Amazon SG",
    "lazada_sg": "Lazada SG (LazMall)",
    "redmart": "RedMart",
    "iherb": "iHerb",
    "little_farms": "Little Farms",
    "ryans_grocery": "Ryan's Grocery",
    "meidiya": "Meidi-Ya",
    "straits_market": "Straits Market",
    "zenxin": "Zenxin Organic",
    "hubers": "Huber's Butchery",
    "meat_club": "The Meat Club",
    "meatery": "The Meatery (Halal)",
    "prime_butchery": "Prime Butchery",
    "greenwood_fish": "Greenwood Fish Market",
    "shiki": "Shiki (四季)",
    "fisk": "Fisk (Snorre Food)",
    "fishwives": "The Fishwives",
    "kuhlbarra": "Kuhlbarra",
    "avo_co": "Avo & Co",
    "quan_fa": "Quan Fa Organic Farm",
}


def get_adapter(platform_name: str, config: dict = None) -> PlatformAdapter:
    """
    Get an adapter instance by platform name.

    Args:
        platform_name: Name of the platform (e.g., 'fairprice', 'amazon_sg')
        config: Optional configuration dict for the adapter

    Returns:
        PlatformAdapter instance

    Raises:
        ValueError: If platform name is not recognized
    """
    adapter_class = ADAPTERS.get(platform_name.lower())
    if not adapter_class:
        available = ", ".join(ADAPTERS.keys())
        raise ValueError(f"Unknown platform: {platform_name}. Available: {available}")

    return adapter_class(config)


def get_all_adapters(configs: dict = None) -> dict:
    """
    Get instances of all available adapters.

    Args:
        configs: Dict of platform_name -> config dict

    Returns:
        Dict of platform_name -> adapter instance
    """
    configs = configs or {}
    return {
        name: cls(configs.get(name, {}))
        for name, cls in ADAPTERS.items()
    }


def get_adapters_by_category(category: str, configs: dict = None) -> dict:
    """
    Get adapter instances for a specific category.

    Args:
        category: Category name (mainstream, specialty, organic, butcher, seafood, farm)
        configs: Dict of platform_name -> config dict

    Returns:
        Dict of platform_name -> adapter instance
    """
    configs = configs or {}
    platform_names = PLATFORM_CATEGORIES.get(category, [])
    return {
        name: ADAPTERS[name](configs.get(name, {}))
        for name in platform_names
        if name in ADAPTERS
    }


__all__ = [
    # Base classes
    "PlatformAdapter",
    "Product",
    "PriceInfo",
    "SearchResult",
    # Mainstream Adapters
    "FairPriceAdapter",
    "AmazonSGAdapter",
    "LazadaSGAdapter",
    "RedMartAdapter",
    # Specialty Adapters
    "iHerbAdapter",
    "LittleFarmsAdapter",
    "RyansGroceryAdapter",
    "MeidiYaAdapter",
    # Organic Adapters
    "StraitsMarketAdapter",
    "ZenxinAdapter",
    # Butcher Adapters
    "HubersAdapter",
    "MeatClubAdapter",
    "MeateryAdapter",
    "PrimeButcheryAdapter",
    # Seafood Adapters
    "GreenwoodFishAdapter",
    "ShikiAdapter",
    "FiskAdapter",
    "FishwivesAdapter",
    "KuhlbarraAdapter",
    # Farm Adapters
    "AvoCoAdapter",
    "QuanFaAdapter",
    # Utilities
    "ADAPTERS",
    "PLATFORM_CATEGORIES",
    "PLATFORM_DISPLAY_NAMES",
    "get_adapter",
    "get_all_adapters",
    "get_adapters_by_category",
]
