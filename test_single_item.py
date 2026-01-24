#!/usr/bin/env python3
"""
测试单个 Workshop 项目的解析和入库
使用现有模块进行测试，类似于单元测试
"""

from database import save_workshop_item
from models.workshop import WorkshopItem
from spiders.workshop import Wrokshop
from utils.log import get_logger

# 创建 logger
logger = get_logger(__name__)


def test_single_item(item_id: str):
    """测试单个项目的完整流程"""
    logger.info(f"开始测试项目 ID: {item_id}")

    try:
        # 使用 Wrokshop 爬虫类
        workshop = Wrokshop()
    except Exception as e:
        logger.error(f"初始化 Wrokshop 失败: {e}")
        return None

    # 1. 获取项目详细信息
    logger.info("正在获取项目详细信息...")
    try:
        # 创建一个基本的 WorkshopItem 对象
        url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={item_id}"
        base_item = WorkshopItem(
            id=item_id,
            url=url,
            title="",
            coverview_url="",
            author="",
            author_profile="",
            images=[],
        )

        # 使用 Wrokshop.get_items_info 获取详细信息
        item = workshop.get_items_info(base_item)
        logger.info("成功获取项目详细信息:")
        logger.info(f"  标题: {item.title}")
        logger.info(f"  作者: {item.author}")
        logger.info(f"  封面 URL: {item.coverview_url}")
        logger.info(f"  描述长度: {len(item.description) if item.description else 0} 字符")
        logger.info(f"  创建时间: {item.created_at}")
        logger.info(f"  更新时间: {item.updated_at}")
        logger.info(f"  文件大小: {item.file_size}")
        logger.info(f"  图片数量: {len(item.images) if item.images else 0}")
        logger.info(f"  Meta Data: {item.meta_data}")

    except Exception as e:
        logger.error(f"获取项目 {item_id} 失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return None

    # 2. 测试入库
    logger.info("\n--- 测试数据入库 ---")
    try:
        result = save_workshop_item(item, exist_ok=True)
        if result:
            logger.info("✓ 项目保存成功")
            logger.info(f"  数据库 ID: {result.id}")
            logger.info(f"  创建时间: {result.created_at}")
            logger.info(f"  更新时间: {result.updated_at}")
            logger.info(f"  同步时间: {result.synced_at}")
            return result
        else:
            logger.error("✗ 项目保存失败: 返回 None")
            return None
    except Exception as e:
        logger.error(f"✗ 项目保存失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return None


def main():
    """主函数"""
    # 测试失败的项目
    test_item_id = "3446121060"

    logger.info("=" * 60)
    logger.info(f"开始测试 Workshop 项目: {test_item_id}")
    logger.info("=" * 60)

    result = test_single_item(test_item_id)

    logger.info("\n" + "=" * 60)
    if result:
        logger.info("✓ 测试通过")
    else:
        logger.info("✗ 测试失败")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
