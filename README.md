
## 数据库设置

### 1. 配置环境变量

复制 `.env.example` 到 `.env` 并配置数据库连接：

```bash
cp .env.example .env
```

编辑 `.env` 文件，设置你的 PostgreSQL 数据库连接：

```
STEAM_WORKSHOP_SYNC_DATABASE_URL=postgresql://username:password@host:port/database
```

**注意：** 如果密码包含特殊字符（如 `%`、`&` 等），需要进行 URL 编码。例如：
- `%` → `%25`
- `&` → `%26`
- `@` → `%40`

### 2. 运行数据库迁移

创建数据库表：

```bash
uv run alembic upgrade head
```

### 3. 使用数据库功能

在你的代码中使用数据库功能：

```python
from database import save_workshop_item, save_workshop_items, get_workshop_item
from models.workshop import WorkshopItem

# 保存单个项目
item = WorkshopItem(...)
save_workshop_item(item)

# 批量保存项目
items = [WorkshopItem(...), WorkshopItem(...)]
save_workshop_items(items)

# 查询项目
item = get_workshop_item("item_id")
```

### 数据库迁移命令

- 创建新迁移：`uv run alembic revision --autogenerate -m "描述"`
- 应用迁移：`uv run alembic upgrade head`
- 回滚迁移：`uv run alembic downgrade -1`
- 查看迁移历史：`uv run alembic history`
- 查看当前版本：`uv run alembic current`
