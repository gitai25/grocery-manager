"""Command Line Interface for Grocery Manager."""

import asyncio
from datetime import date
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from .core.database import AsyncSessionLocal, init_db
from .services.inventory_service import InventoryService
from .services.price_service import PriceService
from .services.shopping_service import ShoppingService
from .services.watchlist_service import WatchlistService, init_foodguard_watchlist
from .adapters import get_adapter, get_all_adapters, ADAPTERS, PLATFORM_DISPLAY_NAMES

console = Console()

# Available platforms for CLI
PLATFORM_CHOICES = list(ADAPTERS.keys())


def run_async(coro):
    """Helper to run async functions."""
    return asyncio.get_event_loop().run_until_complete(coro)


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Grocery Manager - Singapore Daily Essentials & Food Procurement System"""
    pass


# ==================== Inventory Commands ====================

@cli.group()
def inventory():
    """Manage inventory items."""
    pass


@inventory.command("list")
@click.option("--category", "-c", help="Filter by category")
@click.option("--low-stock", is_flag=True, help="Show only low stock items")
def inventory_list(category: str, low_stock: bool):
    """List all inventory items."""

    async def _list():
        async with AsyncSessionLocal() as db:
            service = InventoryService(db)

            if low_stock:
                items = await service.get_low_stock_items()
                title = "Low Stock Items"
            elif category:
                items = await service.get_items_by_category(category)
                title = f"Items in '{category}'"
            else:
                items = await service.get_all_items()
                title = "All Inventory Items"

            table = Table(title=title)
            table.add_column("ID", style="cyan", justify="right")
            table.add_column("Name", style="green")
            table.add_column("Category")
            table.add_column("Qty", justify="right")
            table.add_column("Min", justify="right")
            table.add_column("Unit")
            table.add_column("Status")

            for item in items:
                status = ""
                if item.is_low_stock:
                    status = "[red]LOW[/red]"
                elif item.is_expiring_soon:
                    status = "[yellow]EXPIRING[/yellow]"

                table.add_row(
                    str(item.id),
                    item.name,
                    item.category or "-",
                    f"{item.current_quantity:.1f}",
                    f"{item.min_quantity:.1f}",
                    item.unit or "-",
                    status
                )

            console.print(table)

    run_async(_list())


@inventory.command("add")
@click.argument("name")
@click.option("--category", "-c", help="Item category")
@click.option("--quantity", "-q", type=float, default=0, help="Current quantity")
@click.option("--min-qty", type=float, default=1, help="Minimum quantity")
@click.option("--unit", "-u", help="Unit (e.g., pcs, kg, L)")
@click.option("--expiry", "-e", help="Expiry date (YYYY-MM-DD)")
def inventory_add(name: str, category: str, quantity: float, min_qty: float, unit: str, expiry: str):
    """Add a new inventory item."""

    async def _add():
        async with AsyncSessionLocal() as db:
            service = InventoryService(db)

            expiry_date = None
            if expiry:
                expiry_date = date.fromisoformat(expiry)

            item = await service.create_item(
                name=name,
                category=category,
                current_quantity=quantity,
                min_quantity=min_qty,
                unit=unit,
                expiry_date=expiry_date
            )
            await db.commit()

            console.print(f"[green]Added item:[/green] {item.name} (ID: {item.id})")

    run_async(_add())


@inventory.command("update")
@click.argument("item_id", type=int)
@click.option("--name", "-n", help="New name")
@click.option("--quantity", "-q", type=float, help="New quantity")
@click.option("--min-qty", type=float, help="New minimum quantity")
@click.option("--category", "-c", help="New category")
def inventory_update(item_id: int, name: str, quantity: float, min_qty: float, category: str):
    """Update an inventory item."""

    async def _update():
        async with AsyncSessionLocal() as db:
            service = InventoryService(db)

            kwargs = {}
            if name:
                kwargs["name"] = name
            if quantity is not None:
                kwargs["current_quantity"] = quantity
            if min_qty is not None:
                kwargs["min_quantity"] = min_qty
            if category:
                kwargs["category"] = category

            item = await service.update_item(item_id, **kwargs)
            await db.commit()

            if item:
                console.print(f"[green]Updated item:[/green] {item.name}")
            else:
                console.print(f"[red]Item not found:[/red] {item_id}")

    run_async(_update())


@inventory.command("consume")
@click.argument("item_id", type=int)
@click.argument("quantity", type=float)
def inventory_consume(item_id: int, quantity: float):
    """Record consumption of an item."""

    async def _consume():
        async with AsyncSessionLocal() as db:
            service = InventoryService(db)

            item = await service.update_quantity(item_id, -quantity)
            await db.commit()

            if item:
                console.print(
                    f"[green]Consumed {quantity} {item.unit or 'units'} of {item.name}[/green]"
                )
                console.print(f"Remaining: {item.current_quantity:.1f}")
                if item.is_low_stock:
                    console.print("[yellow]Warning: Item is now low on stock![/yellow]")
            else:
                console.print(f"[red]Item not found:[/red] {item_id}")

    run_async(_consume())


@inventory.command("summary")
def inventory_summary():
    """Show inventory summary."""

    async def _summary():
        async with AsyncSessionLocal() as db:
            service = InventoryService(db)
            summary = await service.get_inventory_summary()

            panel = Panel(
                f"""
