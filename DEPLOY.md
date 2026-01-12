# Grocery Manager 部署指南

## 架构概述

```
┌─────────────────────────────────────────────────────────────┐
│                    Cloudflare Pages                         │
│                   (静态前端网页)                             │
│                 grocery-manager.pages.dev                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ API 请求
┌─────────────────────────────────────────────────────────────┐
│                    API Server                                │
│             (Railway / Fly.io / VPS)                        │
│                  FastAPI + SQLite                           │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  Watchlist  │  │  Scheduler  │  │    Email    │         │
│  │   Service   │  │   (每4小时)  │  │   Service   │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│         │                │                │                 │
│         ▼                ▼                ▼                 │
│  ┌──────────────────────────────────────────────┐          │
│  │           Platform Adapters                   │          │
│  │  Amazon | Lazada | Little Farms | Fossa ...   │          │
│  └──────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

## 1. 前端部署 (Cloudflare Pages)

### 方式一: GitHub 集成 (推荐)

1. 将项目推送到 GitHub
2. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com)
3. 进入 Pages → Create a project → Connect to Git
4. 选择你的仓库
5. 构建设置:
   - Build command: (留空)
   - Build output directory: `frontend/public`
6. 点击 Deploy

### 方式二: 直接上传

```bash
# 安装 Wrangler CLI
npm install -g wrangler

# 登录 Cloudflare
wrangler login

# 部署
wrangler pages deploy frontend/public --project-name grocery-manager
```

## 2. 后端 API 部署

### 方式一: Railway (推荐，简单)

1. 登录 [Railway](https://railway.app)
2. New Project → Deploy from GitHub repo
3. 添加环境变量:

```env
# 邮件通知配置
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SENDER_EMAIL=your-email@gmail.com
SENDER_PASSWORD=your-app-password
RECIPIENT_EMAILS=recipient1@email.com,recipient2@email.com
```

4. Railway 会自动检测 Python 项目并部署

### 方式二: Fly.io

1. 安装 Fly CLI: `brew install flyctl`
2. 登录: `fly auth login`
3. 创建 `fly.toml`:

```toml
app = "grocery-manager-api"
primary_region = "sin"

[build]
  builder = "paketobuildpacks/builder:base"

[env]
  PORT = "8080"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true

[[services]]
  internal_port = 8080
  protocol = "tcp"

  [[services.ports]]
    port = 80
    handlers = ["http"]

  [[services.ports]]
    port = 443
    handlers = ["tls", "http"]
```

4. 部署: `fly deploy`

### 方式三: VPS 部署

```bash
# SSH 到服务器
ssh user@your-server

# 克隆项目
git clone https://github.com/yourusername/grocery-manager.git
cd grocery-manager

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium

# 创建环境配置
cp .env.example .env
nano .env  # 编辑配置

# 使用 systemd 运行
sudo nano /etc/systemd/system/grocery-manager.service
```

systemd 服务文件:

```ini
[Unit]
Description=Grocery Manager API
After=network.target

[Service]
User=www-data
WorkingDirectory=/home/user/grocery-manager
Environment="PATH=/home/user/grocery-manager/venv/bin"
ExecStart=/home/user/grocery-manager/venv/bin/python -m src.cli web --port 8080
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# 启动服务
sudo systemctl enable grocery-manager
sudo systemctl start grocery-manager

# 配置 Nginx 反向代理
sudo nano /etc/nginx/sites-available/grocery-manager
```

Nginx 配置:

```nginx
server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 3. 配置前端 API 地址

部署完后端后，在前端设置中配置 API 地址:

1. 打开前端网页
2. 点击右上角 ⚙️ 设置
3. 输入 API 服务器地址: `https://your-api-server.com`
4. 保存

或者在 Cloudflare Pages 环境变量中设置 `API_URL`

## 4. 邮件通知配置

### Gmail 配置

1. 开启 Gmail 二步验证
2. 创建应用专用密码:
   - 访问 https://myaccount.google.com/apppasswords
   - 选择 "邮件" 和设备
   - 生成密码
3. 使用生成的密码作为 `SENDER_PASSWORD`

### 其他邮件服务

```env
# QQ 邮箱
SMTP_SERVER=smtp.qq.com
SMTP_PORT=587

# 163 邮箱
SMTP_SERVER=smtp.163.com
SMTP_PORT=465

# Outlook
SMTP_SERVER=smtp.office365.com
SMTP_PORT=587
```

## 5. 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 安装 Playwright
playwright install chromium

# 初始化数据库和监控列表
python3 -m src.cli watch init

# 启动 Web 服务器
python3 -m src.cli web --port 8080

# 访问 http://localhost:8080
```

## 6. CLI 命令

```bash
# 初始化 FoodGuard 产品监控列表
python3 -m src.cli watch init

# 查看监控列表
python3 -m src.cli watch list

# 手动检查库存
python3 -m src.cli watch check

# 生成每周采购清单
python3 -m src.cli watch weekly

# 查看未读提醒
python3 -m src.cli watch alerts

# 启动 Web 服务器
python3 -m src.cli web --port 8080

# 启动调度器 (自动检查)
python3 -m src.cli scheduler
```

## 7. 定时任务

系统会自动:
- 每4小时检查一次库存
- 周六早上9点生成每周采购清单
- 发现补货或降价时发送邮件通知

## 故障排除

### Playwright 问题

```bash
# 重新安装浏览器
playwright install chromium --with-deps
```

### 数据库重置

```bash
rm grocery_manager.db
python3 -m src.cli watch init
```

### 查看日志

```bash
# Railway
railway logs

# Fly.io
fly logs

# systemd
journalctl -u grocery-manager -f
```
