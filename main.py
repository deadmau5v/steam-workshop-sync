from datetime import datetime
import os
from pathlib import Path
import time

from database import (
    create_asset_record,
    create_file_record,
    get_existing_asset_id,
    get_items_without_sync_status,
    get_pending_sync_items,
    init_db,
    save_workshop_item,
    update_asset_record,
    update_sync_status_completed,
    upsert_sync_status,
)
from dotenv import load_dotenv
from models.workshop import Pagination, WorkshopItem
from services.mod_sync import ModSyncService
from spiders.workshop import Wrokshop
from utils.log import get_logger

load_dotenv()

logger = get_logger(__name__)

# 配置参数
PAGE_DELAY = float(os.getenv("STEAM_WORKSHOP_SYNC_PAGE_DELAY", 5.0))  # 页面间延迟（秒）
CYCLE_DELAY = float(os.getenv("STEAM_WORKSHOP_SYNC_CYCLE_DELAY", 60.0))  # 循环间延迟（秒）
# 快速增量抓取页数（0 表示每轮全量扫；建议 5，每 10 轮自动进行一次全量扫）
INCREMENTAL_PAGES = int(os.getenv("STEAM_WORKSHOP_SYNC_INCREMENTAL_PAGES", "5"))

# Mod 文件同步配置
MOD_SYNC_ENABLED = os.getenv("STEAM_WORKSHOP_SYNC_MOD_ENABLED", "false").lower() == "true"
MOD_SYNC_BATCH_SIZE = int(os.getenv("STEAM_WORKSHOP_SYNC_MOD_BATCH_SIZE", "5"))
MOD_SYNC_DELAY = float(os.getenv("STEAM_WORKSHOP_SYNC_MOD_SYNC_DELAY", "300"))  # mod 同步轮次间隔（秒）


def wait_for_db(max_retries: int = 30, delay: int = 2) -> bool:
    """等待数据库可用（启动时重试连接）"""
    for attempt in range(1, max_retries + 1):
        try:
            init_db()
            logger.info(f"✅ 数据库连接成功（第 {attempt} 次尝试）")
            return True
        except Exception as e:
            logger.warning(f"⏳ 等待数据库就绪... 第 {attempt}/{max_retries} 次尝试失败: {e}")
            time.sleep(delay)
    logger.error(f"❌ 数据库连接失败，已达到最大重试次数 {max_retries}")
    return False


def process_page(workshop: Wrokshop, page: int) -> tuple[int, int]:
    """
    处理单个页面的数据

    Args:
        workshop: Workshop 爬虫实例
        page: 页码

    Returns:
        tuple: (总页数, 处理的项目数)
    """
    try:
        result = workshop.get_new_items(page)
        pagination: Pagination = result["pagination"]
        items: list[WorkshopItem] = result["items"]

        logger.info(f"📄 第 {pagination.current_page}/{pagination.total_pages} 页 - 找到 {pagination.items_count} 个项目")

        processed_count = 0
        for idx, item in enumerate(items, 1):
            logger.info(f"  [{idx}/{pagination.items_count}] 处理项目: {item.title}")

            try:
                item_info = workshop.get_items_info(item)
                save_workshop_item(item_info, exist_ok=True)
                processed_count += 1
            except Exception as e:
                logger.error(f"  处理项目 {item.id} 失败: {e}")
                continue

        logger.info(f"✅ 第 {page} 页处理完成，成功: {processed_count}/{pagination.items_count}")
        return pagination.total_pages, processed_count

    except Exception as e:
        logger.error(f"❌ 处理第 {page} 页失败: {e}")
        raise


