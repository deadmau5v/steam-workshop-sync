import argparse
from dataclasses import asdict
from datetime import datetime
import json
import os
import re
import time
from uuid import UUID

from database import (
    claim_source,
    commit_source,
    expire_final_source_claims,
    fail_source,
    get_existing_asset_id,
    get_pending_sync_items,
    get_recovery_asset,
    get_workshop_item,
    init_db,
    list_legacy_candidates,
    read_committed_source,
    save_workshop_item,
    seed_source_queue,
)
from dotenv import load_dotenv
from models.workshop import Pagination, WorkshopItem
from services.mod_sync import ModSyncService
from services.r2_service import create_asset_r2_service
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


def _process_claim(mod_sync, item, claim, *, with_images=False):
    try:
        source = mod_sync.sync_mod(item, upload=True)
        if not source:
            fail_source(item, claim, 'download, validation, or object verification failed')
            return None
        images = None
        if with_images and claim.asset_id is None and get_existing_asset_id(item.id) is None:
            images = mod_sync.sync_images(item)
        return commit_source(item, source, claim, images=images), source
    except Exception as exc:
        # Some exceptions (credentials, command lines, HTTP headers) are sensitive.
        fail_source(item, claim, f'source sync failed ({type(exc).__name__})')
        logger.error(f'Workshop {item.id}: source sync failed ({type(exc).__name__})')
        return None


def run_mod_sync(mod_sync: ModSyncService) -> None:
    expire_final_source_claims()
    seed_source_queue()
    pending = get_pending_sync_items(limit=MOD_SYNC_BATCH_SIZE)
    for index, item in enumerate(pending):
        try:
            claim = claim_source(item)
            if claim:
                result = _process_claim(mod_sync, item, claim, with_images=True)
                if result:
                    asset_id, source = result
                    logger.info(f'Workshop {item.id}: published source {source.sha256} -> {asset_id}')
        except Exception as exc:
            logger.error(f'Workshop {item.id}: could not process claim ({type(exc).__name__})')
        if index < len(pending) - 1:
            time.sleep(mod_sync.request_delay)


def run_one_source(mod_sync, item_id: str, asset_id: str, *, apply: bool) -> int:
    if not re.fullmatch(r'[0-9]{1,20}', item_id) or str(UUID(asset_id)) != asset_id:
        raise ValueError('expected a numeric Workshop ID and canonical asset UUID')
    item = get_workshop_item(item_id)
    if item is None:
        raise RuntimeError('Workshop item not found')
    before = get_recovery_asset(item_id, asset_id)
    if not apply:
        source = mod_sync.sync_mod(item, upload=False)
        if source is None:
            return 1
        print(json.dumps({'item_id': item_id, 'asset_id': asset_id, 'default_file_id': before,
                          'published': False, **asdict(source)}))
        return 0
    claim = claim_source(item, expected_asset_id=asset_id)
    if claim is None:
        raise RuntimeError('another source claim is active')
    result = _process_claim(mod_sync, item, claim)
    if result is None:
        return 1
    _, source = result
    committed = read_committed_source(item_id, asset_id, source)
    if before != committed['default_file_id']:
        logger.warning(f'Workshop {item_id}: default changed externally during canary; inspect before continuing')
        return 1
    print(json.dumps({'item_id': item_id, 'asset_id': asset_id, 'published': True,
                      **asdict(source), **committed}))
    return 0


def cli() -> int:
    parser = argparse.ArgumentParser(description='Steam Workshop sync')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--recover-source', metavar='WORKSHOP_ID', help='validate one existing source; no writes without --apply')
    mode.add_argument('--legacy-candidates', type=int, metavar='LIMIT', help='read-only review list for legacy failures/empty hints')
    parser.add_argument('--asset-id', help='required exact asset UUID for --recover-source')
    parser.add_argument('--after', default='', help='last Workshop ID from a previous candidate page')
    parser.add_argument('--check-empty', action='store_true', help='check each legacy candidate object for the 22-byte ZIP')
    parser.add_argument('--apply', action='store_true', help='publish the one verified source; keep the daemon stopped')
    args = parser.parse_args()
    if args.recover_source is not None:
        if not args.asset_id or args.after or args.check_empty:
            parser.error('--recover-source requires --asset-id and does not accept candidate filters')
        try:
            return run_one_source(ModSyncService(), args.recover_source, args.asset_id, apply=args.apply)
        except (ValueError, RuntimeError) as exc:
            logger.error(str(exc))
            return 1
        except Exception as exc:
            logger.error(f'exact recovery failed ({type(exc).__name__})')
            return 1
    if args.apply or args.asset_id or ((args.after or args.check_empty) and args.legacy_candidates is None):
        parser.error('--apply/--asset-id require --recover-source; candidate filters require --legacy-candidates')
    if args.legacy_candidates is not None:
        if not 1 <= args.legacy_candidates <= 100 or (args.after and not re.fullmatch(r'[0-9]{1,20}', args.after)):
            parser.error('candidate limit must be 1–100 and --after must be a numeric Workshop ID')
        storage = create_asset_r2_service() if args.check_empty else None
        failed = False
        for candidate in list_legacy_candidates(args.legacy_candidates, args.after):
            if storage is not None:
                try:
                    candidate['is_empty_legacy_zip'] = storage.is_empty_legacy_zip(candidate['legacy_key'])
                except Exception as exc:
                    candidate['is_empty_legacy_zip'] = None
                    logger.warning(f"Workshop {candidate['item_id']}: object check failed ({type(exc).__name__})")
                    failed = True
            print(json.dumps(candidate))
        return int(failed)
    main()
    return 0


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
    raise SystemExit(cli())
