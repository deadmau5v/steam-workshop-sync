# 使用官方 Python 镜像作为基础镜像
FROM python:3.14-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    postgresql-client \
    lib32gcc-s1 \
    && rm -rf /var/lib/apt/lists/*

# 安装 Steam CMD
RUN mkdir -p /steamcmd && \
    curl -sqL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" | tar zxvf - -C /steamcmd && \
    chmod +x /steamcmd/steamcmd.sh

# 创建下载目录
RUN mkdir -p /app/downloads

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 设置环境变量
ENV UV_SYSTEM_PYTHON=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STEAM_WORKSHOP_SYNC_STEAMCMD_PATH="/steamcmd/steamcmd.sh" \
    STEAM_WORKSHOP_SYNC_DOWNLOAD_DIR="/app/downloads"

# 复制项目文件（优化层缓存）
COPY pyproject.toml uv.lock ./

# 安装依赖
RUN uv sync --frozen --no-dev

# 复制应用代码
COPY . .

# 创建非 root 用户
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /steamcmd

# 切换到非 root 用户
USER appuser

# 健康检查（检查进程是否运行）
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD pgrep -f "python main.py" || exit 1

# 运行数据库迁移并启动应用
CMD ["sh", "-c", "uv run alembic upgrade head && uv run python main.py"]

