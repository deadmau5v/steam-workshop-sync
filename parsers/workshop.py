import re

from bs4 import BeautifulSoup
import html2text
from models.workshop import Pagination, WorkshopItem
from utils.formater import date_formater, file_size_formater, format_number, image_url_formater
from utils.log import get_logger

logger = get_logger(__name__)


class WorkshopParser:
    @staticmethod
    def parser_items_card(html):
        """
        解析创意工坊项目卡片
        """
        soup = BeautifulSoup(html, "lxml").find(attrs={"class": "workshopBrowseItems"})
        pagination_html = BeautifulSoup(html, "lxml").find(attrs={"class": "workshopBrowsePaging"})

        items_tag = soup.find_all(attrs={"class": "workshopItem"})  # type: ignore
        pagination = WorkshopParser.parser_pagination(pagination_html)
        pagination.items_count = len(items_tag)

        items = []
        for item_tag in items_tag:
            # 基础
            item_id = item_tag.find(attrs={"class": "ugc"})["data-publishedfileid"]  # type: ignore
            item_url = item_tag.find(attrs={"class": "ugc"})["href"]  # type: ignore
            title_tag = item_tag.find(attrs={"class": "workshopItemTitle"})
            item_title = title_tag.text.strip() if title_tag else ""

            # 图片
            img_tag = item_tag.find(attrs={"class": "workshopItemPreviewImage"})
            coverview_url = img_tag["src"] if img_tag else ""

            # 作者信息
            author_tag = item_tag.find(attrs={"class": "workshop_author_link"})
            author_name = author_tag.text.strip() if author_tag else ""
            author_profile = author_tag["href"] if author_tag else ""

            # 评分
            rating_img_tag = item_tag.find(attrs={"class": "fileRating"})
            rating_img = rating_img_tag["src"] if rating_img_tag else None
            match = re.search(r"(?:(\d+)-star|not-yet)\.png", rating_img)  # type: ignore
            rating = None

            if match and match.group(1):
                rating = int(match.group(1))

            item = WorkshopItem(
                id=item_id,  # type: ignore
                url=item_url,  # type: ignore
                title=item_title,
                coverview_url=coverview_url,  # type: ignore
                author=author_name,
                author_profile=author_profile,  # type: ignore
                rating=rating,
                images=[],
            )
            items.append(item)

        return {"pagination": pagination, "items": items}

    @staticmethod
    def parser_pagination(paging_soup) -> Pagination:
        controls = paging_soup.find(attrs={"class": "workshopBrowsePagingControls"})
        page_links = [a.get_text(strip=True) for a in controls.find_all(attrs={"class": "pagelink"})]
        current_page = int(page_links[0])

        total_pages = int(page_links[-1])
        pagination = Pagination(
            current_page=current_page if current_page else 1,
            total_pages=total_pages,
        )
        return pagination

    @staticmethod
    def parser_items_info(html):
        soup = BeautifulSoup(html, "lxml")
        h = html2text.HTML2Text()

        # 1. 提取描述
        desc_tag = soup.find(attrs={"class": "workshopItemDescription"})
        description = h.handle(desc_tag.prettify()).strip() if desc_tag else ""

        # 2. 提取统计数据 (大小、发布日期等)
        preview_area = soup.find(attrs={"class": "workshopItemPreviewArea"})
        right_col = preview_area.find_next(attrs={"class": "col_right"}) if preview_area else None

        details_stats = {}
        if right_col:
            keys = [k.text.strip() for k in right_col.find_all(attrs={"class": "detailsStatLeft"})]
            values = [v.text.strip() for v in right_col.find_all(attrs={"class": "detailsStatRight"})]
            details_stats = dict(zip(keys, values, strict=False))

        created_at = date_formater(details_stats.get("Posted") or details_stats.get("发表于"))
        updated_at = date_formater(details_stats.get("Updated") or details_stats.get("更新日期"))
        file_size = file_size_formater(details_stats.get("File Size") or details_stats.get("文件大小"))

        # 3. 提取图片列表
        images = []

        # 主预览图（截图列表）
        enlargeable_container = soup.find(attrs={"class": "workshopItemPreviewImageEnlargeableContainer"})
        if enlargeable_container:
            images_tag = enlargeable_container.find_all("img")
            for img in images_tag:
                if img.get("src"):
                    url = image_url_formater(img["src"])  # type: ignore
                    if url:
                        images.append(url)

        # 底部滚动条缩略图
        strip_bg = soup.find(attrs={"id": "highlight_strip_bg"})
        if strip_bg:
            for img in strip_bg.find_all("img"):
                url = image_url_formater(img["src"])  # type: ignore
                if url:
                    images.append(url)

        # 去重但保持顺序
        images = list(dict.fromkeys(images))

        # 5. 提取作者资料链接和名称
        author_profile = ""
        author_name = ""
        author_link = soup.find(attrs={"class": "friendBlockLink"})
        if author_link and author_link.get("href"):
            author_profile = author_link["href"]  # type: ignore

        author_block = soup.find(attrs={"class": "friendBlockContent"})
        if author_block and author_block.contents:
            author_name = author_block.contents[0].strip()  # type: ignore

        # 6. 提取标题
        title_elem = soup.find(attrs={"class": "workshopItemTitle"})
        title = title_elem.text.strip() if title_elem else ""

        # 7. 提取统计数据（只保存在 meta_data 中）
        meta_data: dict[str, int] = {}

        # 提取评分数量
        num_ratings_elem = soup.find(attrs={"class": "numRatings"})
        if num_ratings_elem:
            num_ratings_text = num_ratings_elem.text.strip()
            meta_data["num_ratings"] = format_number(num_ratings_text)

        # 提取右侧面板的访客/订阅数据
        stats_table = soup.find(attrs={"class": "stats_table"})
        if stats_table:
            rows = stats_table.find_all("tr")
            for row in rows:
                tds = row.find_all("td")
                if len(tds) == 2:
                    label = tds[1].text.strip()
                    value_text = tds[0].text.strip()
                    # 转换为整数
                    value = format_number(value_text)
                    meta_data[label] = value

        return (
            description,
            created_at,
            updated_at,
            file_size,
            images,
            meta_data,
            author_profile,
            title,
            author_name,
        )
