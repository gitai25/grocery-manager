# Task Plan: 新加坡日常用品与食品采购管理系统

## Goal
构建一个本地采购管理系统，能够管理家庭库存、自动匹配新加坡电商平台价格、并支持定期自动/半自动下单。

## Phases
- [x] Phase 1: 需求分析与技术选型
- [x] Phase 2: 研究新加坡电商平台与API接入方案
- [x] Phase 3: 设计系统架构
- [x] Phase 4: 实现核心功能模块 (MVP)
- [x] Phase 5: 扩展平台支持
- [ ] Phase 6: 集成测试与部署

## 已接入平台

### 主流电商 (2/5)
| 平台 | 状态 | 接入方式 | 特点 |
|------|------|----------|------|
| FairPrice | ✅ 已完成 | Playwright 爬虫 | 新加坡最大超市 |
| Amazon SG | ✅ 已完成 | Playwright 爬虫 | 综合电商 |
| RedMart/Lazada | 🔧 框架就绪 | Open Platform API | 需API凭证 |
| Shopee | 🔧 框架就绪 | Open Platform API | 需API凭证 |
| Cold Storage | 📝 待开发 | Playwright 爬虫 | - |

### 精品站 (4/4)
| 平台 | 状态 | 接入方式 | 特点 |
|------|------|----------|------|
| iHerb | ✅ 已完成 | Playwright 爬虫 | 保健品、维生素 |
| Little Farms | ✅ 已完成 | Playwright 爬虫 | 有机食品、精品 |
| Ryan's Grocery | ✅ 已完成 | Playwright 爬虫 | 进口食材、澳洲牛肉 |
| Meidi-Ya | ✅ 已完成 | Playwright 爬虫 | 日本食品、清酒 |

## CLI 命令

```bash
# 查看所有可用平台
grocery-manager price platforms

# 在指定平台搜索
grocery-manager price search "牛奶" -p fairprice
grocery-manager price search "vitamin" -p iherb
grocery-manager price search "wagyu" -p meidiya

# 多平台比价
grocery-manager price compare "鸡蛋" -p fairprice,amazon_sg,little_farms

# 全平台比价（较慢）
grocery-manager price compare-all "olive oil"
```

## 项目文件

```
grocery-manager/
├── src/adapters/
│   ├── fairprice.py      ✅ NTUC FairPrice
│   ├── amazon_sg.py      ✅ Amazon Singapore
│   ├── iherb.py          ✅ iHerb (保健品)
│   ├── little_farms.py   ✅ Little Farms (有机)
│   ├── ryans_grocery.py  ✅ Ryan's Grocery (进口)
│   └── meidiya.py        ✅ Meidi-Ya (日本)
```

## 技术栈
- **后端**: Python + FastAPI + SQLite
- **爬虫**: Playwright (Chromium)
- **调度**: APScheduler
- **CLI**: Click + Rich

## 待完成功能
- [ ] Cold Storage 适配器
- [ ] Lazada/Shopee API集成（需注册开发者账号）
- [ ] 通知推送 (Telegram/Email)
- [ ] Web Dashboard
- [ ] 订单自动下单

## Status
**Phase 5 Complete** - 已接入6个平台（FairPrice、Amazon、iHerb、Little Farms、Ryan's、Meidi-Ya）
