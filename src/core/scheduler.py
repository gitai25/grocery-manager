"""Task scheduler for automated jobs."""

import asyncio
from datetime import datetime
from typing import Callable, Dict, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from .config import settings
from .database import AsyncSessionLocal


class TaskScheduler:
    """Scheduler for automated background tasks."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.jobs: Dict[str, Any] = {}

    def start(self):
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            print("Scheduler started")

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            print("Scheduler stopped")

    def add_interval_job(
        self,
        func: Callable,
        job_id: str,
        hours: int = 1,
        minutes: int = 0,
        **kwargs
    ):
        """Add a job that runs at fixed intervals."""
        trigger = IntervalTrigger(hours=hours, minutes=minutes)
        job = self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            **kwargs
        )
        self.jobs[job_id] = job
        print(f"Added interval job: {job_id} (every {hours}h {minutes}m)")
        return job

    def add_cron_job(
        self,
        func: Callable,
        job_id: str,
        hour: int = 0,
        minute: int = 0,
        day_of_week: str = "*",
        **kwargs
    ):
        """Add a job that runs on a cron schedule."""
        trigger = CronTrigger(
            hour=hour,
            minute=minute,
            day_of_week=day_of_week
        )
        job = self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            **kwargs
        )
        self.jobs[job_id] = job
        print(f"Added cron job: {job_id} (at {hour}:{minute:02d})")
        return job

    def remove_job(self, job_id: str):
        """Remove a scheduled job."""
        if job_id in self.jobs:
            self.scheduler.remove_job(job_id)
            del self.jobs[job_id]
            print(f"Removed job: {job_id}")

    def get_jobs(self) -> list:
        """Get all scheduled jobs."""
        return self.scheduler.get_jobs()

    def run_job_now(self, job_id: str):
        """Run a job immediately."""
        job = self.scheduler.get_job(job_id)
        if job:
            job.modify(next_run_time=datetime.now())
            print(f"Triggered job: {job_id}")


# Task implementations

async def task_monitor_prices():
    """Monitor prices for all inventory items."""
    from ..services.inventory_service import InventoryService
    from ..services.price_service import PriceService
    from ..adapters.fairprice import FairPriceAdapter

    print(f"[{datetime.now()}] Starting price monitoring...")

    async with AsyncSessionLocal() as db:
        inventory_service = InventoryService(db)
        items = await inventory_service.get_all_items()

        adapters = {"fairprice": FairPriceAdapter()}
        price_service = PriceService(db, adapters)

        updated_count = 0
        for item in items:
            try:
                records = await price_service.update_prices_for_item(item)
                updated_count += len(records)
            except Exception as e:
                print(f"Error updating prices for {item.name}: {e}")

        await db.commit()

        # Cleanup
        for adapter in adapters.values():
            await adapter.close()

    print(f"[{datetime.now()}] Price monitoring complete. Updated {updated_count} records.")


async def task_check_inventory():
    """Check inventory levels and generate alerts."""
    from ..services.inventory_service import InventoryService

    print(f"[{datetime.now()}] Checking inventory levels...")

    async with AsyncSessionLocal() as db:
        service = InventoryService(db)

        low_stock = await service.get_low_stock_items()
        expiring = await service.get_expiring_items(days=7)

        if low_stock:
            print(f"Low stock items: {len(low_stock)}")
            for item in low_stock:
                print(f"  - {item.name}: {item.current_quantity} {item.unit or ''}")

        if expiring:
            print(f"Expiring items: {len(expiring)}")
            for item in expiring:
                print(f"  - {item.name}: expires {item.expiry_date}")

    print(f"[{datetime.now()}] Inventory check complete.")


async def task_generate_shopping_list():
    """Auto-generate weekly shopping list."""
    from ..services.shopping_service import ShoppingService

    print(f"[{datetime.now()}] Generating shopping list...")

    async with AsyncSessionLocal() as db:
        service = ShoppingService(db)
        shopping_list = await service.generate_list_from_inventory()

        if shopping_list:
            await db.commit()
            print(f"Generated shopping list with {len(shopping_list.items)} items")
        else:
            print("No items need restocking")

    print(f"[{datetime.now()}] Shopping list generation complete.")


async def task_check_promotions():
    """Check for price drops and promotions."""
    from ..services.price_service import PriceService

    print(f"[{datetime.now()}] Checking promotions...")

    async with AsyncSessionLocal() as db:
        price_service = PriceService(db)
        alerts = await price_service.get_price_alerts(threshold_percent=10)

        if alerts:
            print(f"Found {len(alerts)} price drop alerts:")
            for alert in alerts:
                print(
                    f"  - {alert['item'].name}: "
                    f"${alert['previous_price']:.2f} -> ${alert['current_price']:.2f} "
                    f"({alert['change_percent']:.1f}%)"
                )

    print(f"[{datetime.now()}] Promotion check complete.")


async def task_check_watchlist():
    """Check watchlist items for availability across platforms."""
    from ..services.watchlist_service import WatchlistService

    print(f"[{datetime.now()}] Checking watchlist availability...")

    async with AsyncSessionLocal() as db:
        service = WatchlistService(db)
        items = await service.get_all_items()

        if not items:
            print("No watchlist items configured")
            return

        available_count = 0
        alert_count = 0

        for item in items:
            try:
                await service.check_availability(item)
                if item.is_available_anywhere:
                    available_count += 1
            except Exception as e:
                print(f"Error checking {item.brand} {item.name}: {e}")

        # Check for new alerts
        alerts = await service.get_unread_alerts()
        alert_count = len(alerts)

        print(f"[{datetime.now()}] Watchlist check complete.")
        print(f"  Available: {available_count}/{len(items)} products")
        if alert_count > 0:
            print(f"  New alerts: {alert_count}")
            for alert in alerts[:5]:  # Show first 5
                print(f"    - [{alert.alert_type}] {alert.message[:60]}")


async def task_generate_weekly_sardine_order():
    """Generate weekly sardine/mackerel shopping recommendations."""
    from ..services.watchlist_service import WatchlistService

    print(f"[{datetime.now()}] Generating weekly sardine order...")

    async with AsyncSessionLocal() as db:
        service = WatchlistService(db)
        recommendations = await service.get_weekly_shopping_list()

        available = [r for r in recommendations if r["status"] == "available"]
        unavailable = [r for r in recommendations if r["status"] == "unavailable"]

        if available:
            total = sum(r["total"] for r in available)
            print(f"Weekly Shopping List (Total: ${total:.2f}):")
            for rec in available:
                item = rec["item"]
                print(f"  • {item.brand} {item.name} x{rec['quantity']} @ ${rec['price']:.2f}")
                print(f"    Platform: {rec['platform_name']}")

        if unavailable:
            print(f"\nUnavailable ({len(unavailable)} items):")
            for rec in unavailable:
                print(f"  • {rec['message']}")

    print(f"[{datetime.now()}] Weekly order generation complete.")


def setup_scheduled_tasks(scheduler: TaskScheduler):
    """Setup all scheduled tasks based on configuration."""

    # Price monitoring - every 6 hours
    scheduler.add_interval_job(
        task_monitor_prices,
        job_id="price_monitor",
        hours=6
    )

    # Inventory check - daily at 8 AM
    scheduler.add_cron_job(
        task_check_inventory,
        job_id="inventory_check",
        hour=8,
        minute=0
    )

    # Shopping list generation - weekly on Sunday at 10 AM
    scheduler.add_cron_job(
        task_generate_shopping_list,
        job_id="shopping_list_generation",
        hour=10,
        minute=0,
        day_of_week="sun"
    )

    # Promotion check - every 12 hours
    scheduler.add_interval_job(
        task_check_promotions,
        job_id="promo_check",
        hours=12
    )

    # Watchlist availability check - every 4 hours
    scheduler.add_interval_job(
        task_check_watchlist,
        job_id="watchlist_check",
        hours=4
    )

    # Weekly sardine order generation - every Saturday at 9 AM
    scheduler.add_cron_job(
        task_generate_weekly_sardine_order,
        job_id="weekly_sardine_order",
        hour=9,
        minute=0,
        day_of_week="sat"
    )

    print("All scheduled tasks configured")


# Global scheduler instance
task_scheduler = TaskScheduler()
