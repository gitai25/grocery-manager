# 系统架构设计：新加坡日常用品与食品采购管理系统

## 1. 系统概述

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Grocery Manager System                          │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────────────┐    │
│  │  Web UI   │  │    CLI    │  │  Mobile   │  │  Telegram Bot     │    │
│  │ (Vue.js)  │  │  (Click)  │  │   (PWA)   │  │   (Optional)      │    │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────────┬─────────┘    │
│        └──────────────┴──────────────┴──────────────────┘              │
│                                  │                                      │
│                          ┌───────▼───────┐                             │
│                          │   REST API    │                             │
│                          │  (FastAPI)    │                             │
│                          └───────┬───────┘                             │
│        ┌─────────────────────────┼─────────────────────────┐           │
│        │                         │                         │           │
│  ┌─────▼─────┐            ┌──────▼──────┐           ┌──────▼──────┐   │
│  │ Inventory │            │   Price     │           │   Order     │   │
│  │  Manager  │            │   Monitor   │           │   Manager   │   │
│  └─────┬─────┘            └──────┬──────┘           └──────┬──────┘   │
│        │                         │                         │           │
│        └─────────────────────────┼─────────────────────────┘           │
│                                  │                                      │
│                          ┌───────▼───────┐                             │
│                          │   Scheduler   │                             │
│                          │ (APScheduler) │                             │
│                          └───────┬───────┘                             │
│                                  │                                      │
│  ┌───────────────────────────────┼───────────────────────────────────┐ │
│  │                      Platform Adapters                             │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐  │ │
│  │  │ Shopee  │ │ Lazada  │ │FairPrice│ │  Cold   │ │   Amazon    │  │ │
│  │  │   API   │ │   API   │ │ Scraper │ │ Storage │ │   SG API    │  │ │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └──────┬──────┘  │ │
│  └───────┼──────────┬┼──────────┬┼──────────┬┼─────────────┼─────────┘ │
│          └──────────┴┴──────────┴┴──────────┴┴─────────────┘           │
│                                  │                                      │
│                          ┌───────▼───────┐                             │
│                          │    SQLite     │                             │
│                          │   Database    │                             │
│                          └───────────────┘                             │
└─────────────────────────────────────────────────────────────────────────┘
```

## 2. 核心模块

### 2.1 库存管理模块 (Inventory Manager)

**功能**:
- 管理家庭物品清单
- 跟踪物品数量和过期日期
- 低库存预警
- 消耗速率分析

**数据模型**:
```python
class InventoryItem:
    id: int
    name: str                    # 物品名称
    category: str                # 分类：食品/日用品/清洁用品等
    current_quantity: float      # 当前数量
    unit: str                    # 单位：个/瓶/kg等
    min_quantity: float          # 最低库存警戒线
    preferred_quantity: float    # 理想库存量
    expiry_date: Optional[date]  # 过期日期
    last_purchase_date: date     # 上次购买日期
    avg_consumption_rate: float  # 平均消耗速率（每天）
    preferred_brands: List[str]  # 偏好品牌
    notes: str                   # 备注
```

### 2.2 价格监控模块 (Price Monitor)

**功能**:
- 定时抓取各平台价格
- 价格历史记录
- 最佳价格推荐
- 促销活动监控

**数据模型**:
```python
class PriceRecord:
    id: int
    product_name: str
    platform: str           # shopee/lazada/fairprice/etc
    platform_product_id: str
    price: Decimal
    original_price: Optional[Decimal]
    discount_percent: Optional[float]
    unit_price: Decimal     # 单位价格（便于比较）
    in_stock: bool
    delivery_fee: Decimal
    promo_info: str
    scraped_at: datetime
    url: str
```

### 2.3 采购清单模块 (Shopping List)

**功能**:
- 自动生成采购建议
- 手动添加/编辑清单
- 平台比价汇总
- 最优购买方案

**数据模型**:
```python
class ShoppingList:
    id: int
    created_at: datetime
    status: str             # draft/pending/ordered/completed
    items: List[ShoppingListItem]
    total_estimated_cost: Decimal