def run_metadata_sync(workshop: Wrokshop, full_scan: bool = False) -> None:
    """执行一轮元数据抓取同步

    Args:
        workshop: Workshop 爬虫实例
        full_scan: 是否全量扫描所有页面。如果为 False 且 INCREMENTAL_PAGES > 0，则仅抓取前 INCREMENTAL_PAGES 页。
    """
    cycle_start_time = datetime.now()
    logger.info(f"\n{'=' * 60}")
    scan_type = "全量" if full_scan or INCREMENTAL_PAGES <= 0 else f"增量 (前 {INCREMENTAL_PAGES} 页)"
    logger.info(f"🔄 开始元数据抓取 [{scan_type}] - {cycle_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"{'=' * 60}")

    try:
        # 首先获取第一页以确定总页数
        total_pages, _ = process_page(workshop, 1)

        target_pages = total_pages if (full_scan or INCREMENTAL_PAGES <= 0) else min(total_pages, INCREMENTAL_PAGES)

        if target_pages == 1:
            logger.info("✅ 元数据抓取完成（共 1 页）")
        else:
            time.sleep(PAGE_DELAY)

            for page in range(2, target_pages + 1):
                logger.info(f"\n⏳ {PAGE_DELAY}秒延迟后继续...")
                process_page(workshop, page)

                if page < target_pages:
                    time.sleep(PAGE_DELAY)

            logger.info(f"\n✅ 元数据抓取完成（已处理 {target_pages}/{total_pages} 页）")

        cycle_duration = (datetime.now() - cycle_start_time).total_seconds()
        logger.info(f"⏱️  元数据抓取耗时: {cycle_duration:.2f}秒")

    except Exception as e:
        logger.error(f"\n❌ 元数据抓取错误: {e}")
        raise


def run_mod_sync(mod_sync: ModSyncService) -> None:
    """执行一轮 mod 文件同步

    1. 为新抓取的 items 创建 pending 状态记录
    2. 获取 pending 的 items，逐个下载 mod → 打包 → 上传 R2 → 创建/更新 asset 记录
    """
    logger.info(f"\n{'=' * 60}")
    logger.info("📦 开始 mod 文件同步")
    logger.info(f"{'=' * 60}")

    try:
        # 1. 为新抓取的 items 创建 pending 状态
        new_items = get_items_without_sync_status(limit=100)
        if new_items:
            logger.info(f"为 {len(new_items)} 个新 item 创建同步状态记录")
            for item in new_items:
                upsert_sync_status(item.id, status="pending")
                time.sleep(0.05)  # 避免 DB 压力

        # 2. 获取 pending 的 items（按更新时间优先）
        pending_items = get_pending_sync_items(limit=MOD_SYNC_BATCH_SIZE)

        if not pending_items:
            logger.info("没有待同步的 mod 文件")
            return

        logger.info(f"找到 {len(pending_items)} 个待同步 mod")

        success_count = 0
        for idx, item in enumerate(pending_items, 1):
            logger.info(f"\n--- [{idx}/{len(pending_items)}] mod 同步: {item.id} - {item.title} ---")

            existing_asset_id = get_existing_asset_id(item.id)

            # 标记为 syncing
            upsert_sync_status(item.id, status="syncing")

            # 执行文件同步（下载 → 打包 → 上传 R2 → 图片同步）
            images_result = mod_sync.sync_mod(item)

            if not images_result:
                upsert_sync_status(item.id, status="failed", error_message="文件下载/打包/上传失败")
                continue

            # 创建/获取文件记录
            rwmod_key = f"steam/{item.id}/{item.id}.rwmod"
            file_id = create_file_record(
                object_key=rwmod_key,
                name=f"{item.id}.rwmod",
                mime_type="application/rwmod",
                size=item.file_size,
            )

            if not file_id:
                upsert_sync_status(item.id, status="failed", error_message="创建 file 记录失败")
                continue

            # 创建封面图 file 记录（仅当 R2 实际上传成功）
            cover_file_id = None
            if images_result.get("cover_key"):
                cover_key = images_result["cover_key"]
                ext = Path(cover_key).suffix or ".jpg"
                mime = "image/png" if ext == ".png" else "image/jpeg"
                cover_file_id = create_file_record(
                    object_key=cover_key,
                    name=f"cover{ext}",
                    mime_type=mime,
                )

            # 创建截图 file 记录（仅当 R2 实际上传成功）
            screenshot_file_ids = []
            for ss_key in images_result.get("screenshot_keys", []):
                ext = Path(ss_key).suffix or ".jpg"
                mime = "image/png" if ext == ".png" else "image/jpeg"
                ss_name = Path(ss_key).name
                ss_file_id = create_file_record(
                    object_key=ss_key,
                    name=ss_name,
                    mime_type=mime,
                )
                if ss_file_id:
                    screenshot_file_ids.append(ss_file_id)

            if existing_asset_id:
                # 已有 asset，执行更新操作
                updated = update_asset_record(
                    workshop_item=item,
                    asset_id=existing_asset_id,
                    file_id=file_id,
                    cover_file_id=cover_file_id,
                    screenshot_file_ids=screenshot_file_ids if screenshot_file_ids else None,
                )
                if updated:
                    update_sync_status_completed(item.id, existing_asset_id)
                    success_count += 1
                    logger.info(f"  ✅ mod {item.id} 增量更新完成 -> asset {existing_asset_id}")
                else:
                    upsert_sync_status(item.id, status="failed", error_message="更新 asset 记录失败")
            else:
                # 全新 asset，执行创建操作
                asset_id = create_asset_record(
                    workshop_item=item,
                    file_id=file_id,
                    cover_file_id=cover_file_id,
                    screenshot_file_ids=screenshot_file_ids if screenshot_file_ids else None,
                )

                if asset_id:
                    update_sync_status_completed(item.id, asset_id)
                    success_count += 1
                    logger.info(f"  ✅ mod {item.id} 同步完成 -> asset {asset_id}")
                else:
                    upsert_sync_status(item.id, status="failed", error_message="创建 asset 记录失败")

            # mod 之间延迟
            if idx < len(pending_items):
                time.sleep(mod_sync.request_delay)

        logger.info(f"\n✅ mod 文件同步完成: {success_count}/{len(pending_items)} 成功")

    except Exception as e:
        logger.error(f"\n❌ mod 文件同步错误: {e}")


def main():
    """主循环：持续监控 Workshop 更新"""
    # 启动时等待数据库就绪并初始化表
    if not wait_for_db():
        logger.error("程序退出：无法连接数据库")
        return

    workshop = None
    if os.getenv("STEAM_WORKSHOP_SYNC_API_KEY", "").strip():
        try:
            workshop = Wrokshop()
            logger.info("🔍 元数据同步已启用 (Steam Web API)")
        except Exception as e:
            logger.warning(f"⚠️ 元数据爬虫初始化失败: {e}")
    else:
        logger.info("🔍 元数据同步未启用（未配置 STEAM_WORKSHOP_SYNC_API_KEY，如需自动抓取新 mod 元数据请在 .env 中设置）")

    cycle_count = 0

    # Mod 同步服务（可选启用）
    mod_sync = None
    if MOD_SYNC_ENABLED:
        mod_sync = ModSyncService()
        logger.info("📦 Mod 文件同步已启用")
    else:
        logger.info("📦 Mod 文件同步未启用（设置 STEAM_WORKSHOP_SYNC_MOD_ENABLED=true 启用）")

    logger.info("=" * 60)
    logger.info("🚀 Steam Workshop 监控程序启动")
    logger.info(f"   页面延迟: {PAGE_DELAY}秒")
    logger.info(f"   循环延迟: {CYCLE_DELAY}秒")
    if mod_sync:
        logger.info(f"   Mod 同步批量: {MOD_SYNC_BATCH_SIZE}")
        logger.info(f"   Mod 同步间隔: {MOD_SYNC_DELAY}秒")
    logger.info("=" * 60)

    while True:
        cycle_count += 1

        logger.info(f"\n{'#' * 60}")
        logger.info(f"## 第 {cycle_count} 轮监控 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'#' * 60}")

        try:
            # 1. 元数据抓取（若已配置 API Key）
            # 每 10 轮或启动第 1 轮执行一次全量扫描，其余轮次快速增量扫描前 N 页
            if workshop:
                full_scan = (cycle_count == 1 or cycle_count % 10 == 0)
                run_metadata_sync(workshop, full_scan=full_scan)

            # 2. Mod 文件同步（如果启用）
            if mod_sync:
                run_mod_sync(mod_sync)

            # 等待进入下一轮
            wait_time = CYCLE_DELAY if not mod_sync else min(CYCLE_DELAY, MOD_SYNC_DELAY)
            logger.info(f"\n💤 等待 {wait_time}秒后开始下一轮...")
            time.sleep(wait_time)

        except KeyboardInterrupt:
            logger.info("\n\n⛔ 接收到中断信号，正在退出...")
            break
        except Exception as e:
            logger.error(f"\n❌ 监控过程发生错误: {e}")
            logger.info(f"💤 等待 {CYCLE_DELAY}秒后重试...")
            time.sleep(CYCLE_DELAY)

    logger.info("👋 监控程序已退出")


if __name__ == "__main__":
    main()
