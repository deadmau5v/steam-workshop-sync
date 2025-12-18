import os
import time
from datetime import datetime
from dotenv import load_dotenv

from models.workshop import Pagination, WorkshopItem
from spiders.workshop import Wrokshop
from utils.log import get_logger
from database import save_workshop_item

load_dotenv()

logger = get_logger(__name__)

# 配置参数
PAGE_DELAY = float(os.getenv("STEAM_WORKSHOP_SYNC_PAGE_DELAY", 5.0))  # 页面间延迟（秒）
CYCLE_DELAY = float(os.getenv("STEAM_WORKSHOP_SYNC_CYCLE_DELAY", 60.0))  # 循环间延迟（秒）


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
        
        logger.info(
            f"📄 第 {pagination.current_page}/{pagination.total_pages} 页 "
            f"- 找到 {pagination.items_count} 个项目"
        )
        
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


def main():
    """主循环：持续监控 Workshop 更新"""
    workshop = Wrokshop()
    cycle_count = 0
    
    logger.info("=" * 60)
    logger.info("🚀 Steam Workshop 监控程序启动")
    logger.info(f"   页面延迟: {PAGE_DELAY}秒")
    logger.info(f"   循环延迟: {CYCLE_DELAY}秒")
    logger.info("=" * 60)
    
    while True:
        cycle_count += 1
        cycle_start_time = datetime.now()
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 开始第 {cycle_count} 轮监控 - {cycle_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*60}")
        
        try:
            # 首先获取第一页以确定总页数
            total_pages, _ = process_page(workshop, 1)
            
            # 如果只有一页，直接进入下一轮
            if total_pages == 1:
                logger.info(f"✅ 本轮监控完成（共 1 页）")
            else:
                # 处理剩余页面
                time.sleep(PAGE_DELAY)
                
                for page in range(2, total_pages + 1):
                    logger.info(f"\n⏳ {PAGE_DELAY}秒延迟后继续...")
                    process_page(workshop, page)
                    
                    # 如果不是最后一页，添加延迟
                    if page < total_pages:
                        time.sleep(PAGE_DELAY)
                
                logger.info(f"\n✅ 本轮监控完成（共 {total_pages} 页）")
            
            # 计算本轮耗时
            cycle_end_time = datetime.now()
            cycle_duration = (cycle_end_time - cycle_start_time).total_seconds()
            logger.info(f"⏱️  本轮耗时: {cycle_duration:.2f}秒")
            
            # 等待进入下一轮
            logger.info(f"\n💤 等待 {CYCLE_DELAY}秒后开始下一轮...")
            time.sleep(CYCLE_DELAY)
            
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