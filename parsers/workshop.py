import re

from bs4 import BeautifulSoup
import html2text
from models.workshop import Pagination, WorkshopItem
from utils.formater import date_formater, file_size_formater, image_url_formater
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
        description = h.handle(soup.find(attrs={"class": "workshopItemDescription"}).prettify()).strip()  # type: ignore

        responsive_local_menu = soup.find(attrs={"class": "workshopItemPreviewArea"}).find(  # type: ignore
            attrs={"class": "responsive_local_menu"}
        )

        details_stats_keys = responsive_local_menu.find_all(attrs={"class": "detailsStatLeft"})  # type: ignore
        details_stats_values = responsive_local_menu.find_all(attrs={"class": "detailsStatRight"})  # type: ignore

        details_stats_keys = [key.text.strip() for key in details_stats_keys]
        details_stats_values = [value.text.strip() for value in details_stats_values]
        details_stats = dict(zip(details_stats_keys, details_stats_values, strict=False))

        logger.debug(f"MetaData: {details_stats}")

        created_at = date_formater(details_stats.get("Posted") or details_stats.get("发表于"))
        updated_at = date_formater(details_stats.get("Updated") or details_stats.get("更新于"))
        file_size = file_size_formater(details_stats.get("File Size") or details_stats.get("文件大小"))

        images_tag = soup.find(attrs={"class": "workshopItemPreviewImageEnlargeableContainer"}).find_all("img")  # type: ignore
        images = [image_url_formater(img["src"]) for img in images_tag if image_url_formater(img["src"])]  # type: ignore

        highlight_strip_bg = soup.find(attrs={"id": "highlight_strip_bg"})
        if highlight_strip_bg:
            for image in highlight_strip_bg.find_all("img"):
                image = image_url_formater(image["src"])  # type: ignore
                if image:
                    images.append(image)

        images = list(set(images))
        return description, created_at, updated_at, file_size, images
