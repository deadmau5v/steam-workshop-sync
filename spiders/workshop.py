import os
from datetime import datetime
from uuid import uuid4

import requests
from parsers.workshop import WorkshopItem, WorkshopItemInfo, WorkshopParser

from utils.log import get_logger

logger = get_logger(__name__)


class Wrokshop:
    def __init__(self) -> None:
        self.appid = os.environ.get("STEAM_WORKSHOP_SYNC_APP_ID")
        if not self.appid:
            raise EnvironmentError("没有设置APPID")

        self.headers = {
            "Host": "steamcommunity.com",
            "Connection": "keep-alive",
            "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
            "Referer": "https://steamcommunity.com/workshop/browse/",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    def get_new_items(self):
        start_time = datetime.now()

        parmes = {
            "appid": self.appid,
            "browsesort": "mostrecent",
            "section": "readytouseitems",
            "actualsort": "mostrecent",
            "p": "2",
        }

        url = "https://steamcommunity.com/workshop/browse/"

        response = requests.get(url, params=parmes, headers=self.headers)
        response.encoding = response.apparent_encoding
        response.raise_for_status()

        end_time = datetime.now()
        used_time_ms = int((end_time - start_time).total_seconds() * 1000)
        logger.info(f"爬取最新项目耗时: {used_time_ms}ms")

        with open(f"data/raw/{start_time}-{uuid4().hex}.html", "w") as f:
            f.write(response.text)

        return WorkshopParser.parser_items_card(response.text)

    def get_items_info(self, item: WorkshopItem):
        url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={item.id}"
        response = requests.get(url, headers=self.headers)
        response.encoding = response.apparent_encoding
        response.raise_for_status()

        with open(f"data/raw/{item.id}-{uuid4().hex}.html", "w") as f:
            f.write(response.text)

        description, created_at, updated_at = WorkshopParser.parser_items_info(
            response.text
        )
        return WorkshopItemInfo(
            **item.model_dump(),
            description=description,
            created_at=created_at,
            updated_at=updated_at,
        )
