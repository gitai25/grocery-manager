# Notes: 新加坡电商平台研究

## 平台API接入情况

### 有官方API的平台

#### Shopee Open Platform
- **官网**: https://open.shopee.com
- **功能**: 产品管理、订单处理、库存同步、支付处理
- **认证**: 需要注册开发者账号，获取API Key
- **特点**: 东南亚最大电商，月活3.43亿用户
- **适用性**: ✅ 可直接API集成

#### Lazada Open Platform
- **官网**: https://open.lazada.com
- **API文档**: https://open.lazada.com/doc/api.htm
- **功能**: 订单、产品、库存、客户数据交换
- **认证**: OAuth 2.0，需要 client ID 和 client secret
- **特点**: 13.5万商家，完整的API生态
- **适用性**: ✅ 可直接API集成（RedMart在Lazada平台上）

### 无公开API的平台

#### NTUC FairPrice
- **状态**: 无公开API
- **方案**: Web Scraping
- **特点**: 新加坡最大超市零售商
- **2025动态**: 智能购物车试点、AI推荐引擎

#### Cold Storage
- **状态**: 无公开API
- **方案**: Web Scraping

### 第三方/精品站

#### iHerb
- **状态**: 有Affiliate API
- **功能**: 产品查询、价格获取
- **适用性**: ⚠️ 有限功能

#### Amazon Singapore
- **状态**: Product Advertising API
- **功能**: 产品搜索、价格查询
- **适用性**: ✅ 可用于价格监控

---

## 技术方案

### 数据获取策略

| 平台 | 方案 | 难度 | 稳定性 |
|------|------|------|--------|
| Shopee | 官方API | 中 | 高 |
| Lazada/RedMart | 官方API | 中 | 高 |
| FairPrice | Web Scraping | 高 | 中 |
| Cold Storage | Web Scraping | 高 | 中 |
| Amazon SG | Product API | 中 | 高 |
| iHerb | Affiliate API | 低 | 高 |

### 推荐技术栈

**后端**:
- Python (FastAPI/Flask)
- Playwright/Selenium (爬虫)
- APScheduler (定时任务)

**数据库**:
- SQLite (轻量本地存储)
- 或 PostgreSQL (如需扩展)

**前端**:
- Vue.js / React (Web界面)
- 或 CLI 工具 (简单版)

---

## 第三方集成服务

### OneCart
- 新加坡本地多渠道电商管理平台
- 支持 Shopee, Lazada, TikTok Shop, Amazon
- 实时库存同步

### API2Cart
- 统一电商API接入服务
- 支持多平台集成

---

## Sources
- [Shopee API Guide](https://api2cart.com/api-technology/shopee-api/)
- [Lazada Open Platform](https://open.lazada.com/)
- [Lazada API Reference](https://open.lazada.com/doc/api.htm)
- [Singapore Online Groceries Guide](https://dollarsandsense.sg/singapore-online-groceries-guide/)
- [RedMart FairPrice Scraping](https://www.actowizsolutions.com/redmart-fairprice-grocery-price-intelligence-singapore.php)
