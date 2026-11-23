"""Download and validate Steam originals, then publish immutable archives."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timezone
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
import zipfile

import requests
from utils.log import get_logger

from services.r2_service import create_asset_r2_service, create_image_r2_service

logger = get_logger(__name__)


@dataclass(frozen=True)
class SteamSource:
    object_key: str
    sha256: str
    size: int
    steam_time_updated: int


def _installed_epoch(manifest: Path, item_id: str) -> int:
    # Valve's appworkshop ACF has nested quoted key/value pairs. Only trust
    # WorkshopItemsInstalled, never the newer pending WorkshopItemDetails.
    tokens = iter(re.findall(r'"([^"\r\n]*)"|([{}])', manifest.read_text()))
    stack = []
    pending = None
    target = ['AppWorkshop', 'WorkshopItemsInstalled', item_id]
    for value, brace in tokens:
        if brace == '{':
            stack.append(pending)
            pending = None
        elif brace == '}':
            stack.pop()
            pending = None
        elif pending is None:
            pending = value
        else:
            if stack == target and pending == 'timeupdated':
                return int(value)
            pending = None
    raise ValueError('no installed build timestamp')


def _raise_walk_error(exc: OSError) -> None:
    raise exc


def _payload_files(path: Path) -> list[Path]:
    if not path.is_dir() or path.is_symlink():
        raise ValueError('missing final Workshop content directory')
    files = []
    for root, dirs, names in os.walk(path, followlinks=False, onerror=_raise_walk_error):
        for name in sorted(dirs):
            if (Path(root) / name).is_symlink():
                raise ValueError('symlink in Workshop payload')
        for name in names:
            file = Path(root) / name
            if not stat.S_ISREG(file.lstat().st_mode):
                raise ValueError('non-regular file in Workshop payload')
            files.append(file)
    if not any(f.stat().st_size > 0 for f in files):
        raise ValueError('no nonempty Workshop files')
    return sorted(files)


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
        self.download_dir = Path(os.environ.get("STEAM_WORKSHOP_SYNC_DOWNLOAD_DIR", "./downloads")).resolve()
        self.steam_username = os.environ.get("STEAM_WORKSHOP_SYNC_STEAM_USERNAME", "anonymous")
        self.steam_password = os.environ.get("STEAM_WORKSHOP_SYNC_STEAM_PASSWORD", "")
        self.steam_guard_code = os.environ.get("STEAM_WORKSHOP_SYNC_STEAM_GUARD_CODE", "")
        self.request_delay = float(os.environ.get("STEAM_WORKSHOP_SYNC_REQUEST_DELAY", 1.0))

        # R2 服务
        self.asset_r2 = create_asset_r2_service()
        self.image_r2 = create_image_r2_service()

        # 下载目录
        Path(self.download_dir).mkdir(parents=True, exist_ok=True)

    @contextmanager
    def download_mod_with_steamcmd(self, item_id: str, *, steam_time_updated: int):
        """Use a fresh install root; never package partial or cached directories."""
        if not re.fullmatch(r'[0-9]{1,20}', item_id) or not re.fullmatch(r'[0-9]{1,20}', self.appid):
            raise ValueError('invalid Workshop or app ID')
        with tempfile.TemporaryDirectory(prefix=f'steam-{item_id}-', dir=self.download_dir) as root:
            cmd = [self.steamcmd_path, '+force_install_dir', root, '+login', self.steam_username]
            if self.steam_password:
                cmd.append(self.steam_password)
                if self.steam_guard_code:
                    cmd.append(self.steam_guard_code)
            cmd.extend(['+workshop_download_item', self.appid, item_id, 'validate', '+quit'])
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, errors='replace', timeout=900)
                output = result.stdout + '\n' + result.stderr
                match = re.search(rf'^Success\. Downloaded item {item_id} to "([^"\n]+)"', output, re.M)
                if result.returncode or not match or re.search(r'ERROR!|rate limit', output, re.I):
                    raise ValueError('SteamCMD did not report a successful download')
                workshop = Path(root) / 'steamapps' / 'workshop'
                path = workshop / 'content' / self.appid / item_id
                # Valve may print a terminal /. suffix; resolve it, but reject paths
                # outside the fresh root and never fall back to downloads/ staging.
                if Path(match[1]).resolve() != path or path.resolve() != path:
                    raise ValueError('SteamCMD installed outside the expected content path')
                epoch = _installed_epoch(workshop / f'appworkshop_{self.appid}.acf', item_id)
                if epoch != steam_time_updated:
                    raise ValueError(f'installed build {epoch} differs from expected {steam_time_updated}')
                _payload_files(path)
            except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as exc:
                # Raw SteamCMD output and command arguments may contain credentials.
                reason = str(exc) if type(exc) is ValueError else type(exc).__name__
                logger.warning(f'Workshop {item_id}: {reason}')
                yield None
                return
            yield path

    def pack_mod_to_rwmod(self, mod_dir: Path) -> Path | None:
        """Create a deterministic ZIP of regular files and verify every CRC."""
        tmp_path = None
        try:
            files = _payload_files(mod_dir)
            with tempfile.NamedTemporaryFile(suffix='.rwmod', delete=False, dir=self.download_dir) as tmp_file:
                tmp_path = Path(tmp_file.name)
            with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as archive:
                for file in files:
                    entry = zipfile.ZipInfo(file.relative_to(mod_dir).as_posix())
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    entry.file_size = file.stat().st_size
                    with file.open('rb') as src, archive.open(entry, 'w') as dst:
                        while chunk := src.read(1024 * 1024):
                            dst.write(chunk)
            with zipfile.ZipFile(tmp_path) as archive:
                if not any(not entry.is_dir() and entry.file_size > 0 for entry in archive.infolist()):
                    raise ValueError('archive contains no nonempty files')
                if archive.testzip() is not None:
                    raise ValueError('archive failed CRC validation')
            return tmp_path
        except Exception as exc:
            logger.warning(f'Workshop packaging failed: {type(exc).__name__}')
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
            return None

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

            object_key = f"steam/{item_id}/cover{ext}" if image_type == "cover" else f"steam/{item_id}/screenshot_{index}{ext}"

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

    def sync_mod(self, workshop_item, *, upload: bool = True) -> SteamSource | None:
        """Return the verified source, without modifying the DB or legacy object."""
        item_id = workshop_item.id
        updated_at = workshop_item.updated_at
        if updated_at is None:
            logger.warning(f'Workshop {item_id}: no Steam build timestamp')
            return None
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        epoch = int(updated_at.timestamp())
        if epoch <= 0:
            return None
        with self.download_mod_with_steamcmd(item_id, steam_time_updated=epoch) as mod_dir:
            if mod_dir is None:
                return None
            path = self.pack_mod_to_rwmod(mod_dir)
            if path is None:
                return None
            try:
                size = path.stat().st_size
                # public.files.size is a PostgreSQL integer.
                if size > 2_147_483_647:
                    raise ValueError('archive exceeds maximum database file size')
                with path.open('rb') as handle:
                    digest = hashlib.file_digest(handle, 'sha256').hexdigest()
                key = f'steam/{item_id}/source/{digest}.rwmod'
                if upload and not self.asset_r2.put_immutable_source(path, key, digest):
                    return None
                return SteamSource(key, digest, size, epoch)
            finally:
                path.unlink(missing_ok=True)
