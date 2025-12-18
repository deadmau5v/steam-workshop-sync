# 部署指南

本文档详细说明如何部署和发布 Steam Workshop Sync 项目。

## 📦 部署方式

### 1. Docker Compose 部署（推荐新手）

最简单的部署方式，包含数据库和应用。

```bash
# 1. 克隆项目
git clone https://github.com/deadmau5v/steam-workshop-sync.git
cd steam-workshop-sync

# 2. 初始化环境配置（交互式）
make init
# 或手动创建
bash scripts/init-env.sh

# 3. 启动服务
make up
# 或
docker-compose up -d

# 4. 查看日志
make logs
# 或
docker-compose logs -f steam-workshop-sync
```

### 2. 使用预构建镜像部署

如果你已经有 PostgreSQL 数据库：

```bash
docker run -d \
  --name steam-workshop-sync \
  --restart unless-stopped \
  -e STEAM_WORKSHOP_SYNC_DATABASE_URL="postgresql://user:password@host:5432/db" \
  -e STEAM_WORKSHOP_SYNC_PAGE_DELAY=5.0 \
  -e STEAM_WORKSHOP_SYNC_CYCLE_DELAY=60.0 \
  ghcr.io/deadmau5v/steam-workshop-sync:latest
```

### 3. 本地开发

```bash
# 1. 安装依赖
make dev-setup
# 或
uv sync
uv run alembic upgrade head

# 2. 配置 .env 文件
# 编辑 .env 设置本地数据库连接

# 3. 运行
make dev-run
# 或
uv run python main.py
```

## 🚀 CI/CD 发布流程

本项目使用 GitHub Actions 自动化构建和发布，提供完整的安全扫描和自动化发布流程。

### 发布新版本

1. **提交代码**
   ```bash
   git add .
   git commit -m "feat: 新功能描述"
   git push origin master
   ```

2. **创建版本标签**
   ```bash
   # 创建标签（遵循语义化版本）
   git tag v1.0.0

   # 推送标签到远程
   git push origin v1.0.0
   ```

3. **自动化流程**

   推送标签后，GitHub Actions 会自动执行以下操作：

   #### 构建阶段
   - ✅ 构建多架构 Docker 镜像（amd64 和 arm64）
   - ✅ 生成镜像元数据和标签
   - ✅ 推送镜像到 GitHub Container Registry (GHCR)
   - ✅ 生成 Provenance 和 SBOM（软件物料清单）

   #### 安全扫描阶段
   - ✅ 使用 Trivy 扫描镜像漏洞（CRITICAL 和 HIGH 级别）
   - ✅ 生成 SBOM (Software Bill of Materials)
   - ✅ 上传扫描结果到 GitHub Security 面板
   - ✅ 附加安全报告到 Release

   #### 发布阶段
   - ✅ 自动生成 Changelog（基于 Git 提交历史）
   - ✅ 创建 GitHub Release 包含详细说明
   - ✅ 附加 SBOM 和安全扫描报告
   - ✅ 标记镜像为 `latest` 和版本号标签

4. **使用发布的镜像**
   ```bash
   # 拉取特定版本
   docker pull ghcr.io/deadmau5v/steam-workshop-sync:v1.0.0

   # 拉取最新版本
   docker pull ghcr.io/deadmau5v/steam-workshop-sync:latest
   ```

### 配置 GitHub Actions

#### 步骤 1: 配置仓库权限

1. 前往你的 GitHub 仓库
2. 点击 **Settings** → **Actions** → **General**
3. 在 **Workflow permissions** 部分：
   - 选择 **Read and write permissions**
   - 勾选 **Allow GitHub Actions to create and approve pull requests**
4. 点击 **Save**

#### 步骤 2: 启用安全功能（可选但推荐）

1. 点击 **Settings** → **Code security and analysis**
2. 启用以下功能：
   - **Dependency graph** - 依赖关系图
   - **Dependabot alerts** - 依赖安全警报
   - **Dependabot security updates** - 自动安全更新
   - **Code scanning** - 代码扫描（集成 Trivy 结果）

#### 步骤 3: 验证工作流

查看 `.github/workflows/` 目录下的工作流文件：

- `release.yml` - 发布工作流（标签触发）
  - 多架构镜像构建
  - 安全扫描和 SBOM 生成
  - 自动 Release 创建
- `docker-test.yml` - 测试工作流（PR/Push 触发）
  - 构建测试验证

#### 步骤 4: 测试发布

创建一个测试标签：

```bash
git tag v0.0.1-test
git push origin v0.0.1-test
```

前往 **Actions** 标签页查看工作流运行状态。

### 版本管理策略

使用语义化版本（Semantic Versioning）：

- **主版本号（Major）**: `v2.0.0` - 不兼容的 API 修改
- **次版本号（Minor）**: `v1.1.0` - 向后兼容的新功能
- **修订号（Patch）**: `v1.0.1` - 向后兼容的问题修复

示例：
```bash
# 修复 bug
git tag v1.0.1
git push origin v1.0.1

# 新增功能
git tag v1.1.0
git push origin v1.1.0

# 重大更新
git tag v2.0.0
git push origin v2.0.0
```

