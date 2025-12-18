from bs4 import BeautifulSoup
import html2text
import re

from models.workshop import WorkshopItem, Pagination
from utils.formater import date_formater
from utils.log import get_logger

logger = get_logger(__name__)


class WorkshopParser:
    @staticmethod
    def parser_items_card(html):
        """
        解析创意工坊项目卡片
        """
        soup = BeautifulSoup(html, "lxml").find(attrs={"class": "workshopBrowseItems"})
        pagination_html = BeautifulSoup(html, "lxml").find(
            attrs={"class": "workshopBrowsePaging"}
        )

        items_tag = soup.find_all(attrs={"class": "workshopItem"})
        pagination = WorkshopParser.parser_pagination(pagination_html)
        pagination.items_count = len(items_tag)

        items = []
        for item_tag in items_tag:

            # 基础
            item_id = item_tag.find(attrs={"class": "ugc"})["data-publishedfileid"]
            item_url = item_tag.find(attrs={"class": "ugc"})["href"]
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
            match = re.search(r"(?:(\d+)-star|not-yet)\.png", rating_img)
            rating = None

            if match and match.group(1):
                rating = int(match.group(1))

            item = WorkshopItem(
                id=item_id,
                url=item_url,
                title=item_title,
                coverview_url=coverview_url,
                author=author_name,
                author_profile=author_profile,
                rating=rating,
            )
            items.append(item)

        return {"pagination": pagination, "items": items}

    @staticmethod
    def parser_pagination(paging_soup) -> Pagination:
        controls = paging_soup.find(attrs={"class": "workshopBrowsePagingControls"})
        page_links = [
            a.get_text(strip=True)
            for a in controls.find_all(attrs={"class": "pagelink"})
        ]
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
        description = h.handle(
            soup.find(attrs={"class": "workshopItemDescription"}).prettify()
        ).strip()
        details_stats_container = soup.find(
            attrs={"class": "rightDetailsBlock"}
        )

        details_stats_keys = details_stats_container.find_all(
            attrs={"class": "detailsStatLeft"}
        )
        details_stats_values = details_stats_container.find_all(
            attrs={"class": "detailsStatRight"}
        )

        details_stats_keys = [key.text.strip() for key in details_stats_keys]
        details_stats_values = [value.text.strip() for value in details_stats_values]
        details_stats = dict(zip(details_stats_keys, details_stats_values))

        created_at = date_formater(details_stats.get("Posted", None))
        updated_at = date_formater(details_stats.get("Updated", None))
        file_size: str | None = details_stats.get("File Size", None)

        return description, created_at, updated_at, file_size
