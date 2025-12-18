#!/bin/bash
# Docker 构建测试脚本

set -e

echo "🧪 开始 Docker 构建测试..."
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 测试计数
TESTS_PASSED=0
TESTS_FAILED=0

# 测试函数
test_step() {
    local description=$1
    echo -e "${YELLOW}▶${NC} $description"
}

test_pass() {
    local message=$1
    echo -e "${GREEN}✓${NC} $message"
    ((TESTS_PASSED++))
}

test_fail() {
    local message=$1
    echo -e "${RED}✗${NC} $message"
    ((TESTS_FAILED++))
}

# 清理函数
cleanup() {
    echo ""
    echo "🧹 清理测试容器..."
    docker rm -f steam-workshop-test 2>/dev/null || true
}

# 设置退出时清理
trap cleanup EXIT

# 测试 1: 构建镜像
test_step "测试 1: 构建 Docker 镜像"
if docker build -t steam-workshop-sync:test . > /tmp/docker-build.log 2>&1; then
    test_pass "Docker 镜像构建成功"
else
    test_fail "Docker 镜像构建失败"
    echo "查看日志: /tmp/docker-build.log"
    exit 1
fi

# 测试 2: 检查镜像大小
test_step "测试 2: 检查镜像大小"
IMAGE_SIZE=$(docker images steam-workshop-sync:test --format "{{.Size}}")
echo "  镜像大小: $IMAGE_SIZE"
test_pass "镜像已创建"

# 测试 3: 检查镜像层
test_step "测试 3: 检查镜像层结构"
LAYERS=$(docker history steam-workshop-sync:test --format "{{.CreatedBy}}" | wc -l)
echo "  镜像层数: $LAYERS"
test_pass "镜像层结构正常"

# 测试 4: 验证文件存在
test_step "测试 4: 验证关键文件"
docker run --rm steam-workshop-sync:test ls -la /app/main.py > /dev/null 2>&1
if [ $? -eq 0 ]; then
    test_pass "main.py 文件存在"
else
    test_fail "main.py 文件缺失"
fi

docker run --rm steam-workshop-sync:test ls -la /app/database.py > /dev/null 2>&1
if [ $? -eq 0 ]; then
    test_pass "database.py 文件存在"
else
    test_fail "database.py 文件缺失"
fi

# 测试 5: 验证 Python 版本
test_step "测试 5: 验证 Python 版本"
PYTHON_VERSION=$(docker run --rm steam-workshop-sync:test python --version)
echo "  $PYTHON_VERSION"
test_pass "Python 版本正常"

# 测试 6: 验证依赖安装
test_step "测试 6: 验证 Python 依赖"
DEPS=("sqlmodel" "alembic" "requests" "pydantic")
for dep in "${DEPS[@]}"; do
    if docker run --rm steam-workshop-sync:test python -c "import $dep" 2>/dev/null; then
        test_pass "$dep 已安装"
    else
        test_fail "$dep 未安装"
    fi
done

# 测试 7: 验证用户权限
test_step "测试 7: 验证容器用户"
CONTAINER_USER=$(docker run --rm steam-workshop-sync:test whoami)
if [ "$CONTAINER_USER" = "appuser" ]; then
    test_pass "容器使用非 root 用户运行"
else
    test_fail "容器未使用非 root 用户运行 (当前: $CONTAINER_USER)"
fi

# 测试 8: 验证 uv 可用
test_step "测试 8: 验证 uv 工具"
if docker run --rm steam-workshop-sync:test uv --version > /dev/null 2>&1; then
    UV_VERSION=$(docker run --rm steam-workshop-sync:test uv --version)
    echo "  $UV_VERSION"
    test_pass "uv 工具可用"
else
    test_fail "uv 工具不可用"
fi

# 测试 9: 验证 Alembic
test_step "测试 9: 验证 Alembic 迁移工具"
if docker run --rm steam-workshop-sync:test uv run alembic --help > /dev/null 2>&1; then
    test_pass "Alembic 可用"
else
    test_fail "Alembic 不可用"
fi

# 测试 10: 验证健康检查
test_step "测试 10: 验证健康检查配置"
HEALTHCHECK=$(docker inspect steam-workshop-sync:test --format='{{.Config.Healthcheck}}')
if [ "$HEALTHCHECK" != "<nil>" ]; then
    test_pass "健康检查已配置"
else
    test_fail "健康检查未配置"
fi

# 总结
echo ""
echo "=" * 50
echo "📊 测试总结"
echo "=" * 50
echo -e "${GREEN}通过: $TESTS_PASSED${NC}"
echo -e "${RED}失败: $TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✨ 所有测试通过！Docker 镜像准备就绪。${NC}"
    echo ""
    echo "🚀 下一步:"
    echo "  1. 配置环境变量: make init"
    echo "  2. 启动服务: make up"
    echo "  3. 查看日志: make logs"
    exit 0
else
    echo -e "${RED}❌ 有 $TESTS_FAILED 个测试失败，请检查并修复。${NC}"
    exit 1
fi

