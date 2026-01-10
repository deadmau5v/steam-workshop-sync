import os
import time
import subprocess
from datetime import datetime
from pathlib import Path

import requests

from models.workshop import WorkshopItem
from parsers.workshop import WorkshopParser
from utils.log import get_logger
from utils.retry import retry_on_error

logger = get_logger(__name__)


class Wrokshop:
    def __init__(self) -> None:
        self.appid = os.environ.get("STEAM_WORKSHOP_SYNC_APP_ID", "").strip()
        if not self.appid:
            raise EnvironmentError(
                "没有设置 STEAM_WORKSHOP_SYNC_APP_ID（Steam Workshop APP ID）"
            )

        self.timeout = int(os.environ.get("STEAM_WORKSHOP_SYNC_TIMEOUT", 30))
        # 请求之间的基础延迟（秒）
        self.request_delay = float(
            os.environ.get("STEAM_WORKSHOP_SYNC_REQUEST_DELAY", 1.0)
        )

        # Steam CMD 配置
        self.steamcmd_path = os.environ.get("STEAM_WORKSHOP_SYNC_STEAMCMD_PATH", "steamcmd")
        self.download_dir = os.environ.get("STEAM_WORKSHOP_SYNC_DOWNLOAD_DIR", "./downloads")
        self.steam_username = os.environ.get("STEAM_WORKSHOP_SYNC_STEAM_USERNAME", "anonymous")
        self.steam_password = os.environ.get("STEAM_WORKSHOP_SYNC_STEAM_PASSWORD", "")
        self.steam_guard_code = os.environ.get("STEAM_WORKSHOP_SYNC_STEAM_GUARD_CODE", "")

        # 确保下载目录存在
        Path(self.download_dir).mkdir(parents=True, exist_ok=True)

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
            "Referer": "https://steamcommunity.com/workshop/browse/",
        }

        self.session = requests.Session()

    @retry_on_error(
        retry_on_status={
            429: None,  # 429 无限重试
            500: 3,  # 服务器错误重试3次
            502: 3,
            503: 3,
            504: 3,
        },
        backoff_base=5.0,
        backoff_max=300.0,
        default_retry=False,
    )
    def _do_request(self, url: str, **kwargs) -> requests.Response:
        """执行HTTP请求（带重试机制）"""
        response = self.session.get(url, **kwargs)
        response.raise_for_status()
        return response

    def get_new_items(self, page: int = 1):
        start_time = datetime.now()

        params = {
            "appid": self.appid,
            "browsesort": "mostrecent",
            "section": "readytouseitems",
            "actualsort": "mostrecent",
            "p": str(page),
        }

        url = "https://steamcommunity.com/workshop/browse/"

        logger.info(f"正在请求第 {page} 页: {url}")
        response = self._do_request(
            url, params=params, headers=self.headers, timeout=self.timeout
        )
        response.encoding = response.apparent_encoding

        end_time = datetime.now()
        used_time_ms = int((end_time - start_time).total_seconds() * 1000)
        logger.info(f"爬取第 {page} 页耗时: {used_time_ms}ms")

        return WorkshopParser.parser_items_card(response.text)

    def get_items_info(self, item: WorkshopItem):
        url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={item.id}"

        # 在每个请求之间添加延迟，避免请求过快
        time.sleep(self.request_delay)

        response = self._do_request(url, headers=self.headers, timeout=self.timeout)
        response.encoding = response.apparent_encoding

        description, created_at, updated_at, file_size, images = (
            WorkshopParser.parser_items_info(response.text)
        )
        item_data = item.model_dump()
        item_data.update(
            {
                "description": description,
                "created_at": created_at,
                "updated_at": updated_at,
                "file_size": file_size,
                "images": images,
            }
        )
        return WorkshopItem.model_validate(item_data)

    def download_mod(self, item_id: str) -> bool:
        """
        使用 Steam CMD 下载 Workshop mod

        Args:
            item_id: Workshop item ID

        Returns:
            bool: 下载是否成功
        """
        item_id = item_id.strip()
        logger.info(f"开始下载 mod: {item_id}")

        # Steam CMD 临时下载目录（在 steamcmd 目录下）
        steamcmd_temp_dir = os.path.join(os.path.dirname(self.steamcmd_path), "downloads")
        Path(steamcmd_temp_dir).mkdir(parents=True, exist_ok=True)

        # 构建 Steam CMD 命令
        cmd = [
            self.steamcmd_path,
            "+force_install_dir", steamcmd_temp_dir,
            "+login", self.steam_username,
        ]

        # 如果有密码，添加密码
        if self.steam_password:
            cmd.append(self.steam_password)
            # 如果有 Steam Guard 代码，添加代码
            if self.steam_guard_code:
                cmd.append(self.steam_guard_code)

        # 添加下载命令
        cmd.extend([
            "+workshop_download_item", self.appid, item_id,
            "validate",
            "+quit"
        ])

        try:
            logger.info(f"执行 Steam CMD 命令: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,  # 1小时超时
            )

            if result.returncode == 0:
                logger.info(f"mod {item_id} 下载成功")
                # 检查输出中是否包含成功标记
                if "Success." in result.stdout or "success" in result.stdout.lower():
                    # 移动文件到目标目录
                    source_dir = os.path.join(steamcmd_temp_dir, "steamapps", "workshop", "content", self.appid, item_id)
                    target_dir = os.path.join(self.download_dir, item_id)

                    if os.path.exists(source_dir):
                        # 如果目标目录已存在，先删除
                        if os.path.exists(target_dir):
                            import shutil
                            shutil.rmtree(target_dir)
                        # 移动目录
                        import shutil
                        shutil.move(source_dir, target_dir)
                        logger.info(f"mod {item_id} 已移动到: {target_dir}")
                    else:
                        logger.warning(f"未找到下载的 mod 文件: {source_dir}")
                        return False
                    return True
                else:
                    logger.warning(f"mod {item_id} 可能下载失败，返回码为 0 但未找到成功标记")
                    logger.debug(f"Steam CMD 输出: {result.stdout}")
                    return False
            else:
                logger.error(f"mod {item_id} 下载失败，返回码: {result.returncode}")
                logger.error(f"错误输出: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"mod {item_id} 下载超时")
            return False
        except FileNotFoundError:
            logger.error(f"未找到 Steam CMD，请检查路径: {self.steamcmd_path}")
            return False
        except Exception as e:
            logger.error(f"mod {item_id} 下载时发生异常: {e}")
            return False

    def download_mods(self, item_ids: list[str]) -> dict[str, bool]:
        """
        批量下载 Workshop mods

        Args:
            item_ids: Workshop item IDs 列表

        Returns:
            dict: {item_id: success} 的字典
        """
        results = {}
        total = len(item_ids)

        for index, item_id in enumerate(item_ids, 1):
            logger.info(f"正在下载 {index}/{total}: {item_id}")
            success = self.download_mod(item_id)
            results[item_id] = success

            # 下载之间添加延迟，避免请求过快
            if index < total:
                time.sleep(self.request_delay)

        success_count = sum(1 for success in results.values() if success)
        logger.info(f"下载完成: {success_count}/{total} 成功")

        return results
