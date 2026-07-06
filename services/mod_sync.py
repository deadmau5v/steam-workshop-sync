"""Mod 文件同步服务

完整流程：
1. 从数据库获取待同步的 workshop_items（通过 steam_sync_status 跟踪状态）
2. 使用 SteamCMD 下载 mod 文件
3. 打包为 .rwmod（zip 格式）
4. 上传 .rwmod 到 R2 资产存储
5. 下载封面图和截图，上传到 R2 图片存储
6. 在数据库创建 file + asset 记录
7. 更新 steam_sync_status 为 completed

独立实现，不依赖主项目 app 模块。
"""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import zipfile

import requests
from services.r2_service import R2Service, create_asset_r2_service, create_image_r2_service
from utils.log import get_logger

logger = get_logger(__name__)

# Steam 系统用户 ID（与主项目一致）
STEAM_USER_ID = "00000000-0000-0000-0000-000000000001"

# 图片 MIME 类型映射
IMAGE_EXT_MAP = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


class ModSyncService:
    """Mod 文件同步服务"""

    def __init__(self):
        self.appid = os.environ.get("STEAM_WORKSHOP_SYNC_APP_ID", "").strip()
        self.steamcmd_path = os.environ.get("STEAM_WORKSHOP_SYNC_STEAMCMD_PATH", "steamcmd")
        self.download_dir = os.environ.get("STEAM_WORKSHOP_SYNC_DOWNLOAD_DIR", "./downloads")
        self.steam_username = os.environ.get("STEAM_WORKSHOP_SYNC_STEAM_USERNAME", "anonymous")
        self.steam_password = os.environ.get("STEAM_WORKSHOP_SYNC_STEAM_PASSWORD", "")
        self.steam_guard_code = os.environ.get("STEAM_WORKSHOP_SYNC_STEAM_GUARD_CODE", "")
        self.request_delay = float(os.environ.get("STEAM_WORKSHOP_SYNC_REQUEST_DELAY", 1.0))

        # R2 服务
        self.asset_r2 = create_asset_r2_service()
        self.image_r2 = create_image_r2_service()

        # 下载目录
        Path(self.download_dir).mkdir(parents=True, exist_ok=True)

    def download_mod_with_steamcmd(self, item_id: str, max_retries: int = 3) -> Path | None:
        """使用 SteamCMD 下载 Workshop mod

        Args:
            item_id: Workshop item ID
            max_retries: 最大重试次数

        Returns:
            Path: 下载的 mod 目录路径，失败返回 None
        """
        item_id = item_id.strip()
        retry_delay = 60

        steamcmd_temp_dir = os.path.abspath(os.path.join(os.path.dirname(self.steamcmd_path), "downloads"))
        Path(steamcmd_temp_dir).mkdir(parents=True, exist_ok=True)

        for attempt in range(max_retries):
            logger.info(f"SteamCMD 下载 mod: {item_id} (尝试 {attempt + 1}/{max_retries})")

            cmd = [
                self.steamcmd_path,
                "+force_install_dir",
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
                logger.info(f"执行 SteamCMD: {' '.join(cmd[:6])}...")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

                output = result.stdout + result.stderr

                # Rate Limit 重试
                if "Rate Limit" in output or "rate limit" in output.lower():
                    logger.warning(f"Rate Limit，等待 {retry_delay} 秒后重试...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue

                # 查找下载的文件
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
                        shutil.rmtree(target_dir)
                    shutil.move(source_dir, target_dir)
                    logger.info(f"mod {item_id} 下载成功: {target_dir}")
                    return Path(target_dir)
                else:
                    if "ERROR!" in output or "failed" in output.lower():
                        logger.error(f"mod {item_id} 下载失败: {output[-200:]}")
                    else:
                        logger.warning(f"mod {item_id} 未找到下载文件")
                    return None

            except subprocess.TimeoutExpired:
                logger.error(f"mod {item_id} 下载超时（1小时）")
                return None
            except FileNotFoundError:
                logger.error(f"SteamCMD 未找到: {self.steamcmd_path}")
                return None
            except Exception as e:
                logger.error(f"mod {item_id} 下载异常: {e}")
                return None

        logger.error(f"mod {item_id} 下载失败，已达最大重试次数")
        return None

    def pack_mod_to_rwmod(self, mod_dir: Path) -> Path | None:
        """将 mod 目录打包成 .rwmod 文件（zip 格式）

        Args:
            mod_dir: mod 文件目录

        Returns:
            Path: .rwmod 文件路径，失败返回 None
        """
        if not mod_dir.exists():
            return None

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".rwmod", delete=False) as tmp_file:
                tmp_path = Path(tmp_file.name)

            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, _dirs, files in os.walk(mod_dir):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(mod_dir)
                        zipf.write(file_path, arcname)

            logger.info(f"打包完成: {tmp_path} ({tmp_path.stat().st_size} bytes)")
            return tmp_path
        except Exception as e:
            logger.error(f"打包失败: {e}")
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()
            return None

    def upload_rwmod_to_r2(self, rwmod_path: Path, item_id: str) -> str | None:
        """上传 .rwmod 文件到 R2

        Returns:
            str: R2 object_key，失败返回 None
        """
        object_key = f"steam/{item_id}/{item_id}.rwmod"
        success = self.asset_r2.upload_file(str(rwmod_path), object_key, content_type="application/octet-stream")
        return object_key if success else None

    def download_and_upload_image(self, image_url: str, item_id: str, image_type: str, index: int = 0) -> str | None:
        """下载图片并上传到 R2 图片存储

        Args:
            image_url: 图片 URL
            item_id: Workshop item ID
            image_type: "cover" 或 "screenshot"
            index: 截图序号

        Returns:
            str: R2 object_key，失败返回 None
        """
        if not self.image_r2.is_configured:
            logger.warning("图片 R2 服务未配置")
            return None

        tmp_path = None
        try:
            image_url_clean = image_url.split("?")[0]

            # 获取 Content-Type
            try:
                head_resp = requests.head(image_url_clean, timeout=10)
                content_type = head_resp.headers.get("content-type", "image/jpeg")
            except Exception:
                content_type = "image/jpeg"

            ext = IMAGE_EXT_MAP.get(content_type, ".jpg")

            if image_type == "cover":
                object_key = f"steam/{item_id}/cover{ext}"
            else:
                object_key = f"steam/{item_id}/screenshot_{index}{ext}"

            # 下载图片
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()

            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
                tmp_path = Path(tmp_file.name)
                tmp_path.write_bytes(response.content)

            # 上传到 R2
            success = self.image_r2.upload_file(str(tmp_path), object_key, content_type=content_type)
            return object_key if success else None

        except Exception as e:
            logger.error(f"图片处理失败 {image_url[:50]}: {e}")
            return None
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()

    def sync_images(self, workshop_item) -> dict[str, str | list[str]]:
        """同步封面图和截图到 R2

        Args:
            workshop_item: WorkshopItem 对象

        Returns:
            dict: {"cover_key": str|None, "screenshot_keys": list[str]}
        """
        result = {"cover_key": None, "screenshot_keys": []}

        # 封面图
        if workshop_item.coverview_url:
            cover_key = self.download_and_upload_image(workshop_item.coverview_url, workshop_item.id, "cover")
            if cover_key:
                result["cover_key"] = cover_key
                time.sleep(self.request_delay)

        # 截图（最多 10 张）
        if workshop_item.images:
            for i, img_url in enumerate(workshop_item.images[:10]):
                ss_key = self.download_and_upload_image(img_url, workshop_item.id, "screenshot", i)
                if ss_key:
                    result["screenshot_keys"].append(ss_key)
                    time.sleep(self.request_delay)

        return result

    def sync_mod(self, workshop_item) -> bool:
        """同步单个 mod：下载 → 打包 → 上传 R2 → 同步图片

        此方法只负责文件操作，数据库记录由 database.py 的 sync_status 函数管理。

        Args:
            workshop_item: WorkshopItem 对象

        Returns:
            bool: 是否成功
        """
        item_id = workshop_item.id
        logger.info(f"开始同步 mod: {item_id} - {workshop_item.title}")

        rwmod_path = None
        mod_dir = None

        try:
            # 1. SteamCMD 下载
            mod_dir = self.download_mod_with_steamcmd(item_id)
            if not mod_dir:
                logger.error(f"mod {item_id} 下载失败")
                return False

            # 2. 打包 .rwmod
            rwmod_path = self.pack_mod_to_rwmod(mod_dir)
            if not rwmod_path:
                logger.error(f"mod {item_id} 打包失败")
                return False

            # 3. 上传 .rwmod 到 R2
            rwmod_key = self.upload_rwmod_to_r2(rwmod_path, item_id)
            if not rwmod_key:
                logger.error(f"mod {item_id} 上传 R2 失败")
                return False

            # 4. 同步图片到 R2
            images_result = self.sync_images(workshop_item)

            logger.info(f"✓ mod {item_id} 文件同步完成 (rwmod + 封面 + {len(images_result['screenshot_keys'])} 张截图)")
            return True

        except Exception as e:
            logger.error(f"mod {item_id} 同步异常: {e}")
            return False
        finally:
            # 清理临时文件
            if rwmod_path and rwmod_path.exists():
                rwmod_path.unlink()
            # 保留 mod_dir 供后续检查，不自动删除
