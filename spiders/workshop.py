import os
import time
from datetime import datetime

import requests
from models.workshop import WorkshopItem
from parsers.workshop import WorkshopParser

from utils.log import get_logger
from utils.retry import retry_on_error

logger = get_logger(__name__)


class Wrokshop:
    def __init__(self) -> None:
        self.appid = os.environ.get("STEAM_WORKSHOP_SYNC_APP_ID")
        if not self.appid:
            raise EnvironmentError("没有设置APPID")

        self.timeout = int(os.environ.get("STEAM_WORKSHOP_SYNC_TIMEOUT", 30))
        # 请求之间的基础延迟（秒）
        self.request_delay = float(os.environ.get("STEAM_WORKSHOP_SYNC_REQUEST_DELAY", 1.0))

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
            "Referer": "https://steamcommunity.com/workshop/browse/",
        }

        self.session = requests.Session()

    @retry_on_error(
        retry_on_status={
            429: None,  # 429 无限重试
            500: 3,     # 服务器错误重试3次
            502: 3,
            503: 3,
            504: 3,
        },
        backoff_base=5.0,
        backoff_max=300.0,
        default_retry=False
    )
    def _do_request(self, url: str, **kwargs) -> requests.Response:
        """执行HTTP请求（带重试机制）"""
        response = self.session.get(url, **kwargs)
        response.raise_for_status()
        return response

    def get_new_items(self):
        start_time = datetime.now()

        params = {
            "appid": self.appid,
            "browsesort": "mostrecent",
            "section": "readytouseitems",
            "actualsort": "mostrecent",
            "p": "2",
        }

        url = "https://steamcommunity.com/workshop/browse/"

        logger.info(f"正在请求: {url}")
        response = self._do_request(url, params=params, headers=self.headers, timeout=self.timeout)
        response.encoding = response.apparent_encoding

        end_time = datetime.now()
        used_time_ms = int((end_time - start_time).total_seconds() * 1000)
        logger.info(f"爬取最新项目耗时: {used_time_ms}ms")

        return WorkshopParser.parser_items_card(response.text)

    def get_items_info(self, item: WorkshopItem):
        url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={item.id}"
        
        # 在每个请求之间添加延迟，避免请求过快
        time.sleep(self.request_delay)
        
        response = self._do_request(url, headers=self.headers, timeout=self.timeout)
        response.encoding = response.apparent_encoding

        description, created_at, updated_at = WorkshopParser.parser_items_info(
            response.text
        )
        item_data = item.model_dump()
        item_data.update({
            "description": description,
            "created_at": created_at,
            "updated_at": updated_at,
        })
        return WorkshopItem.model_validate(item_data)
