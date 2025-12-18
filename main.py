from models.workshop import WorkshopItem
from parsers.workshop import WorkshopItem
from spiders.workshop import Wrokshop
from dotenv import load_dotenv
from utils.log import get_logger

load_dotenv()

workshohp = Wrokshop()
logger = get_logger(__name__)
result = workshohp.get_new_items()
items: list[WorkshopItem] = result["items"]

for idx, item in enumerate[WorkshopItem](items, 1):
    logger.info(f"[{idx}/{len(items)}] 处理中...")

    item_info = workshohp.get_items_info(item)
    logger.info("-" * 80)
