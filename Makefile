.PHONY: help init build up down logs restart clean test

help: ## 显示帮助信息
	@echo "Steam Workshop Sync - 可用命令："
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

init: ## 初始化环境配置
	@bash scripts/init-env.sh

build: ## 构建 Docker 镜像
	docker-compose build

up: ## 启动服务
	docker-compose up -d

down: ## 停止服务
	docker-compose down

logs: ## 查看日志
	docker-compose logs -f steam-workshop-sync

logs-all: ## 查看所有服务日志
	docker-compose logs -f

restart: ## 重启服务
	docker-compose restart steam-workshop-sync

clean: ## 清理容器和数据卷
	docker-compose down -v

ps: ## 查看服务状态
	docker-compose ps

shell: ## 进入应用容器
	docker-compose exec steam-workshop-sync sh

db-shell: ## 进入数据库容器
	docker-compose exec postgres psql -U $${POSTGRES_USER:-steam_user} -d $${POSTGRES_DB:-steam_workshop}

test: ## 测试 Docker 构建
	@bash scripts/test-docker.sh

dev-setup: ## 本地开发环境设置
	uv sync
	uv run alembic upgrade head

dev-run: ## 本地开发运行
	uv run python main.py

dev-migrate: ## 创建数据库迁移
	uv run alembic revision --autogenerate -m "$(msg)"

dev-upgrade: ## 应用数据库迁移
	uv run alembic upgrade head

dev-downgrade: ## 回滚数据库迁移
	uv run alembic downgrade -1

