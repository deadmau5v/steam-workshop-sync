# 🚀 快速开始指南

5 分钟部署 Steam Workshop Sync！

## 方法 1: Docker Compose（推荐）

适合快速部署，包含数据库和应用。

```bash
# 1. 克隆项目
git clone https://github.com/你的用户名/steam-workshop-sync.git
cd steam-workshop-sync

# 2. 快速配置（一行命令）
cat > .env << 'EOF'
POSTGRES_USER=steam_user
POSTGRES_PASSWORD=your_secure_password_here
POSTGRES_DB=steam_workshop
POSTGRES_PORT=5432
STEAM_WORKSHOP_SYNC_DATABASE_URL=postgresql://steam_user:your_secure_password_here@postgres:5432/steam_workshop
STEAM_WORKSHOP_SYNC_PAGE_DELAY=5.0
STEAM_WORKSHOP_SYNC_CYCLE_DELAY=60.0
EOF

# 3. 启动！
docker-compose up -d

# 4. 查看日志
docker-compose logs -f steam-workshop-sync
```

就这么简单！✨

## 方法 2: 使用预构建镜像

如果你已有 PostgreSQL 数据库：

```bash
docker run -d \
  --name steam-workshop-sync \
  --restart unless-stopped \
  -e STEAM_WORKSHOP_SYNC_DATABASE_URL="postgresql://user:pass@host:5432/db" \
  ghcr.io/你的用户名/steam-workshop-sync:latest
```

## 方法 3: 交互式配置

使用友好的交互式脚本：

```bash
# 克隆项目
git clone https://github.com/你的用户名/steam-workshop-sync.git
cd steam-workshop-sync

# 运行配置脚本（会提示输入配置）
make init

# 启动服务
make up

# 查看日志
make logs
```

## 常用命令

```bash
make help          # 查看所有命令
make up            # 启动服务
make down          # 停止服务
make logs          # 查看日志
make restart       # 重启服务
make ps            # 查看状态
make shell         # 进入容器
```

## 验证部署

检查服务是否正常运行：

```bash
# 查看容器状态
docker-compose ps

# 查看日志
docker-compose logs steam-workshop-sync

# 进入数据库查看数据
docker-compose exec postgres psql -U steam_user -d steam_workshop
```

在数据库中：
```sql
-- 查看表
\dt

-- 查看 workshop 数据
SELECT id, title, author FROM workshop_items LIMIT 10;
```

## 🎯 下一步

- 📖 阅读 [完整文档](README.md)
- 🚀 了解 [部署指南](DEPLOYMENT.md)
- 🔧 自定义配置参数
- 📊 设置监控和告警

## 🆘 遇到问题？

1. **容器无法启动**
   ```bash
   docker-compose logs
   ```

2. **数据库连接失败**
   - 检查 `.env` 文件中的数据库配置
   - 确认数据库 URL 格式正确

3. **查看详细日志**
   ```bash
   docker-compose logs -f --tail=100
   ```

4. **重新开始**
   ```bash
   docker-compose down -v  # 清理所有数据
   make init               # 重新配置
   make up                 # 重新启动
   ```

## 📞 获取帮助

- 🐛 [提交 Issue](https://github.com/你的用户名/steam-workshop-sync/issues)
- 📚 [查看文档](README.md)
- 💬 [讨论区](https://github.com/你的用户名/steam-workshop-sync/discussions)

---

**就这么简单！** 🎉 现在你的 Steam Workshop 监控器已经在运行了。