### 镜像标签策略

每次发布会生成以下标签：

- `v1.2.3` - 完整版本号
- `v1.2` - 主要和次要版本
- `v1` - 主要版本
- `latest` - 最新版本（仅在主分支）

所有镜像支持多架构：
- `linux/amd64` - x86_64 架构（标准服务器）
- `linux/arm64` - ARM64 架构（Apple Silicon、ARM 服务器）

示例：
```bash
# 拉取特定版本（自动选择适合的架构）
docker pull ghcr.io/deadmau5v/steam-workshop-sync:v1.2.3

# 拉取 1.2.x 最新版
docker pull ghcr.io/deadmau5v/steam-workshop-sync:v1.2

# 拉取 1.x.x 最新版
docker pull ghcr.io/deadmau5v/steam-workshop-sync:v1

# 拉取最新版
docker pull ghcr.io/deadmau5v/steam-workshop-sync:latest

# 强制拉取特定架构
docker pull --platform linux/amd64 ghcr.io/deadmau5v/steam-workshop-sync:latest
docker pull --platform linux/arm64 ghcr.io/deadmau5v/steam-workshop-sync:latest
```

### 安全和合规性

每次发布都包含完整的安全报告：

1. **漏洞扫描报告** (`trivy-results.sarif`)
   - 扫描 CRITICAL 和 HIGH 级别漏洞
   - 自动上传到 GitHub Security 面板
   - 可在 Release 页面下载完整报告

2. **SBOM（软件物料清单）** (`sbom.spdx.json`)
   - SPDX 格式的完整依赖清单
   - 用于合规性审计和供应链安全
   - 可在 Release 页面下载

3. **镜像签名和证明**
   - 启用 Docker Provenance
   - 包含构建环境和依赖信息
   - 可验证镜像完整性

#### 查看安全报告

```bash
# 在 GitHub 仓库中查看
# 1. 前往 Security → Code scanning alerts
# 2. 查看 Trivy 扫描结果

# 下载 SBOM
curl -L -o sbom.json https://github.com/deadmau5v/steam-workshop-sync/releases/download/v1.0.0/sbom.spdx.json

# 验证镜像
docker buildx imagetools inspect ghcr.io/deadmau5v/steam-workshop-sync:v1.0.0
```

## 🔧 配置说明

### 环境变量

| 变量名 | 说明 | 必需 | 默认值 |
|--------|------|------|--------|
| `STEAM_WORKSHOP_SYNC_DATABASE_URL` | PostgreSQL 数据库连接字符串 | ✅ | - |
| `STEAM_WORKSHOP_SYNC_PAGE_DELAY` | 页面间延迟（秒） | ❌ | 5.0 |
| `STEAM_WORKSHOP_SYNC_CYCLE_DELAY` | 循环间延迟（秒） | ❌ | 60.0 |

### 数据库连接字符串格式

```
postgresql://用户名:密码@主机:端口/数据库名
```

**Docker Compose 内部连接**（使用服务名）：
```
postgresql://steam_user:password@postgres:5432/steam_workshop
```

**外部数据库连接**：
```
postgresql://user:password@192.168.1.100:5432/dbname
```

## 📊 监控和日志

### 查看日志

```bash
# Docker Compose
make logs
docker-compose logs -f steam-workshop-sync

# 单独容器
docker logs -f steam-workshop-sync
```

### 查看服务状态

```bash
make ps
docker-compose ps
```

### 进入容器调试

```bash
# 进入应用容器
make shell
docker-compose exec steam-workshop-sync sh

# 进入数据库容器
make db-shell
docker-compose exec postgres psql -U steam_user -d steam_workshop
```

## 🛠️ 常用命令

### Docker Compose

```bash
make help          # 显示所有可用命令
make init          # 初始化环境配置
make up            # 启动服务
make down          # 停止服务
make logs          # 查看应用日志
make restart       # 重启服务
make clean         # 清理容器和数据
```

### 本地开发

```bash
make dev-setup     # 设置开发环境
make dev-run       # 运行应用
make dev-migrate msg="描述"  # 创建数据库迁移
make dev-upgrade   # 应用迁移
make dev-downgrade # 回滚迁移
```

## 🐛 故障排查

### 1. 容器无法启动

检查日志：
```bash
docker-compose logs steam-workshop-sync
```

常见问题：
- 数据库连接失败：检查 `DATABASE_URL` 配置
- 端口冲突：修改 `docker-compose.yml` 中的端口映射

### 2. 数据库连接失败

```bash
# 测试数据库连接
docker-compose exec postgres pg_isready -U steam_user

# 查看数据库日志
docker-compose logs postgres
```

### 3. 镜像拉取失败

确保你已登录 GHCR：
```bash
echo $GITHUB_TOKEN | docker login ghcr.io -u deadmau5v --password-stdin
```

### 4. GitHub Actions 失败

1. 检查仓库权限设置
2. 查看 Actions 标签页的错误日志
3. 确认 `.github/workflows/` 文件语法正确
