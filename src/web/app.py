"""Web application for Grocery Manager dashboard."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from ..core.database import AsyncSessionLocal, init_db
from ..services.watchlist_service import WatchlistService
from ..adapters import PLATFORM_DISPLAY_NAMES

app = FastAPI(title="Grocery Manager", version="1.0.0")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your Cloudflare Pages domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup templates
templates_dir = Path(__file__).parent / "templates"
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))

# Static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# Product images mapping
PRODUCT_IMAGES = {
    "José Gourmet": "https://www.fossaprovisions.com/cdn/shop/products/jose-gourmet-small-mackerel-in-olive-oil-120g.jpg",
    "The Stock Merchant": "https://thestockmerchant.com.au/cdn/shop/products/MSC-Sardines-in-Organic-EVOO-120g.jpg",
    "Good Fish": "https://good-fish.com.au/wp-content/uploads/2021/05/GF_Sardines_EVOO_Can.png",
    "NURI": "https://m.media-amazon.com/images/I/71qWDGzL8ZL._SL1500_.jpg",
    "Ortiz": "https://m.media-amazon.com/images/I/71YVY2QxX0L._SL1500_.jpg",
    "Ramón Peña": "https://lata.shop/cdn/shop/products/Ramon-Pena-Sardines-in-Olive-Oil.jpg",
}


@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    await init_db()


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard showing watchlist status."""
    async with AsyncSessionLocal() as db:
        service = WatchlistService(db)
        items = await service.get_all_items()
        alerts = await service.get_unread_alerts()

    # Process items for display
    watchlist_data = []
    for item in items:
        # Get availability info
        availability = item.availability_status or {}
        available_platforms = []
        best_price = None
        best_platform = None

        for platform, status in availability.items():
            if status.get("in_stock"):
                available_platforms.append({
                    "name": PLATFORM_DISPLAY_NAMES.get(platform, platform),
                    "price": status.get("price"),
                    "url": status.get("url", ""),
                })
                if status.get("price"):
                    if best_price is None or status["price"] < best_price:
                        best_price = status["price"]
                        best_platform = platform

        watchlist_data.append({
            "id": item.id,
            "brand": item.brand,
            "name": item.name,
            "category": item.category,
            "origin": item.origin_country,
            "size": item.size,
            "score": item.foodguard_score,
            "weekly_qty": item.weekly_target_qty,
            "max_price": item.max_price,
            "image": PRODUCT_IMAGES.get(item.brand, ""),
            "is_available": item.is_available_anywhere,
            "available_platforms": available_platforms,
            "best_price": best_price,
            "best_platform": PLATFORM_DISPLAY_NAMES.get(best_platform, best_platform) if best_platform else None,
            "last_checked": item.last_checked_at.strftime("%Y-%m-%d %H:%M") if item.last_checked_at else "未检查",
            "notes": item.notes,
        })

    # Stats
    total = len(watchlist_data)
    available_count = sum(1 for w in watchlist_data if w["is_available"])
    unavailable_count = total - available_count

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "watchlist": watchlist_data,
        "alerts": alerts[:10],  # Last 10 alerts
        "stats": {
            "total": total,
            "available": available_count,
            "unavailable": unavailable_count,
        },
        "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "platform_names": PLATFORM_DISPLAY_NAMES,
    })


@app.get("/api/watchlist")
async def api_watchlist():
    """API endpoint for watchlist data."""
    async with AsyncSessionLocal() as db:
        service = WatchlistService(db)
        items = await service.get_all_items()
        alerts = await service.get_unread_alerts()

    items_data = [{
        "id": item.id,
        "brand": item.brand,
        "name": item.name,
        "category": item.category,
        "origin_country": item.origin_country,
        "size": item.size,
        "foodguard_score": item.foodguard_score,
        "weekly_target_qty": item.weekly_target_qty,
        "max_price": item.max_price,
        "is_available_anywhere": item.is_available_anywhere,
        "current_best_price": item.current_best_price,
        "current_best_platform": item.current_best_platform,
        "availability_status": item.availability_status or {},
        "last_checked_at": item.last_checked_at.isoformat() if item.last_checked_at else None,
        "notes": item.notes,
    } for item in items]

    alerts_data = [{
        "id": alert.id,
        "alert_type": alert.alert_type,
        "platform": alert.platform,
        "message": alert.message,
        "old_price": alert.old_price,
        "new_price": alert.new_price,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    } for alert in alerts]

    return {
        "items": items_data,
        "alerts": alerts_data,
        "last_updated": datetime.now().isoformat(),
    }


@app.post("/api/watchlist/check")
async def api_check_watchlist():
    """Trigger availability check for all watchlist items."""
    async with AsyncSessionLocal() as db:
        service = WatchlistService(db)
        results = await service.check_all_items()

    return {
        "success": True,
        "checked": len(results),
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/api/check/{item_id}")
async def api_check_item(item_id: int):
    """Trigger availability check for a specific item."""
    async with AsyncSessionLocal() as db:
        service = WatchlistService(db)
        item = await service.get_item(item_id)
        if not item:
            return {"error": "Item not found"}

        results = await service.check_availability(item)
        return {
            "item_id": item_id,
            "brand": item.brand,
            "name": item.name,
            "results": results,
            "is_available": item.is_available_anywhere,
        }


@app.post("/api/check-all")
async def api_check_all():
    """Trigger availability check for all items."""
    async with AsyncSessionLocal() as db:
        service = WatchlistService(db)
        results = await service.check_all_items()
        return {"checked": len(results), "results": results}


def run_server(host: str = "0.0.0.0", port: int = 8080):
    """Run the web server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
