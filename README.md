# Steam Workshop Sync

[![Build and Release](https://github.com/deadmau5v/steam-workshop-sync/actions/workflows/release.yml/badge.svg)](https://github.com/deadmau5v/steam-workshop-sync/actions/workflows/release.yml)
[![Docker Image](https://img.shields.io/badge/docker-ghcr.io-blue)](https://github.com/deadmau5v/steam-workshop-sync/pkgs/container/steam-workshop-sync)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Steam Workshop 数据同步工具，用于监控和同步 Steam 创意工坊的物品数据到数据库。

## ✨ 特性

- 🔄 自动持续监控 Steam Workshop 更新
- 💾 数据存储到 PostgreSQL 数据库
- 🐳 Docker 容器化部署，支持多架构（amd64/arm64）
- 🔧 可配置的延迟和监控策略
- 📊 详细的日志记录
- 🔒 自动安全扫描和 SBOM 生成
- 🚀 GitHub Actions 自动化 CI/CD

## 快速开始

### 方式一：使用 Docker Compose（推荐）

这是最简单的部署方式，会自动创建 PostgreSQL 数据库和应用容器。

1. 克隆仓库：
```bash
git clone https://github.com/deadmau5v/steam-workshop-sync.git
cd steam-workshop-sync
```

2. 创建环境变量文件：
```bash
# 创建 .env 文件
cat > .env << EOF
POSTGRES_USER=steam_user
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=steam_workshop
POSTGRES_PORT=5432

STEAM_WORKSHOP_SYNC_DATABASE_URL=postgresql://steam_user:your_secure_password@postgres:5432/steam_workshop
STEAM_WORKSHOP_SYNC_APP_ID=647960
STEAM_WORKSHOP_SYNC_PAGE_DELAY=5.0
STEAM_WORKSHOP_SYNC_CYCLE_DELAY=60.0
EOF
```

3. 启动服务：
```bash
docker-compose up -d
```

4. 查看日志：
```bash
docker-compose logs -f steam-workshop-sync
```

5. 停止服务：
```bash
docker-compose down
```

### 方式二：使用预构建的 Docker 镜像

如果你已经有一个 PostgreSQL 数据库：

```bash
docker run -d \
  --name steam-workshop-sync \
  -e STEAM_WORKSHOP_SYNC_DATABASE_URL="postgresql://user:password@host:5432/db" \
  -e STEAM_WORKSHOP_SYNC_APP_ID="647960" \
  -e STEAM_WORKSHOP_SYNC_PAGE_DELAY=5.0 \
  -e STEAM_WORKSHOP_SYNC_CYCLE_DELAY=60.0 \
  ghcr.io/deadmau5v/steam-workshop-sync:latest
```

### 方式三：本地开发运行

1. 安装依赖：
```bash
# 确保已安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装项目依赖
uv sync
```

2. 配置环境变量：
```bash
cp .env.example .env
# 编辑 .env 文件配置数据库连接
```

3. 运行数据库迁移：
```bash
uv run alembic upgrade head
```

4. 启动应用：
```bash
uv run python main.py
```

## 环境变量配置

| 变量名 | 说明 | 默认值 | 必需 |
|--------|------|--------|------|
| `STEAM_WORKSHOP_SYNC_DATABASE_URL` | PostgreSQL 数据库连接字符串 | - | ✅ |
| `STEAM_WORKSHOP_SYNC_APP_ID` | Steam 游戏 App ID（用于访问对应的 Workshop） | - | ✅ |
| `STEAM_WORKSHOP_SYNC_PAGE_DELAY` | 页面间延迟（秒） | 5.0 | ❌ |
| `STEAM_WORKSHOP_SYNC_CYCLE_DELAY` | 循环间延迟（秒） | 60.0 | ❌ |

**数据库连接字符串格式：**
```
postgresql://用户名:密码@主机:端口/数据库名
```

**注意：** 如果密码包含特殊字符（如 `%`、`&` 等），需要进行 URL 编码：
- `%` → `%25`
- `&` → `%26`
- `@` → `%40`

## 数据库管理

### 数据库迁移命令

```bash
# 创建新迁移
uv run alembic revision --autogenerate -m "描述"

# 应用迁移
uv run alembic upgrade head

# 回滚迁移
uv run alembic downgrade -1

# 查看迁移历史
uv run alembic history

# 查看当前版本
uv run alembic current
```

### 数据库 API 使用

```python
from database import save_workshop_item, save_workshop_items, get_workshop_item
from models.workshop import WorkshopItem

# 保存单个项目
item = WorkshopItem(...)
save_workshop_item(item, exist_ok=True)

# 批量保存项目
items = [WorkshopItem(...), WorkshopItem(...)]
save_workshop_items(items)

# 查询项目
item = get_workshop_item("item_id")
```

## 构建 Docker 镜像

如果你想自己构建 Docker 镜像：

```bash
# 构建镜像
docker build -t steam-workshop-sync:latest .

# 运行镜像
docker run -d \
  --name steam-workshop-sync \
  -e STEAM_WORKSHOP_SYNC_DATABASE_URL="postgresql://user:password@host:5432/db" \
  -e STEAM_WORKSHOP_SYNC_APP_ID="647960" \
  steam-workshop-sync:latest
```

## CI/CD 发布流程

本项目使用 GitHub Actions 自动构建和发布 Docker 镜像到 GitHub Container Registry (GHCR)。
发布镜像运行时请确保设置必需变量：`STEAM_WORKSHOP_SYNC_DATABASE_URL` 和 `STEAM_WORKSHOP_SYNC_APP_ID`。

### 发布新版本

1. 创建并推送版本标签：
```bash
git tag v1.0.0
git push origin v1.0.0
```

2. GitHub Actions 会自动：
   - 构建 Docker 镜像（支持 amd64 和 arm64）
   - 推送到 GHCR
   - 创建 GitHub Release

3. 拉取镜像：
```bash
docker pull ghcr.io/deadmau5v/steam-workshop-sync:v1.0.0
# 或使用 latest
docker pull ghcr.io/deadmau5v/steam-workshop-sync:latest
```

4. 运行镜像示例：
```bash
docker run -d \
  --name steam-workshop-sync \
  --restart unless-stopped \
  -e STEAM_WORKSHOP_SYNC_DATABASE_URL="postgresql://user:password@host:5432/db" \
  -e STEAM_WORKSHOP_SYNC_APP_ID="647960" \
  -e STEAM_WORKSHOP_SYNC_PAGE_DELAY=5.0 \
  -e STEAM_WORKSHOP_SYNC_CYCLE_DELAY=60.0 \
  ghcr.io/deadmau5v/steam-workshop-sync:latest
```

### 配置 GHCR

在项目的 GitHub 设置中：
1. 前往 Settings → Actions → General
2. 在 "Workflow permissions" 中选择 "Read and write permissions"
3. 保存更改

镜像将发布到：`ghcr.io/<your-username>/steam-workshop-sync`

## 故障排查

### 查看容器日志
```bash
# Docker Compose
docker-compose logs -f steam-workshop-sync

# 单独容器
docker logs -f steam-workshop-sync
```

### 进入容器调试
```bash
# Docker Compose
docker-compose exec steam-workshop-sync sh

# 单独容器
docker exec -it steam-workshop-sync sh
```

### 数据库连接问题
- 确保数据库 URL 格式正确
- 检查数据库是否可访问（防火墙/网络）
- 验证数据库凭证是否正确

## 许可证

[MIT License](LICENSE)

## 贡献

欢迎提交 Issue 和 Pull Request！