class ShoppingListItem:
    inventory_item_id: int
    quantity_needed: float
    best_platform: str
    best_price: Decimal
    alternatives: List[PlatformOption]
```

### 2.4 订单管理模块 (Order Manager)

**功能**:
- 下单（API或跳转链接）
- 订单跟踪
- 历史订单记录
- 自动确认收货更新库存

**数据模型**:
```python
class Order:
    id: int
    platform: str
    platform_order_id: str
    items: List[OrderItem]
    total_amount: Decimal
    status: str             # pending/paid/shipped/delivered
    ordered_at: datetime
    delivered_at: Optional[datetime]
```

## 3. 平台适配器设计

### 3.1 抽象基类

```python
from abc import ABC, abstractmethod

class PlatformAdapter(ABC):
    @abstractmethod
    async def search_products(self, query: str, limit: int = 20) -> List[Product]:
        """搜索商品"""
        pass

    @abstractmethod
    async def get_product_details(self, product_id: str) -> ProductDetails:
        """获取商品详情"""
        pass

    @abstractmethod
    async def get_price(self, product_id: str) -> PriceInfo:
        """获取当前价格"""
        pass

    @abstractmethod
    async def add_to_cart(self, product_id: str, quantity: int) -> bool:
        """添加到购物车"""
        pass

    @abstractmethod
    async def create_order(self, cart_items: List[CartItem]) -> OrderResult:
        """创建订单"""
        pass
```

### 3.2 各平台实现

| 平台 | 适配器类 | 数据获取方式 | 下单方式 |
|------|----------|--------------|----------|
| Shopee | ShopeeAdapter | Open API | API |
| Lazada/RedMart | LazadaAdapter | Open API | API |
| FairPrice | FairPriceAdapter | Playwright | 跳转链接 |
| Cold Storage | ColdStorageAdapter | Playwright | 跳转链接 |
| Amazon SG | AmazonAdapter | Product API | 跳转链接 |
| iHerb | iHerbAdapter | Affiliate API | 跳转链接 |

## 4. 数据库设计

### 4.1 表结构

```sql
-- 库存物品表
CREATE TABLE inventory_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT,
    current_quantity REAL DEFAULT 0,
    unit TEXT,
    min_quantity REAL,
    preferred_quantity REAL,
    expiry_date DATE,
    last_purchase_date DATE,
    avg_consumption_rate REAL,
    preferred_brands TEXT,  -- JSON array
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 价格记录表
CREATE TABLE price_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inventory_item_id INTEGER,
    platform TEXT NOT NULL,
    platform_product_id TEXT,
    product_name TEXT,
    price DECIMAL(10,2),
    original_price DECIMAL(10,2),
    unit_price DECIMAL(10,2),
    in_stock BOOLEAN,
    url TEXT,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (inventory_item_id) REFERENCES inventory_items(id)
);

-- 采购清单表
CREATE TABLE shopping_lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT DEFAULT 'draft',
    total_estimated_cost DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- 采购清单项目表
CREATE TABLE shopping_list_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shopping_list_id INTEGER,
    inventory_item_id INTEGER,
    quantity_needed REAL,
    selected_platform TEXT,
    selected_price DECIMAL(10,2),
    FOREIGN KEY (shopping_list_id) REFERENCES shopping_lists(id),
    FOREIGN KEY (inventory_item_id) REFERENCES inventory_items(id)
);

-- 订单表
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shopping_list_id INTEGER,
    platform TEXT,
    platform_order_id TEXT,
    total_amount DECIMAL(10,2),
    status TEXT DEFAULT 'pending',
    ordered_at TIMESTAMP,
    delivered_at TIMESTAMP,
    FOREIGN KEY (shopping_list_id) REFERENCES shopping_lists(id)
);

