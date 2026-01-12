"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import date

from .core.config import settings
from .core.database import init_db, get_db, AsyncSessionLocal
from .core.scheduler import task_scheduler, setup_scheduled_tasks
from .services.inventory_service import InventoryService
from .services.shopping_service import ShoppingService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    await init_db()
    setup_scheduled_tasks(task_scheduler)
    task_scheduler.start()
    yield
    # Shutdown
    task_scheduler.stop()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Singapore Daily Essentials & Food Procurement Management System",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== Pydantic Models ====================

class InventoryItemCreate(BaseModel):
    name: str
    category: Optional[str] = None
    unit: Optional[str] = None
    current_quantity: float = 0
    min_quantity: float = 1
    preferred_quantity: Optional[float] = None
    expiry_date: Optional[date] = None
    preferred_brands: Optional[List[str]] = None
    notes: Optional[str] = None


class InventoryItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    current_quantity: Optional[float] = None
    min_quantity: Optional[float] = None
    preferred_quantity: Optional[float] = None
    expiry_date: Optional[date] = None
    notes: Optional[str] = None


class InventoryItemResponse(BaseModel):
    id: int
    name: str
    category: Optional[str]
    unit: Optional[str]
    current_quantity: float
    min_quantity: float
    preferred_quantity: Optional[float]
    expiry_date: Optional[date]
    is_low_stock: bool
    is_expiring_soon: bool

    class Config:
        from_attributes = True


class QuantityUpdate(BaseModel):
    quantity_change: float


# ==================== API Routes ====================

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running"
    }


# Inventory endpoints

@app.get("/api/inventory", response_model=List[InventoryItemResponse])
async def list_inventory_items(
    category: Optional[str] = None,
    low_stock_only: bool = False
):
    """Get all inventory items."""
    async with AsyncSessionLocal() as db:
        service = InventoryService(db)

        if low_stock_only:
            items = await service.get_low_stock_items()
        elif category:
            items = await service.get_items_by_category(category)
        else:
            items = await service.get_all_items()

        return [InventoryItemResponse(
            id=item.id,
            name=item.name,
            category=item.category,
            unit=item.unit,
            current_quantity=item.current_quantity,
            min_quantity=item.min_quantity,
            preferred_quantity=item.preferred_quantity,
            expiry_date=item.expiry_date,
            is_low_stock=item.is_low_stock,
            is_expiring_soon=item.is_expiring_soon
        ) for item in items]


@app.post("/api/inventory", response_model=InventoryItemResponse)
async def create_inventory_item(item: InventoryItemCreate):
    """Create a new inventory item."""
    async with AsyncSessionLocal() as db:
        service = InventoryService(db)
        new_item = await service.create_item(**item.model_dump())
        await db.commit()

        return InventoryItemResponse(
            id=new_item.id,
            name=new_item.name,
            category=new_item.category,
            unit=new_item.unit,
            current_quantity=new_item.current_quantity,
            min_quantity=new_item.min_quantity,
            preferred_quantity=new_item.preferred_quantity,
            expiry_date=new_item.expiry_date,
            is_low_stock=new_item.is_low_stock,
            is_expiring_soon=new_item.is_expiring_soon
        )


@app.get("/api/inventory/{item_id}", response_model=InventoryItemResponse)
async def get_inventory_item(item_id: int):
    """Get a specific inventory item."""
    async with AsyncSessionLocal() as db:
        service = InventoryService(db)
        item = await service.get_item_by_id(item_id)

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        return InventoryItemResponse(
            id=item.id,
            name=item.name,
            category=item.category,
            unit=item.unit,
            current_quantity=item.current_quantity,
            min_quantity=item.min_quantity,
            preferred_quantity=item.preferred_quantity,
            expiry_date=item.expiry_date,
            is_low_stock=item.is_low_stock,
            is_expiring_soon=item.is_expiring_soon
        )


@app.put("/api/inventory/{item_id}", response_model=InventoryItemResponse)
async def update_inventory_item(item_id: int, update: InventoryItemUpdate):
    """Update an inventory item."""
    async with AsyncSessionLocal() as db:
        service = InventoryService(db)

        item = await service.update_item(
            item_id,
            **update.model_dump(exclude_unset=True)
        )

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        await db.commit()

        return InventoryItemResponse(
            id=item.id,
            name=item.name,
            category=item.category,
            unit=item.unit,
            current_quantity=item.current_quantity,
            min_quantity=item.min_quantity,
            preferred_quantity=item.preferred_quantity,
            expiry_date=item.expiry_date,
            is_low_stock=item.is_low_stock,
            is_expiring_soon=item.is_expiring_soon
        )


@app.post("/api/inventory/{item_id}/quantity")
async def update_quantity(item_id: int, update: QuantityUpdate):
    """Update item quantity (positive to add, negative to consume)."""
    async with AsyncSessionLocal() as db:
        service = InventoryService(db)

        item = await service.update_quantity(item_id, update.quantity_change)

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        await db.commit()

        return {
            "id": item.id,
            "name": item.name,
            "current_quantity": item.current_quantity,
            "is_low_stock": item.is_low_stock
        }


@app.delete("/api/inventory/{item_id}")
async def delete_inventory_item(item_id: int):
    """Delete an inventory item."""
    async with AsyncSessionLocal() as db:
        service = InventoryService(db)
        success = await service.delete_item(item_id)

        if not success:
            raise HTTPException(status_code=404, detail="Item not found")

        await db.commit()
        return {"status": "deleted", "id": item_id}


@app.get("/api/inventory/summary")
async def get_inventory_summary():
    """Get inventory summary statistics."""
    async with AsyncSessionLocal() as db:
        service = InventoryService(db)
        return await service.get_inventory_summary()


# Shopping list endpoints

@app.post("/api/shopping/generate")
async def generate_shopping_list():
    """Generate a shopping list based on inventory levels."""
    async with AsyncSessionLocal() as db:
        service = ShoppingService(db)
        shopping_list = await service.generate_list_from_inventory()

        if not shopping_list:
            return {"message": "No items need restocking", "list": None}

        await db.commit()

        return {
            "message": "Shopping list generated",
            "list_id": shopping_list.id,
            "item_count": len(shopping_list.items)
        }


@app.get("/api/shopping/lists")
async def get_shopping_lists():
    """Get all active shopping lists."""
    async with AsyncSessionLocal() as db:
        service = ShoppingService(db)
        lists = await service.get_active_lists()

        return [{
            "id": lst.id,
            "name": lst.name,
            "status": lst.status,
            "item_count": len(lst.items),
            "total_estimated": lst.total_estimated_cost,
            "created_at": lst.created_at.isoformat()
        } for lst in lists]


@app.get("/api/shopping/lists/{list_id}")
async def get_shopping_list(list_id: int):
    """Get details of a shopping list."""
    async with AsyncSessionLocal() as db:
        service = ShoppingService(db)
        summary = await service.get_list_summary(list_id)

        if not summary:
            raise HTTPException(status_code=404, detail="Shopping list not found")

        return summary


# Scheduler endpoints

@app.get("/api/scheduler/jobs")
async def get_scheduled_jobs():
    """Get all scheduled jobs."""
    jobs = task_scheduler.get_jobs()
    return [{
        "id": job.id,
        "name": job.name,
        "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
        "trigger": str(job.trigger)
    } for job in jobs]


@app.post("/api/scheduler/jobs/{job_id}/run")
async def run_job_now(job_id: str):
    """Trigger a job to run immediately."""
    task_scheduler.run_job_now(job_id)
    return {"status": "triggered", "job_id": job_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
