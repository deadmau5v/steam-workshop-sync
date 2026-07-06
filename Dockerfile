# 使用官方 Python 镜像作为基础镜像
FROM python:3.14-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
# lib32gcc-s1 仅在 amd64 上可用（Steam CMD 需要），arm64 跳过
RUN apt-get update && apt-get install -y \
    curl \
    postgresql-client \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && (dpkg --print-architecture | grep -q amd64 \
        && apt-get update \
        && apt-get install -y lib32gcc-s1 lib32stdc++6 \
        && rm -rf /var/lib/apt/lists/* \
        || true)

# 安装 Steam CMD（仅 amd64 有官方二进制；arm64 跳过）
RUN mkdir -p /steamcmd && \
    if [ "$(dpkg --print-architecture)" = "amd64" ]; then \
        curl -sqL "https://media.steampowered.com/client/installer/steamcmd_linux.tar.gz" | tar zxvf - -C /steamcmd && \
        chmod +x /steamcmd/steamcmd.sh; \
    else \
        echo "Steam CMD 仅支持 amd64，当前架构跳过安装（不影响元数据抓取，但无法下载 mod 文件）"; \
    fi

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
RUN uv sync --no-dev

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

# 初始化数据库表（create_all 幂等，表已存在时跳过）并启动应用
CMD ["sh", "-c", "uv run python -c \"from database import init_db; init_db()\" && uv run python main.py"]
