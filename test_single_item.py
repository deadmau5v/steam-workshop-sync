#!/usr/bin/env python3
"""
测试单个 Workshop 项目的解析和入库
"""


from database import save_workshop_item
from models.workshop import WorkshopItem
from parsers.workshop import WorkshopParser
import requests
from utils.log import get_logger

# 创建 logger
logger = get_logger(__name__)


def test_single_item(item_id: str):
    """测试单个项目的完整流程"""
    logger.info(f"开始测试项目 ID: {item_id}")

    # 1. 直接获取项目 HTML
    url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={item_id}"
    logger.info(f"正在获取项目信息: {url}")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.encoding = response.apparent_encoding
        html = response.text
    except Exception as e:
        logger.error(f"无法获取项目 {item_id} 的 HTML: {e}")
        return None

    logger.info(f"成功获取 HTML，长度: {len(html)} 字符")

    # 2. 解析项目信息
    logger.info("正在解析项目信息...")
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")

        # 提取标题
        title_tag = soup.find(attrs={"class": "workshopItemTitle"})
        title = title_tag.text.strip() if title_tag else "Unknown"

        # 提取封面图
        preview_tag = soup.find(attrs={"id": "previewImage"}) or soup.find(attrs={"class": "workshopItemPreviewImageMain"})
        coverview_url = preview_tag["src"] if preview_tag and preview_tag.get("src") else ""

        # 提取作者信息
        # 尝试多种方式查找作者信息
        author = "Unknown"
        author_profile = ""

        # 方法1: friendBlockContent
        author_tag = soup.find(attrs={"class": "friendBlockContent"})
        if author_tag:
            author_link_tag = author_tag.find("a")
            if author_link_tag:
                author = author_link_tag.text.strip()
                author_profile = author_link_tag["href"]

        # 方法2: 如果方法1失败，尝试查找 creatorsBlock
        if author == "Unknown":
            creators_block = soup.find(attrs={"class": "creatorsBlock"})
            if creators_block:
                author_link = creators_block.find("a", attrs={"class": "friendBlockLinkOverlay"})
                if author_link:
                    author_profile = author_link["href"]
                    # 从friendBlockContent获取名称
                    author_name_div = creators_block.find(attrs={"class": "friendBlockContent"})
                    if author_name_div:
                        # 获取第一行文本（作者名）
                        lines = [line.strip() for line in author_name_div.stripped_strings]
                        if lines:
                            author = lines[0]

        # 解析详细信息
        description, created_at, updated_at, file_size, images = WorkshopParser.parser_items_info(html)
    except Exception as e:
        logger.error(f"解析项目 {item_id} 失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return None

    logger.info("成功解析项目信息:")
    logger.info(f"  标题: {title}")
    logger.info(f"  作者: {author}")
    logger.info(f"  封面 URL: {coverview_url}")
    logger.info(f"  描述长度: {len(description) if description else 0} 字符")
    logger.info(f"  创建时间: {created_at}")
    logger.info(f"  更新时间: {updated_at}")
    logger.info(f"  文件大小: {file_size}")
    logger.info(f"  图片数量: {len(images) if images else 0}")

    # 3. 构建完整的项目数据
    logger.info("\n--- 构建项目数据 ---")
    item = WorkshopItem(
        id=item_id,
        url=url,
        title=title,
        coverview_url=coverview_url,
        author=author,
        author_profile=author_profile,
        description=description,
        created_at=created_at,
        updated_at=updated_at,
        file_size=file_size,
        images=images or [],
    )

    logger.info("完整项目数据:")
    logger.info(f"  id: {item.id}")
    logger.info(f"  url: {item.url}")
    logger.info(f"  title: {item.title}")
    logger.info(f"  description: {len(item.description) if item.description else 0} 字符")
    logger.info(f"  created_at: {item.created_at}")
    logger.info(f"  updated_at: {item.updated_at}")
    logger.info(f"  file_size: {item.file_size}")

    # 4. 测试入库
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
    test_item_id = "3226535413"

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
