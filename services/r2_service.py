"""R2/S3 存储服务

独立的 R2 上传服务，不依赖主项目 app 模块。
用于上传 mod 文件（.rwmod）和图片到 Cloudflare R2。
"""

from contextlib import closing
import hashlib
import os
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from utils.log import get_logger

logger = get_logger(__name__)


class R2Service:
    """Cloudflare R2 / S3 兼容存储服务"""

    def __init__(
        self,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        endpoint_url: str,
        region_name: str = "auto",
    ):
        self.bucket_name = bucket_name
        self.endpoint_url = endpoint_url
        self.is_configured = bool(access_key_id and secret_access_key and bucket_name and endpoint_url)
        self._client = None

        if self.is_configured:
            try:
                self._client = boto3.client(
                    "s3",
                    endpoint_url=endpoint_url,
                    aws_access_key_id=access_key_id,
                    aws_secret_access_key=secret_access_key,
                    region_name=region_name,
                    config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                                  connect_timeout=10, read_timeout=60, retries={"total_max_attempts": 3}),
                )
            except Exception as e:
                logger.error(f"R2 客户端初始化失败: {e}")
                self.is_configured = False

    def upload_file(self, file_path: str, object_key: str, content_type: str = "application/octet-stream") -> bool:
        """上传文件到 R2

        Args:
            file_path: 本地文件路径
            object_key: R2 对象键（如 steam/123456/123456.rwmod）
            content_type: MIME 类型

        Returns:
            bool: 上传是否成功
        """
        if not self.is_configured or self._client is None:
            logger.error("R2 服务未配置")
            return False

        try:
            self._client.upload_file(
                file_path,
                self.bucket_name,
                object_key,
                ExtraArgs={"ContentType": content_type},
            )
            logger.info(f"上传成功: {object_key}")
            return True
        except Exception as e:
            logger.error(f"上传失败 {object_key}: {e}")
            return False

    def put_immutable_source(self, path: Path, key: str, sha256: str) -> bool:
        """Create only, then verify remote bytes, including on a deduplicated retry."""
        if self._client is None:
            return False
        try:
            size = path.stat().st_size
            with path.open('rb') as body:
                try:
                    self._client.put_object(
                        Bucket=self.bucket_name, Key=key, Body=body, IfNoneMatch='*',
                        ContentLength=size, ContentType='application/octet-stream',
                        Metadata={'sha256': sha256},
                    )
                except ClientError as exc:
                    if exc.response['ResponseMetadata']['HTTPStatusCode'] != 412:
                        raise
            return self.verify_source_object(key, size, sha256)
        except Exception as exc:
            logger.error(f'Immutable source {key}: {type(exc).__name__}')
            return False

    def verify_source_object(self, key: str, size: int, sha256: str) -> bool:
        if self._client is None:
            return False
        response = self._client.get_object(Bucket=self.bucket_name, Key=key)
        digest = hashlib.sha256()
        read = 0
        with closing(response['Body']) as body:
            if response['ContentLength'] != size:
                return False
            while chunk := body.read(1024 * 1024):
                read += len(chunk)
                if read > size:
                    return False
                digest.update(chunk)
        return read == size and digest.hexdigest() == sha256

    def is_empty_legacy_zip(self, key: str) -> bool:
        """Identify the exact 22-byte ZIP produced by the historic empty-folder bug."""
        if self._client is None:
            raise RuntimeError('asset object storage is not configured')
        try:
            head = self._client.head_object(Bucket=self.bucket_name, Key=key)
        except ClientError as exc:
            if exc.response.get('ResponseMetadata', {}).get('HTTPStatusCode') == 404:
                return False
            raise
        if head['ContentLength'] != 22:
            return False
        obj = self._client.get_object(Bucket=self.bucket_name, Key=key, IfMatch=head['ETag'])
        with closing(obj['Body']) as body:
            return obj['ContentLength'] == 22 and body.read(23) == b'PK\x05\x06' + bytes(18)

    def upload_bytes(self, data: bytes, object_key: str, content_type: str = "application/octet-stream") -> bool:
        """上传字节数据到 R2"""
        if not self.is_configured or self._client is None:
            logger.error("R2 服务未配置")
            return False

        try:
            self._client.put_object(
                Bucket=self.bucket_name,
                Key=object_key,
                Body=data,
                ContentType=content_type,
            )
            logger.info(f"上传成功: {object_key} ({len(data)} bytes)")
            return True
        except Exception as e:
            logger.error(f"上传失败 {object_key}: {e}")
            return False

    def object_exists(self, object_key: str) -> bool:
        """检查对象是否存在"""
        if not self.is_configured or self._client is None:
            return False
        try:
            from botocore.exceptions import ClientError

            self._client.head_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except ClientError:
            return False
        except Exception:
            return False


def create_asset_r2_service() -> R2Service:
    """创建资产存储 R2 服务（用于 .rwmod 文件）"""
    return R2Service(
        access_key_id=os.getenv("S3_ACCESS_KEY_ID", ""),
        secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY", ""),
        bucket_name=os.getenv("S3_BUCKET_NAME", ""),
        endpoint_url=os.getenv("S3_ENDPOINT_URL", ""),
        region_name=os.getenv("S3_REGION", "auto"),
    )


def create_image_r2_service() -> R2Service:
    """创建图片存储 R2 服务（用于封面图、截图）"""
    return R2Service(
        access_key_id=os.getenv("S3_IMAGE_ACCESS_KEY_ID", os.getenv("S3_ACCESS_KEY_ID", "")),
        secret_access_key=os.getenv("S3_IMAGE_SECRET_ACCESS_KEY", os.getenv("S3_SECRET_ACCESS_KEY", "")),
        bucket_name=os.getenv("S3_IMAGE_BUCKET_NAME", os.getenv("S3_BUCKET_NAME", "")),
        endpoint_url=os.getenv("S3_IMAGE_ENDPOINT_URL", os.getenv("S3_ENDPOINT_URL", "")),
        region_name=os.getenv("S3_IMAGE_REGION", os.getenv("S3_REGION", "auto")),
    )
