"""Steam Workshop 爬虫 - 使用 Steam Web API (api.steampowered.com)

替代原来的 HTML 爬取方案（steamcommunity.com 在国内被墙），
改用官方 Steam Web API，返回 JSON，更稳定且国内可直连。
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import time

from models.workshop import WorkshopItem
import requests
from utils.log import get_logger
from utils.retry import retry_on_error

logger = get_logger(__name__)


class Wrokshop:
    """Steam Workshop 爬虫 - 基于 Steam Web API"""

    QUERY_FILES_URL = "https://api.steampowered.com/IPublishedFileService/QueryFiles/v1"
    PLAYER_SUMMARIES_URL = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2"
    DEFAULT_PAGE_SIZE = 50

    def __init__(self) -> None:
        self.appid = os.environ.get("STEAM_WORKSHOP_SYNC_APP_ID", "").strip()
        if not self.appid:
            raise OSError("没有设置 STEAM_WORKSHOP_SYNC_APP_ID（Steam Workshop APP ID）")

        self.api_key = os.environ.get("STEAM_WORKSHOP_SYNC_API_KEY", "").strip()
        if not self.api_key:
            raise OSError("没有设置 STEAM_WORKSHOP_SYNC_API_KEY（Steam Web API Key，获取: https://steamcommunity.com/dev/apikey）")

        self.timeout = int(os.environ.get("STEAM_WORKSHOP_SYNC_TIMEOUT", 30))
        self.request_delay = float(os.environ.get("STEAM_WORKSHOP_SYNC_REQUEST_DELAY", 1.0))
        self.page_size = int(os.environ.get("STEAM_WORKSHOP_SYNC_PAGE_SIZE", self.DEFAULT_PAGE_SIZE))

        # Steam CMD 配置（保留用于下载功能，抓取不依赖）
        self.steamcmd_path = os.environ.get("STEAM_WORKSHOP_SYNC_STEAMCMD_PATH", "steamcmd")
        self.download_dir = os.environ.get("STEAM_WORKSHOP_SYNC_DOWNLOAD_DIR", "./downloads")
        self.steam_username = os.environ.get("STEAM_WORKSHOP_SYNC_STEAM_USERNAME", "anonymous")
        self.steam_password = os.environ.get("STEAM_WORKSHOP_SYNC_STEAM_PASSWORD", "")
        self.steam_guard_code = os.environ.get("STEAM_WORKSHOP_SYNC_STEAM_GUARD_CODE", "")

        Path(self.download_dir).mkdir(parents=True, exist_ok=True)

        self.session = requests.Session()

        # 代理配置（可选）
        proxy = os.environ.get("STEAM_WORKSHOP_SYNC_PROXY", "").strip()
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
            logger.info(f"使用代理: {proxy}")

        # cursor 分页状态（Steam Web API 使用 cursor 而非页码）
        self._cursor = "*"
        self._next_cursor: str | None = None
        self._total = 0

    @retry_on_error(
        retry_on_status={
            429: None,
            500: 3,
            502: 3,
            503: 3,
            504: 3,
        },
        backoff_base=5.0,
        backoff_max=300.0,
        default_retry=False,
    )
    def _do_request(self, url: str, **kwargs) -> requests.Response:
        """执行 HTTP 请求（带重试机制）"""
        response = self.session.get(url, **kwargs)
        response.raise_for_status()
        return response

    def _resolve_authors(self, steam_ids: list[str]) -> dict[str, dict]:
        """批量解析作者信息（steam64 → personaname, profileurl）

        GetPlayerSummaries 单次最多 100 个 steam_id
        """
        if not steam_ids:
            return {}

        result = {}
        for i in range(0, len(steam_ids), 100):
            batch = steam_ids[i : i + 100]
            params = {
                "key": self.api_key,
                "steamids": ",".join(batch),
            }
            try:
                time.sleep(self.request_delay)
                response = self._do_request(self.PLAYER_SUMMARIES_URL, params=params, timeout=self.timeout)
                data = response.json()
                for player in data.get("response", {}).get("players", []):
                    result[player["steamid"]] = {
                        "personaname": player.get("personaname", ""),
                        "profileurl": player.get("profileurl", ""),
                    }
            except Exception as e:
                logger.warning(f"解析作者信息失败 (batch {i}): {e}")

        return result

    @staticmethod
    def _ts_to_datetime(ts) -> datetime | None:
        """Unix 时间戳 → datetime"""
        if not ts:
            return None
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).replace(tzinfo=None)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _score_to_rating(score, votes_up: int = 0, votes_down: int = 0) -> int | None:
        """投票分数 (0-100) → 星级评分 (1-5)"""
        if not score or (votes_up + votes_down) == 0:
            return None
        try:
            stars = round(float(score) / 20)
            return max(1, min(5, stars))
        except (ValueError, TypeError):
            return None

    def _parse_item(self, detail: dict, authors: dict) -> WorkshopItem:
        """将 API 返回的 publishedfiledetail 转换为 WorkshopItem"""
        item_id = detail["publishedfileid"]
        creator_steam64 = detail.get("creator", "")

        author_info = authors.get(creator_steam64, {})
        author_name = author_info.get("personaname") or creator_steam64
        author_profile = author_info.get("profileurl") or f"https://steamcommunity.com/profiles/{creator_steam64}/"

        # 图片列表：只取 preview_type == 0 (图片预览)，跳过 YouTube 视频 (type 1)
        images = []
        for preview in detail.get("previews", []):
            if preview.get("preview_type") == 0 and preview.get("url"):
                url = preview["url"]
                if "?" in url:
                    url = url.split("?")[0]
                images.append(url)

        # 去重但保持顺序
        images = list(dict.fromkeys(images))

        # 评分
        vote_data = detail.get("vote_data") or {}
        score = vote_data.get("score")
        votes_up = vote_data.get("votes_up", 0)
        votes_down = vote_data.get("votes_down", 0)
        rating = self._score_to_rating(score, votes_up, votes_down)

        # meta_data：保存所有 API 返回的额外字段（供后续使用）
        meta_data: dict = {}

        # 投票数据
        if score is not None:
            meta_data["score"] = score
        meta_data["votes_up"] = votes_up
        meta_data["votes_down"] = votes_down
        meta_data["num_ratings"] = votes_up + votes_down

        # 订阅/收藏/浏览统计
        meta_data["subscriptions"] = detail.get("subscriptions", 0)
        meta_data["favorited"] = detail.get("favorited", 0)
        meta_data["followers"] = detail.get("followers", 0)
        meta_data["views"] = detail.get("views", 0)
        meta_data["num_comments"] = detail.get("num_comments_public", 0)
        meta_data["num_children"] = detail.get("num_children", 0)
        meta_data["num_reports"] = detail.get("num_reports", 0)

        # 生命周期统计
        meta_data["lifetime_subscriptions"] = detail.get("lifetime_subscriptions", 0)
        meta_data["lifetime_favorited"] = detail.get("lifetime_favorited", 0)
        meta_data["lifetime_followers"] = detail.get("lifetime_followers", 0)
        meta_data["lifetime_playtime"] = detail.get("lifetime_playtime", 0)
        meta_data["lifetime_playtime_sessions"] = detail.get("lifetime_playtime_sessions", 0)

        # 文件元数据
        if detail.get("creator_appid"):
            meta_data["creator_appid"] = detail["creator_appid"]
        if detail.get("consumer_appid"):
            meta_data["consumer_appid"] = detail["consumer_appid"]
        if detail.get("file_type") is not None:
            meta_data["file_type"] = detail["file_type"]
        if detail.get("revision") is not None:
            meta_data["revision"] = detail["revision"]
        if detail.get("revision_change_number"):
            meta_data["revision_change_number"] = detail["revision_change_number"]
        if detail.get("hcontent_file"):
            meta_data["hcontent_file"] = detail["hcontent_file"]
        if detail.get("hcontent_preview"):
            meta_data["hcontent_preview"] = detail["hcontent_preview"]
        if detail.get("preview_file_size"):
            meta_data["preview_file_size"] = detail["preview_file_size"]
        if detail.get("flags"):
            meta_data["flags"] = detail["flags"]
        if detail.get("visibility") is not None:
            meta_data["visibility"] = detail["visibility"]

        # 布尔标志
        meta_data["banned"] = detail.get("banned", False)
        if meta_data["banned"] and detail.get("ban_reason"):
            meta_data["ban_reason"] = detail["ban_reason"]
        meta_data["workshop_file"] = detail.get("workshop_file", False)
        meta_data["workshop_accepted"] = detail.get("workshop_accepted", False)
        meta_data["can_subscribe"] = detail.get("can_subscribe", False)
        meta_data["show_subscribe_all"] = detail.get("show_subscribe_all", False)
        meta_data["maybe_inappropriate_sex"] = detail.get("maybe_inappropriate_sex", False)
        meta_data["maybe_inappropriate_violence"] = detail.get("maybe_inappropriate_violence", False)

        # 作者 Steam64 ID（便于后续关联）
        if creator_steam64:
            meta_data["creator_steam64"] = creator_steam64
        if detail.get("banner"):
            meta_data["banner"] = detail["banner"]

        # KV tags（key-value 标签）
        kv_tags = detail.get("kvtags", [])
        if kv_tags:
            meta_data["kv_tags"] = {item.get("key", ""): item.get("value", "") for item in kv_tags if item.get("key")}

        # 标签（display_name 列表）
        tags = [t.get("display_name", t.get("tag", "")) for t in detail.get("tags", []) if t.get("display_name")]
        if tags:
            meta_data["tags"] = tags

        # YouTube 视频预览（preview_type == 1）
        youtube_videos = [p.get("youtubevideoid") for p in detail.get("previews", []) if p.get("preview_type") == 1 and p.get("youtubevideoid")]
        if youtube_videos:
            meta_data["youtube_videos"] = youtube_videos

        # 应用名
        if detail.get("app_name"):
            meta_data["app_name"] = detail["app_name"]

        return WorkshopItem(
            id=item_id,
            url=f"https://steamcommunity.com/sharedfiles/filedetails/?id={item_id}",
            title=detail.get("title", ""),
            coverview_url=detail.get("preview_url", ""),
            author=author_name,
            author_profile=author_profile,
            rating=rating,
            description=detail.get("file_description"),
            file_size=int(detail.get("file_size", 0) or 0),
            images=images,
            created_at=self._ts_to_datetime(detail.get("time_created")),
            updated_at=self._ts_to_datetime(detail.get("time_updated")),
            meta_data=meta_data,
        )

    def get_new_items(self, page: int = 1):
        """获取一页 Workshop items（使用 Steam Web API QueryFiles）

        兼容旧的 page 参数：
        - page=1 重置 cursor，使用初始 cursor="*"
        - page>1 使用上一次返回的 next_cursor
        """
        start_time = datetime.now()

        if page == 1:
            self._cursor = "*"
            self._next_cursor = None

        cursor = self._cursor
        params = {
            "key": self.api_key,
            "appid": self.appid,
            "page_size": str(self.page_size),
            "cursor": cursor,
            "return_vote_data": "true",
            "return_previews": "true",
            "return_tags": "true",
            "return_kv_tags": "true",
            "return_metadata": "true",
        }

        logger.info(f"正在请求 API 第 {page} 页 (cursor={cursor[:20]}...)")
        response = self._do_request(self.QUERY_FILES_URL, params=params, timeout=self.timeout)
        data = response.json().get("response", {})

        details = data.get("publishedfiledetails", [])
        self._total = int(data.get("total", 0))
        self._next_cursor = data.get("next_cursor")

        # 批量解析作者信息
        creator_ids = list(dict.fromkeys(d.get("creator", "") for d in details if d.get("creator")))
        authors = self._resolve_authors(creator_ids)

        items = [self._parse_item(d, authors) for d in details if d.get("result") == 1]

        # 更新 cursor 供下一页使用
        if self._next_cursor:
            self._cursor = self._next_cursor

        # 计算总页数：如果没有 next_cursor 说明已到最后一页
        if not self._next_cursor:
            total_pages = page
        else:
            total_pages = max(page, (self._total + self.page_size - 1) // self.page_size) if self._total else page

        from models.workshop import Pagination

        pagination = Pagination(
            items_count=len(items),
            current_page=page,
            total_pages=total_pages,
        )

        used_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        logger.info(f"爬取第 {page} 页耗时: {used_time_ms}ms (总计 {self._total} 个项目, 本页 {len(items)} 个)")

        return {"pagination": pagination, "items": items}

    def get_items_info(self, item: WorkshopItem) -> WorkshopItem:
        """获取项目详细信息

        使用 Steam Web API 时，所有信息已在 get_new_items 中完整获取，
        此方法直接返回传入的 item（保持接口兼容）。
        """
        return item

    def download_mod(self, item_id: str) -> bool:
        """使用 Steam CMD 下载 Workshop mod（带 Rate Limit 重试机制）"""
        item_id = item_id.strip()
        max_retries = 3
        retry_delay = 60

        for attempt in range(max_retries):
            logger.info(f"开始下载 mod: {item_id} (尝试 {attempt + 1}/{max_retries})")

            steamcmd_temp_dir = os.path.abspath(os.path.join(os.path.dirname(self.steamcmd_path), "downloads"))
            Path(steamcmd_temp_dir).mkdir(parents=True, exist_ok=True)

            cmd = [
                self.steamcmd_path,
                "+force_installdir",
                steamcmd_temp_dir,
                "+login",
                self.steam_username,
            ]

            if self.steam_password:
                cmd.append(self.steam_password)
                if self.steam_guard_code:
                    cmd.append(self.steam_guard_code)

            cmd.extend(["+workshop_download_item", self.appid, item_id, "validate", "+quit"])

            try:
                logger.info(f"执行 Steam CMD 命令: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

                output = result.stdout + result.stderr
                if "Rate Limit" in output or "rate limit" in output.lower():
                    logger.warning(f"检测到 Rate Limit 错误，等待 {retry_delay} 秒后重试...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue

                possible_source_dirs = [
                    os.path.join(steamcmd_temp_dir, "steamapps", "workshop", "content", self.appid, item_id),
                    os.path.join(steamcmd_temp_dir, "steamapps", "workshop", "downloads", self.appid, item_id),
                ]

                source_dir = None
                for possible_dir in possible_source_dirs:
                    if os.path.exists(possible_dir):
                        source_dir = possible_dir
                        break

                if source_dir:
                    target_dir = os.path.join(self.download_dir, item_id)
                    if os.path.exists(target_dir):
                        import shutil

                        shutil.rmtree(target_dir)
                    import shutil

                    shutil.move(source_dir, target_dir)
                    logger.info(f"mod {item_id} 已移动到: {target_dir}")
                    logger.info(f"mod {item_id} 下载成功")
                    return True
                else:
                    if "ERROR!" in output or "failed" in output.lower():
                        logger.error(f"mod {item_id} 下载失败")
                        logger.debug(f"Steam CMD 输出: {result.stdout}")
                        logger.debug(f"Steam CMD 错误输出: {result.stderr}")
                    else:
                        logger.warning(f"未找到下载的 mod 文件，尝试的路径: {possible_source_dirs}")
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

        logger.error(f"mod {item_id} 下载失败，已达到最大重试次数 {max_retries}")
        return False

    def download_mods(self, item_ids: list[str]) -> dict[str, bool]:
        """批量下载 Workshop mods"""
        results = {}
        total = len(item_ids)

        for index, item_id in enumerate(item_ids, 1):
            logger.info(f"正在下载 {index}/{total}: {item_id}")
            success = self.download_mod(item_id)
            results[item_id] = success

            if index < total:
                time.sleep(self.request_delay)

        success_count = sum(1 for success in results.values() if success)
        logger.info(f"下载完成: {success_count}/{total} 成功")

        return results
