from parsers.workshop import WorkshopItem
from spiders.workshop import Wrokshop
from dotenv import load_dotenv
from pprint import pprint

load_dotenv()

workshohp = Wrokshop()
items: WorkshopItem = workshohp.get_new_items()["items"]

for item in items:
    pprint(workshohp.get_items_info(item))
