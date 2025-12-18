#!/bin/bash
# 快速初始化环境变量配置文件

set -e

echo "🚀 初始化 Steam Workshop Sync 环境配置"
echo ""

# 检查 .env 文件是否已存在
if [ -f .env ]; then
    read -p "⚠️  .env 文件已存在，是否覆盖？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ 已取消"
        exit 0
    fi
fi

# 生成随机密码
generate_password() {
    openssl rand -base64 32 | tr -d "=+/" | cut -c1-25
}

# 获取用户输入或使用默认值
read -p "PostgreSQL 用户名 (默认: steam_user): " POSTGRES_USER
POSTGRES_USER=${POSTGRES_USER:-steam_user}

read -p "PostgreSQL 密码 (留空自动生成): " POSTGRES_PASSWORD
if [ -z "$POSTGRES_PASSWORD" ]; then
    POSTGRES_PASSWORD=$(generate_password)
    echo "  → 自动生成密码: $POSTGRES_PASSWORD"
fi

read -p "PostgreSQL 数据库名 (默认: steam_workshop): " POSTGRES_DB
POSTGRES_DB=${POSTGRES_DB:-steam_workshop}

read -p "PostgreSQL 端口 (默认: 5432): " POSTGRES_PORT
POSTGRES_PORT=${POSTGRES_PORT:-5432}

read -p "Steam Workshop APP ID (默认: 647960): " STEAM_WORKSHOP_SYNC_APP_ID
STEAM_WORKSHOP_SYNC_APP_ID=${STEAM_WORKSHOP_SYNC_APP_ID:-647960}

read -p "页面间延迟（秒，默认: 5.0）: " PAGE_DELAY
PAGE_DELAY=${PAGE_DELAY:-5.0}

read -p "循环间延迟（秒，默认: 60.0）: " CYCLE_DELAY
CYCLE_DELAY=${CYCLE_DELAY:-60.0}

# 创建 .env 文件
cat > .env << EOF
# PostgreSQL 数据库配置
POSTGRES_USER=$POSTGRES_USER
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=$POSTGRES_DB
POSTGRES_PORT=$POSTGRES_PORT

# Steam Workshop Sync 应用配置
# 数据库连接字符串（使用 Docker Compose 服务名）
STEAM_WORKSHOP_SYNC_DATABASE_URL=postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@postgres:5432/$POSTGRES_DB

# Steam 游戏 APP ID（用于访问对应的 Workshop）
STEAM_WORKSHOP_SYNC_APP_ID=$STEAM_WORKSHOP_SYNC_APP_ID

# 页面间延迟（秒）
STEAM_WORKSHOP_SYNC_PAGE_DELAY=$PAGE_DELAY

# 循环间延迟（秒）
STEAM_WORKSHOP_SYNC_CYCLE_DELAY=$CYCLE_DELAY
EOF

echo ""
echo "✅ 配置文件创建成功！"
echo ""
echo "📋 配置信息："
echo "  - 数据库用户: $POSTGRES_USER"
echo "  - 数据库名: $POSTGRES_DB"
echo "  - 数据库端口: $POSTGRES_PORT"
echo "  - APP ID: $STEAM_WORKSHOP_SYNC_APP_ID"
echo "  - 页面延迟: ${PAGE_DELAY}秒"
echo "  - 循环延迟: ${CYCLE_DELAY}秒"
echo ""
echo "🐳 现在可以运行以下命令启动服务："
echo "  docker-compose up -d"
echo ""
echo "📊 查看日志："
echo "  docker-compose logs -f steam-workshop-sync"