[bold]Total Items:[/bold] {summary['total_items']}
[bold]Low Stock:[/bold] [red]{summary['low_stock_count']}[/red]
[bold]Expiring Soon:[/bold] [yellow]{summary['expiring_count']}[/yellow]
[bold]Categories:[/bold] {', '.join(summary['categories']) or 'None'}
                """,
                title="Inventory Summary"
            )
            console.print(panel)

    run_async(_summary())


# ==================== Price Commands ====================

@cli.group()
def price():
    """Price monitoring and comparison."""
    pass


@price.command("search")
@click.argument("query")
@click.option("--platform", "-p", type=click.Choice(PLATFORM_CHOICES), default="fairprice",
              help="Platform to search (default: fairprice)")
@click.option("--limit", "-l", type=int, default=10, help="Number of results")
def price_search(query: str, platform: str, limit: int):
    """Search for products on a specific platform."""

    async def _search():
        adapter = get_adapter(platform)
        try:
            result = await adapter.search_products(query, limit=limit)

            table = Table(title=f"Search Results for '{query}' on {platform.upper()}")
            table.add_column("Product", style="green")
            table.add_column("Price", justify="right")
            table.add_column("Original", justify="right")
            table.add_column("Stock")
            table.add_column("Rating")

            for product in result.products:
                stock = "[green]In Stock[/green]" if product.in_stock else "[red]Out[/red]"
                price_str = f"${product.price:.2f}"
                orig_str = f"${product.original_price:.2f}" if product.original_price else "-"
                rating_str = f"{product.rating:.1f}" if product.rating else "-"

                table.add_row(
                    product.name[:55] + "..." if len(product.name) > 55 else product.name,
                    price_str,
                    orig_str,
                    stock,
                    rating_str
                )

            console.print(table)
            console.print(f"\nTotal results: {result.total_count}")
        finally:
            await adapter.close()

    run_async(_search())


@price.command("platforms")
def price_platforms():
    """List all available platforms."""
    table = Table(title="Available Platforms")
    table.add_column("Platform", style="cyan")
    table.add_column("Description")
    table.add_column("Type")

    platforms_info = {
        "fairprice": ("NTUC FairPrice", "Supermarket"),
        "amazon_sg": ("Amazon Singapore", "E-commerce"),
        "iherb": ("iHerb", "Health & Supplements"),
        "little_farms": ("Little Farms", "Organic & Premium"),
        "ryans_grocery": ("Ryan's Grocery", "Imported Foods"),
        "meidiya": ("Meidi-Ya", "Japanese Foods"),
    }

    for name in PLATFORM_CHOICES:
        info = platforms_info.get(name, (name, "Other"))
        table.add_row(name, info[0], info[1])

    console.print(table)


@price.command("compare")
@click.argument("query")
@click.option("--platforms", "-p", default="fairprice,amazon_sg,iherb",
              help="Comma-separated platforms to compare (default: fairprice,amazon_sg,iherb)")
@click.option("--limit", "-l", type=int, default=3, help="Results per platform")
def price_compare(query: str, platforms: str, limit: int):
    """Compare prices across multiple platforms."""

    async def _compare():
        platform_list = [p.strip() for p in platforms.split(",")]
        adapters = {}

        # Create adapters for selected platforms
        for p in platform_list:
            if p in PLATFORM_CHOICES:
                adapters[p] = get_adapter(p)
            else:
                console.print(f"[yellow]Unknown platform: {p}[/yellow]")

        if not adapters:
            console.print("[red]No valid platforms selected[/red]")
            return

        console.print(f"[dim]Searching {len(adapters)} platforms for '{query}'...[/dim]\n")

        async with AsyncSessionLocal() as db:
            price_service = PriceService(db, adapters)
            results = await price_service.compare_prices(query, limit=limit)

            if not results:
                console.print("[yellow]No results found[/yellow]")
                return

            table = Table(title=f"Price Comparison: '{query}'")
            table.add_column("Rank", style="cyan", justify="right")
            table.add_column("Platform", style="magenta")
            table.add_column("Product", style="green")
            table.add_column("Price", justify="right")
            table.add_column("Stock")

            for i, result in enumerate(results[:15], 1):  # Top 15
                stock = "[green]Yes[/green]" if result["product"].in_stock else "[red]No[/red]"
                name = result["product"].name
                if len(name) > 45:
                    name = name[:45] + "..."

                table.add_row(
                    str(i),
                    result["platform"],
                    name,
                    f"${result['price']:.2f}",
                    stock
                )

            console.print(table)

            # Show best deal
            if results:
                best = results[0]
                console.print(f"\n[bold green]Best Price:[/bold green] ${best['price']:.2f} on {best['platform']}")
                console.print(f"[dim]{best['product'].url}[/dim]")

        # Cleanup
        for adapter in adapters.values():
            await adapter.close()

    run_async(_compare())


@price.command("compare-all")
@click.argument("query")
def price_compare_all(query: str):
    """Compare prices across ALL platforms (slower but comprehensive)."""

    async def _compare():
        adapters = get_all_adapters()
        console.print(f"[dim]Searching all {len(adapters)} platforms for '{query}'...[/dim]\n")

        async with AsyncSessionLocal() as db:
            price_service = PriceService(db, adapters)
            results = await price_service.compare_prices(query, limit=3)

            if not results:
                console.print("[yellow]No results found[/yellow]")
                return

            table = Table(title=f"All Platforms Comparison: '{query}'")
            table.add_column("Rank", style="cyan", justify="right")
            table.add_column("Platform", style="magenta")
            table.add_column("Product", style="green")
            table.add_column("Price", justify="right")

            for i, result in enumerate(results[:20], 1):
                name = result["product"].name
                if len(name) > 45:
                    name = name[:45] + "..."

                table.add_row(
                    str(i),
                    result["platform"],
                    name,
                    f"${result['price']:.2f}"
                )

            console.print(table)

        # Cleanup
        for adapter in adapters.values():
            await adapter.close()

    run_async(_compare())


# ==================== Shopping List Commands ====================

@cli.group()
def shop():
    """Shopping list management."""
    pass


@shop.command("generate")
def shop_generate():
    """Generate shopping list from inventory."""

    async def _generate():
        async with AsyncSessionLocal() as db:
            service = ShoppingService(db)

            shopping_list = await service.generate_list_from_inventory()
            await db.commit()

            if shopping_list:
                console.print(f"[green]Created shopping list:[/green] {shopping_list.name}")
                console.print(f"Items: {len(shopping_list.items)}")

                table = Table(title="Shopping List Items")
                table.add_column("Item")
                table.add_column("Qty", justify="right")
                table.add_column("Unit")

                for item in shopping_list.items:
                    table.add_row(
                        item.product_name,
                        f"{item.quantity_needed:.1f}",
                        item.unit or "-"
                    )

                console.print(table)
            else:
                console.print("[yellow]No items need restocking.[/yellow]")

    run_async(_generate())


@shop.command("list")
def shop_list():
    """Show active shopping lists."""

    async def _list():
        async with AsyncSessionLocal() as db:
            service = ShoppingService(db)
            lists = await service.get_active_lists()

            if not lists:
                console.print("[yellow]No active shopping lists.[/yellow]")
                return

            table = Table(title="Active Shopping Lists")
            table.add_column("ID", style="cyan", justify="right")
            table.add_column("Name", style="green")
            table.add_column("Items", justify="right")
            table.add_column("Total", justify="right")
            table.add_column("Status")
            table.add_column("Created")

            for lst in lists:
                table.add_row(
                    str(lst.id),
                    lst.name or "-",
                    str(len(lst.items)),
                    f"${lst.total_estimated_cost:.2f}" if lst.total_estimated_cost else "-",
                    lst.status,
                    lst.created_at.strftime("%Y-%m-%d")
                )

            console.print(table)

    run_async(_list())


@shop.command("show")
@click.argument("list_id", type=int)
def shop_show(list_id: int):
    """Show details of a shopping list."""

    async def _show():
        async with AsyncSessionLocal() as db:
            service = ShoppingService(db)
            summary = await service.get_list_summary(list_id)

            if not summary:
                console.print(f"[red]Shopping list not found:[/red] {list_id}")
                return

            lst = summary["list"]
            console.print(Panel(
                f"[bold]{lst.name}[/bold]\n"
                f"Status: {lst.status}\n"
                f"Items: {summary['item_count']}\n"
                f"Estimated Total: ${summary['total_estimated'] or 0:.2f}",
                title=f"Shopping List #{list_id}"
            ))

            for platform, data in summary["by_platform"].items():
                table = Table(title=f"{platform.upper()} (${data['subtotal']:.2f})")
                table.add_column("Item")
                table.add_column("Qty", justify="right")
                table.add_column("Price", justify="right")
                table.add_column("Status")

                for item in data["items"]:
                    status = "[green]Purchased[/green]" if item.is_purchased else "[dim]Pending[/dim]"
                    table.add_row(
                        item.product_name,
                        f"{item.quantity_needed:.1f}",
                        f"${item.selected_price:.2f}" if item.selected_price else "-",
                        status
                    )

                console.print(table)

    run_async(_show())


# ==================== Watchlist Commands ====================

@cli.group()
def watch():
    """Premium product watchlist and monitoring."""
    pass


@watch.command("init")
def watch_init():
    """Initialize watchlist with FoodGuard recommended products."""

    async def _init():
        await init_db()  # Ensure tables exist
        async with AsyncSessionLocal() as db:
            items = await init_foodguard_watchlist(db)
            console.print(f"\n[green]Watchlist initialized with {len(items)} products![/green]")

            table = Table(title="FoodGuard Premium Products")
            table.add_column("ID", style="cyan", justify="right")
            table.add_column("Brand", style="magenta")
            table.add_column("Product", style="green")
            table.add_column("Score", justify="center")
            table.add_column("Target/Week", justify="right")

            for item in items:
                table.add_row(
                    str(item.id),
                    item.brand,
                    item.name[:40],
                    f"{item.foodguard_score}/10" if item.foodguard_score else "-",
                    str(item.weekly_target_qty)
                )

            console.print(table)

    run_async(_init())


@watch.command("list")
def watch_list():
    """Show all watchlist items."""

    async def _list():
        async with AsyncSessionLocal() as db:
            service = WatchlistService(db)
            items = await service.get_all_items()

            if not items:
                console.print("[yellow]No items in watchlist. Run 'watch init' first.[/yellow]")
                return

            table = Table(title="Watchlist Items")
            table.add_column("ID", style="cyan", justify="right")
            table.add_column("Brand", style="magenta")
            table.add_column("Product", style="green")
            table.add_column("Score", justify="center")
            table.add_column("Best Price", justify="right")
            table.add_column("Platform")
            table.add_column("Status")

            for item in items:
                price_str = f"${item.current_best_price:.2f}" if item.current_best_price else "-"
                platform_str = PLATFORM_DISPLAY_NAMES.get(
                    item.current_best_platform, item.current_best_platform
                ) if item.current_best_platform else "-"

                if item.is_available_anywhere:
                    status = "[green]In Stock[/green]"
                else:
                    status = "[red]Unavailable[/red]"

                table.add_row(
                    str(item.id),
                    item.brand,
                    item.name[:35],
                    f"{item.foodguard_score}/10" if item.foodguard_score else "-",
                    price_str,
                    platform_str,
                    status
                )

            console.print(table)

    run_async(_list())


@watch.command("check")
@click.option("--id", "item_id", type=int, help="Check specific item by ID")
def watch_check(item_id: int):
    """Check availability of watchlist items across all platforms."""

    async def _check():
        async with AsyncSessionLocal() as db:
            service = WatchlistService(db)

            if item_id:
                item = await service.get_item(item_id)
                if not item:
                    console.print(f"[red]Item not found:[/red] {item_id}")
                    return
                items = [item]
            else:
                items = await service.get_all_items()

            if not items:
                console.print("[yellow]No items in watchlist.[/yellow]")
                return

            console.print(f"[dim]Checking {len(items)} products across platforms...[/dim]\n")

            for item in items:
                console.print(f"[bold]{item.brand} - {item.name}[/bold]")
                results = await service.check_availability(item)

                for platform, status in results.items():
                    platform_name = PLATFORM_DISPLAY_NAMES.get(platform, platform)
                    if status.get("in_stock"):
                        price = status.get("price", 0)
                        console.print(f"  [green]✓[/green] {platform_name}: ${price:.2f}")
                    elif status.get("error"):
                        console.print(f"  [yellow]![/yellow] {platform_name}: Error")
                    else:
                        console.print(f"  [red]✗[/red] {platform_name}: Not found")

                console.print()

    run_async(_check())


@watch.command("weekly")
def watch_weekly():
    """Generate weekly shopping recommendations."""

    async def _weekly():
        async with AsyncSessionLocal() as db:
            service = WatchlistService(db)
            recommendations = await service.get_weekly_shopping_list()

            if not recommendations:
                console.print("[yellow]No recommendations. Run 'watch check' first.[/yellow]")
                return

            # Group by status
            available = [r for r in recommendations if r["status"] == "available"]
            unavailable = [r for r in recommendations if r["status"] == "unavailable"]
            over_budget = [r for r in recommendations if r["status"] == "over_budget"]

            if available:
                table = Table(title="Weekly Shopping List")
                table.add_column("Product", style="green")
                table.add_column("Qty", justify="center")
                table.add_column("Platform", style="cyan")
                table.add_column("Unit Price", justify="right")
                table.add_column("Total", justify="right")

                total = 0
                for rec in available:
                    item = rec["item"]
                    table.add_row(
                        f"{item.brand} {item.name[:30]}",
                        str(rec["quantity"]),
                        rec["platform_name"],
                        f"${rec['price']:.2f}",
                        f"${rec['total']:.2f}"
                    )
                    total += rec["total"]

                console.print(table)
                console.print(f"\n[bold]Total: ${total:.2f}[/bold]")

            if unavailable:
                console.print("\n[red]Unavailable Products:[/red]")
                for rec in unavailable:
                    console.print(f"  • {rec['message']}")

            if over_budget:
                console.print("\n[yellow]Over Budget:[/yellow]")
                for rec in over_budget:
                    console.print(f"  • {rec['message']}")

    run_async(_weekly())


@watch.command("alerts")
def watch_alerts():
    """Show unread alerts."""

    async def _alerts():
        async with AsyncSessionLocal() as db:
            service = WatchlistService(db)
            alerts = await service.get_unread_alerts()

            if not alerts:
                console.print("[green]No new alerts.[/green]")
                return

            table = Table(title=f"Alerts ({len(alerts)} unread)")
            table.add_column("Type", style="cyan")
            table.add_column("Platform")
            table.add_column("Message", style="green")
            table.add_column("Time")

            for alert in alerts:
                type_style = {
                    "restock": "[green]RESTOCK[/green]",
                    "price_drop": "[cyan]PRICE DROP[/cyan]",
                    "out_of_stock": "[red]OUT OF STOCK[/red]",
                }.get(alert.alert_type, alert.alert_type)

                table.add_row(
                    type_style,
                    alert.platform,
                    alert.message[:50],
                    alert.created_at.strftime("%m-%d %H:%M")
                )

            console.print(table)

    run_async(_alerts())


@watch.command("export")
@click.option("--output", "-o", default="data/watchlist.json", help="Output file path")
def watch_export(output: str):
    """Export watchlist to JSON file for static frontend."""
    import json
    from datetime import datetime
    from pathlib import Path

    async def _export():
        async with AsyncSessionLocal() as db:
            service = WatchlistService(db)
            items = await service.get_all_items()

            if not items:
                console.print("[yellow]No items in watchlist.[/yellow]")
                return

            # Product images mapping
            images = {
                "José Gourmet": "https://www.fossaprovisions.com/cdn/shop/products/Jg_small_mack_oo-removebg-preview_1024x1024@2x.png",
                "The Stock Merchant": "https://cdn.shopify.com/s/files/1/0553/1521/products/TheStockMerchant-SardinesInExtraVirginOliveOil-120g_1024x1024.jpg",
                "Good Fish": "https://cdn.shopify.com/s/files/1/0278/8577/0734/products/sardines-olive-oil_1024x1024.jpg",
                "NURI": "https://m.media-amazon.com/images/I/71qWDGzL8ZL._SL1500_.jpg",
                "Ortiz": "https://m.media-amazon.com/images/I/71LvUjl5q2L._SL1500_.jpg",
                "Ramón Peña": "https://www.conservasramonpena.com/wp-content/uploads/2021/04/sardinillas-aceite-oliva-16-20-piezas-linea-oro.png",
            }

            products = []
            for item in items:
                products.append({
                    "id": item.id,
                    "brand": item.brand,
                    "name": item.name,
                    "category": item.category,
                    "origin_country": item.origin_country,
                    "size": item.size,
                    "foodguard_score": item.foodguard_score,
                    "weekly_target_qty": item.weekly_target_qty,
                    "max_price": item.max_price,
                    "search_keywords": item.search_keywords,
                    "platform_products": item.platform_products or {},
                    "availability_status": item.availability_status or {},
                    "current_best_price": item.current_best_price,
                    "current_best_platform": item.current_best_platform,
                    "last_checked_at": item.last_checked_at.isoformat() if item.last_checked_at else None,
                    "notes": item.notes,
                    "image": images.get(item.brand, ""),
                })

            data = {
                "version": "1.0.0",
                "last_updated": datetime.utcnow().isoformat() + "Z",
                "products": products,
            }

            # Write to file
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            console.print(f"[green]Exported {len(products)} products to {output}[/green]")

    run_async(_export())


@watch.command("sync")
def watch_sync():
    """Export watchlist and copy to frontend for deployment."""
    import json
    import shutil
    from datetime import datetime
    from pathlib import Path

    async def _sync():
        async with AsyncSessionLocal() as db:
            service = WatchlistService(db)
            items = await service.get_all_items()

            if not items:
                console.print("[yellow]No items in watchlist.[/yellow]")
                return

            # Product images mapping
            images = {
                "José Gourmet": "https://www.fossaprovisions.com/cdn/shop/products/Jg_small_mack_oo-removebg-preview_1024x1024@2x.png",
                "The Stock Merchant": "https://cdn.shopify.com/s/files/1/0553/1521/products/TheStockMerchant-SardinesInExtraVirginOliveOil-120g_1024x1024.jpg",
                "Good Fish": "https://cdn.shopify.com/s/files/1/0278/8577/0734/products/sardines-olive-oil_1024x1024.jpg",
                "NURI": "https://m.media-amazon.com/images/I/71qWDGzL8ZL._SL1500_.jpg",
                "Ortiz": "https://m.media-amazon.com/images/I/71LvUjl5q2L._SL1500_.jpg",
                "Ramón Peña": "https://www.conservasramonpena.com/wp-content/uploads/2021/04/sardinillas-aceite-oliva-16-20-piezas-linea-oro.png",
            }

            products = []
            for item in items:
                products.append({
                    "id": item.id,
                    "brand": item.brand,
                    "name": item.name,
                    "category": item.category,
                    "origin_country": item.origin_country,
                    "size": item.size,
                    "foodguard_score": item.foodguard_score,
                    "weekly_target_qty": item.weekly_target_qty,
                    "max_price": item.max_price,
                    "search_keywords": item.search_keywords,
                    "platform_products": item.platform_products or {},
                    "availability_status": item.availability_status or {},
                    "current_best_price": item.current_best_price,
                    "current_best_platform": item.current_best_platform,
                    "last_checked_at": item.last_checked_at.isoformat() if item.last_checked_at else None,
                    "notes": item.notes,
                    "image": images.get(item.brand, ""),
                })

            data = {
                "version": "1.0.0",
                "last_updated": datetime.utcnow().isoformat() + "Z",
                "products": products,
            }

            # Write to data directory
            data_path = Path("data/watchlist.json")
            data_path.parent.mkdir(parents=True, exist_ok=True)
            with open(data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # Copy to frontend
            frontend_data_path = Path("frontend/public/data")
            frontend_data_path.mkdir(parents=True, exist_ok=True)
            shutil.copy(data_path, frontend_data_path / "watchlist.json")

            console.print(f"[green]Synced {len(products)} products to frontend[/green]")
            console.print("\n[cyan]Next steps:[/cyan]")
            console.print("  1. git add data/ frontend/public/data/")
            console.print("  2. git commit -m 'Update watchlist data'")
            console.print("  3. git push origin main")
            console.print("\n[dim]Cloudflare Pages will auto-deploy on push[/dim]")

    run_async(_sync())


@watch.command("add")
@click.argument("brand")
@click.argument("name")
@click.option("--category", "-c", default="sardines", help="Product category")
@click.option("--origin", "-o", help="Origin country")
@click.option("--size", "-s", help="Package size")
@click.option("--score", type=int, help="FoodGuard score (1-10)")
@click.option("--qty", type=int, default=2, help="Weekly target quantity")
@click.option("--max-price", type=float, help="Maximum acceptable price")
@click.option("--notes", help="Additional notes")
def watch_add(brand, name, category, origin, size, score, qty, max_price, notes):
    """Add a new product to the watchlist."""

    async def _add():
        async with AsyncSessionLocal() as db:
            service = WatchlistService(db)
            item = await service.add_item(
                name=name,
                brand=brand,
                category=category,
                origin_country=origin,
                size=size,
                foodguard_score=score,
                weekly_target_qty=qty,
                max_price=max_price,
                notes=notes,
            )
            console.print(f"[green]Added: {brand} - {name} (ID: {item.id})[/green]")
            console.print("\n[dim]Run 'watch sync' to update frontend data[/dim]")

    run_async(_add())


# ==================== Database Commands ====================

@cli.command("init")
def init_database():
    """Initialize the database."""

    async def _init():
        await init_db()
        console.print("[green]Database initialized successfully![/green]")

    run_async(_init())


# ==================== Web Server Command ====================

@cli.command("web")
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind")
@click.option("--port", "-p", type=int, default=8080, help="Port to bind")
def web_server(host: str, port: int):
    """Start the web dashboard server."""
    import uvicorn
    from .web.app import app

    console.print(f"[green]Starting web server at http://{host}:{port}[/green]")
    console.print("[dim]Press Ctrl+C to stop[/dim]")

    # Initialize database first
    run_async(init_db())

    uvicorn.run(app, host=host, port=port)


# ==================== Entry Point ====================

def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
