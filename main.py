from dotenv import load_dotenv

from models.workshop import Pagination, WorkshopItem
from spiders.workshop import Wrokshop
from utils.log import get_logger
from database import save_workshop_item

load_dotenv()

workshohp = Wrokshop()
logger = get_logger(__name__)
result = workshohp.get_new_items()

pagination: Pagination = result["pagination"]
items: list[WorkshopItem] = result["items"]

for idx, item in enumerate[WorkshopItem](items, 1):
    logger.info(f"[{idx}/{pagination.items_count}] 处理中...")

    item_info = workshohp.get_items_info(item)
    save_workshop_item(item_info, exist_ok=True)