-- 消耗记录表（用于计算消耗速率）
CREATE TABLE consumption_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inventory_item_id INTEGER,
    quantity_consumed REAL,
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (inventory_item_id) REFERENCES inventory_items(id)
);
```

## 5. 定时任务设计

```python
# 定时任务配置
SCHEDULED_JOBS = {
    "price_monitor": {
        "trigger": "interval",
        "hours": 6,           # 每6小时更新价格
        "func": "tasks.monitor_prices"
    },
    "inventory_check": {
        "trigger": "cron",
        "hour": 8,            # 每天早上8点检查库存
        "func": "tasks.check_inventory_levels"
    },
    "auto_generate_list": {
        "trigger": "cron",
        "day_of_week": "sun", # 每周日生成采购清单
        "hour": 10,
        "func": "tasks.generate_shopping_list"
    },
    "promo_alert": {
        "trigger": "interval",
        "hours": 12,          # 每12小时检查促销
        "func": "tasks.check_promotions"
    }
}
```

## 6. 用户界面设计

### 6.1 Web Dashboard

```
┌──────────────────────────────────────────────────────────────┐
│  🏠 Grocery Manager                        [通知] [设置]     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │  📦 库存概览    │  │  💰 今日最优价  │  │  ⚠️ 预警     │ │
│  │  总物品: 45     │  │  牛奶 $3.50     │  │  低库存: 5   │ │
│  │  低库存: 5      │  │  鸡蛋 $4.20     │  │  即将过期: 2 │ │
│  │  即将过期: 2    │  │  大米 $12.90    │  │              │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  📋 本周采购清单                          [生成订单]  │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │ ☐ 牛奶 2L x2      FairPrice $3.50   RedMart $3.80│  │   │
│  │  │ ☐ 鸡蛋 30个       Shopee $4.20      FairPrice $4.50│  │   │
│  │  │ ☐ 洗衣液 3L      Lazada $15.90     Amazon $16.50│  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  │  预计总价: $56.80                                     │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 6.2 CLI 界面

```bash
$ grocery-manager

Commands:
  inventory list              # 查看库存
  inventory add <item>        # 添加物品
  inventory update <id>       # 更新物品

  price check <item>          # 查询价格
  price history <item>        # 价格历史

  list generate               # 生成采购清单
  list show                   # 显示当前清单
  list order                  # 下单

  schedule show               # 显示定时任务
  schedule run <job>          # 手动运行任务
```

## 7. 项目结构

```
grocery-manager/
├── README.md
├── requirements.txt
├── config.yaml                 # 配置文件
├── docker-compose.yml
│
├── src/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 入口
│   ├── cli.py                  # CLI 入口
│   │
│   ├── core/
│   │   ├── config.py           # 配置管理
│   │   ├── database.py         # 数据库连接
│   │   └── scheduler.py        # 定时任务
│   │
│   ├── models/
│   │   ├── inventory.py
│   │   ├── price.py
│   │   ├── shopping_list.py
│   │   └── order.py
│   │
│   ├── adapters/
│   │   ├── base.py             # 抽象基类
│   │   ├── shopee.py
│   │   ├── lazada.py
│   │   ├── fairprice.py
│   │   ├── cold_storage.py
│   │   └── amazon.py
│   │
│   ├── services/
│   │   ├── inventory_service.py
│   │   ├── price_service.py
│   │   ├── shopping_service.py
│   │   └── order_service.py
│   │
│   ├── api/
│   │   ├── routes/
│   │   │   ├── inventory.py
│   │   │   ├── prices.py
│   │   │   ├── shopping.py
│   │   │   └── orders.py
│   │   └── dependencies.py
│   │
│   └── tasks/
│       ├── price_monitor.py
│       ├── inventory_check.py
│       └── promo_alert.py
│
├── web/                        # Vue.js 前端
│   ├── src/
│   ├── public/
│   └── package.json
│
├── tests/
│   ├── test_adapters/
│   ├── test_services/
│   └── test_api/
│
└── data/
    └── grocery.db              # SQLite 数据库
```

## 8. 实现优先级

### Phase 1: MVP (最小可行产品)
1. SQLite 数据库初始化
2. 库存管理基础功能 (CRUD)
3. CLI 界面
4. FairPrice 价格爬虫 (最常用)

### Phase 2: 扩展平台
5. Lazada/RedMart API 集成
6. Shopee API 集成
7. 价格比较功能

### Phase 3: 自动化
8. 定时任务框架
9. 自动生成采购清单
10. 低库存预警通知

### Phase 4: 完善
11. Web Dashboard
12. 订单管理
13. 消耗分析报表
