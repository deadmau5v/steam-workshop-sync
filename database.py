from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os

from dotenv import load_dotenv
from models.workshop import WorkshopItem
from services.mod_sync import SteamSource
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine, select
from utils.log import get_logger

load_dotenv()

logger = get_logger(__name__)

# Steam 系统用户 ID（与主项目一致）
STEAM_USER_ID = "00000000-0000-0000-0000-000000000001"

# 从环境变量获取数据库 URL
DATABASE_URL = os.getenv("STEAM_WORKSHOP_SYNC_DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("STEAM_WORKSHOP_SYNC_DATABASE_URL 环境变量未设置")

# 创建数据库引擎
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)


def get_db() -> Session:
    """获取数据库会话"""
    return Session(engine)


def save_workshop_item(item: WorkshopItem, exist_ok: bool = False) -> WorkshopItem:
    """
    保存单个 WorkshopItem 到数据库

    Args:
        item: WorkshopItem 对象
        exist_ok: 如果为 True，当记录已存在时会更新；如果为 False，当记录已存在时直接返回

    Returns:
        WorkshopItem: 保存的数据库对象
    """

    db = get_db()

    try:
        statement = select(WorkshopItem).where(WorkshopItem.id == item.id).with_for_update()
        existing = db.exec(statement).first()

        if existing:
            if not exist_ok:
                return existing

            # A Steam build change wakes the queue in the same transaction as
            # the scraped timestamp, but never replaces translated asset fields.
            is_updated = item.updated_at is not None and (
                existing.updated_at is None or item.updated_at > existing.updated_at
            )
            update_data = item.model_dump(exclude={'id', 'synced_at'})
            if existing.updated_at is not None and not is_updated:
                update_data.pop('updated_at', None)
            for key, value in update_data.items():
                setattr(existing, key, value)
            existing.synced_at = datetime.now(timezone.utc).replace(tzinfo=None)
            if is_updated:
                db.execute(text("""
                    UPDATE public.steam_sync_status
                    SET status = 'pending', error_message = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE workshop_item_id = :item_id
                """), {'item_id': item.id})
            db.commit()
            db.refresh(existing)
            return existing
        else:
            # 创建新记录
            item.synced_at = datetime.utcnow()
            db.add(item)
            db.commit()
            db.refresh(item)
            logger.info(f"保存新 WorkshopItem: {item.id} - {item.title}")
            return item

    except Exception as e:
        db.rollback()
        logger.error(f"保存 WorkshopItem 失败: {e}")
        raise
    finally:
        db.close()


def save_workshop_items(items: list[WorkshopItem]) -> int:
    """
    批量保存 WorkshopItem 到数据库

    Args:
        items: WorkshopItem 对象列表

    Returns:
        int: 保存成功的数量
    """
    saved_count = 0

    for item in items:
        try:
            save_workshop_item(item, exist_ok=True)
            saved_count += 1
        except Exception as e:
            logger.error(f"保存 item {item.id} 失败: {e}")
            continue

    logger.info(f"批量保存完成，成功: {saved_count}/{len(items)}")
    return saved_count


def get_workshop_item(item_id: str) -> WorkshopItem | None:
    """
    根据 ID 获取 WorkshopItem

    Args:
        item_id: Workshop Item ID

    Returns:
        WorkshopItem: 数据库对象或 None
    """
    db = get_db()
    try:
        statement = select(WorkshopItem).where(WorkshopItem.id == item_id)
        return db.exec(statement).first()
    finally:
        db.close()


def init_db():
    """初始化数据库表"""

    logger.info("初始化数据库表...")
    SQLModel.metadata.create_all(bind=engine)
    logger.info("数据库表初始化完成")


# ============================================================
# Steam Sync Status 管理（steam_sync_status 表）
# ============================================================


def get_sync_status(item_id: str) -> dict | None:
    """获取 workshop item 的同步状态"""
    db = get_db()
    try:
        result = db.execute(
            text("SELECT workshop_item_id, asset_id, status, error_message, synced_at FROM public.steam_sync_status WHERE workshop_item_id = :id"),
            {"id": item_id},
        )
        row = result.first()
        if row is None:
            return None
        return {
            "workshop_item_id": row[0],
            "asset_id": str(row[1]) if row[1] else None,
            "status": row[2],
            "error_message": row[3],
            "synced_at": row[4],
        }
    finally:
        db.close()


# Versioned attempt marker in the existing text field, avoiding a schema change.
# Legacy failed/syncing rows did not have a marker and are never bulk requeued.
MAX_ATTEMPTS = 3
ATTEMPT_PATTERN = r'^source-v1 attempt=([1-3]);'
DUE = """(s.status = 'pending' OR (
    substring(s.error_message from :attempt_pattern) IS NOT NULL
    AND CAST(substring(s.error_message from :attempt_pattern) AS integer) < :max_attempts
    AND ((s.status = 'failed' AND s.updated_at <= CURRENT_TIMESTAMP - interval '15 minutes')
         OR (s.status = 'syncing' AND s.updated_at <= CURRENT_TIMESTAMP - interval '90 minutes'))
))"""


@dataclass(frozen=True)
class SourceClaim:
    attempt: int
    claimed_at: datetime
    asset_id: str | None


def seed_source_queue(limit: int = 100) -> None:
    with get_db() as db, db.begin():
        db.execute(text("""
            INSERT INTO public.steam_sync_status (workshop_item_id, status)
            SELECT w.id, 'pending' FROM public.workshop_items w
            LEFT JOIN public.steam_sync_status s ON s.workshop_item_id = w.id
            WHERE s.workshop_item_id IS NULL
            ORDER BY w.updated_at DESC NULLS LAST, w.id LIMIT :limit
            ON CONFLICT (workshop_item_id) DO NOTHING
        """), {'limit': limit})


def expire_final_source_claims() -> int:
    with get_db() as db, db.begin():
        return db.execute(text("""
            UPDATE public.steam_sync_status SET status='failed', updated_at=CURRENT_TIMESTAMP,
                error_message=:failed WHERE status='syncing' AND error_message=:in_progress
                AND updated_at <= CURRENT_TIMESTAMP - interval '90 minutes'
        """), {'failed': f'source-v1 attempt={MAX_ATTEMPTS}; worker lease expired',
               'in_progress': f'source-v1 attempt={MAX_ATTEMPTS}; in progress'}).rowcount


def get_pending_sync_items(limit: int = 10) -> list[WorkshopItem]:
    with get_db() as db:
        query = select(WorkshopItem).from_statement(text(f"""
            SELECT w.* FROM public.workshop_items w
            JOIN public.steam_sync_status s ON s.workshop_item_id=w.id
            WHERE {DUE} ORDER BY s.updated_at, w.id LIMIT :limit
        """))
        return list(db.execute(query, {'attempt_pattern': ATTEMPT_PATTERN,
                                      'max_attempts': MAX_ATTEMPTS, 'limit': limit}).scalars())


def _lock_item(db: Session, item: WorkshopItem) -> None:
    row = db.execute(text('SELECT updated_at FROM public.workshop_items WHERE id=:id FOR UPDATE'),
                     {'id': item.id}).one_or_none()
    if row is None or row.updated_at != item.updated_at:
        raise RuntimeError('Workshop build changed during source sync')


def _matching_asset(db: Session, item_id: str, *, lock: bool = False):
    return db.execute(text("""
        SELECT id, creator_id, metadata, file_id FROM asset.assets
        WHERE metadata->>'steam_workshop_id' = :item AND deleted_at IS NULL
    """ + (' FOR UPDATE' if lock else '')), {'item': item_id}).one_or_none()


def claim_source(item: WorkshopItem, *, expected_asset_id: str | None = None) -> SourceClaim | None:
    with get_db() as db, db.begin():
        _lock_item(db, item)
        recovery = expected_asset_id is not None
        if recovery:
            asset = _matching_asset(db, item.id)
            if asset is None or str(asset.id) != expected_asset_id or str(asset.creator_id) != STEAM_USER_ID:
                raise RuntimeError('Workshop item does not match the expected Steam asset')
            db.execute(text("""
                INSERT INTO public.steam_sync_status (workshop_item_id, status)
                VALUES (:item, 'pending') ON CONFLICT (workshop_item_id) DO NOTHING
            """), {'item': item.id})
        current = db.execute(text(f"""
            SELECT s.asset_id, s.status, ({DUE}) AS due,
                   substring(s.error_message from :attempt_pattern) AS attempt,
                   s.updated_at > CURRENT_TIMESTAMP - interval '90 minutes' AS fresh
            FROM public.steam_sync_status s WHERE s.workshop_item_id=:item FOR UPDATE
        """), {'item': item.id, 'attempt_pattern': ATTEMPT_PATTERN, 'max_attempts': MAX_ATTEMPTS}).one_or_none()
        if not current or (not recovery and not current.due):
            return None
        if recovery and current.status == 'syncing' and current.attempt and current.fresh:
            return None
        if recovery and current.asset_id and str(current.asset_id) != expected_asset_id:
            raise RuntimeError('sync status belongs to a different asset')
        attempt = 1 if recovery or current.status == 'pending' else int(current.attempt) + 1
        claimed_at = db.execute(text("""
            UPDATE public.steam_sync_status SET status='syncing', updated_at=clock_timestamp(),
                error_message=:marker WHERE workshop_item_id=:item RETURNING updated_at
        """), {'item': item.id, 'marker': f'source-v1 attempt={attempt}; in progress'}).scalar_one()
        asset_id = expected_asset_id or (str(current.asset_id) if current.asset_id else None)
        return SourceClaim(attempt, claimed_at, asset_id)


def fail_source(item: WorkshopItem, claim: SourceClaim, reason: str) -> None:
    with get_db() as db, db.begin():
        db.execute(text("""
            UPDATE public.steam_sync_status SET status='failed', updated_at=CURRENT_TIMESTAMP,
                error_message=:marker WHERE workshop_item_id=:item
                    AND status='syncing' AND updated_at=:claim
        """), {'item': item.id, 'claim': claim.claimed_at,
               'marker': f'source-v1 attempt={claim.attempt}; {reason}'})


def _insert_file(db: Session, key: str, name: str, mime: str, size: int | None = None) -> str:
    return str(db.execute(text("""
        INSERT INTO public.files (user_id, object_key, name, mime_type, size, status)
        VALUES (:owner, :key, :name, :mime, :size, 'completed') RETURNING id
    """), {'owner': STEAM_USER_ID, 'key': key, 'name': name, 'mime': mime, 'size': size}).scalar_one())


def commit_source(item: WorkshopItem, source: SteamSource, claim: SourceClaim,
                  *, images: dict | None = None) -> str:
    """Atomically publish only an uploaded, read-back-verified Steam source."""
    if item.updated_at is None:
        raise RuntimeError('missing Workshop build timestamp')
    updated_at = item.updated_at if item.updated_at.tzinfo else item.updated_at.replace(tzinfo=timezone.utc)
    if int(updated_at.timestamp()) != source.steam_time_updated:
        raise RuntimeError('source belongs to a different Workshop build')
    with get_db() as db, db.begin():
        _lock_item(db, item)
        status = db.execute(text("""
            SELECT asset_id FROM public.steam_sync_status WHERE workshop_item_id=:item
            AND status='syncing' AND updated_at=:claim FOR UPDATE
        """), {'item': item.id, 'claim': claim.claimed_at}).one_or_none()
        if status is None:
            raise RuntimeError('source claim expired or superseded')
        existing = _matching_asset(db, item.id, lock=True)
        expected = claim.asset_id or (str(status.asset_id) if status.asset_id else None)
        if expected and (existing is None or str(existing.id) != expected):
            raise RuntimeError('source asset no longer matches the claim')
        if existing and str(existing.creator_id) != STEAM_USER_ID:
            raise RuntimeError('source asset is not owned by the Steam system account')
        previous = ((existing.metadata or {}).get('steam_source') or {}) if existing else {}
        if isinstance(previous.get('steam_time_updated'), int) and previous['steam_time_updated'] > source.steam_time_updated:
            raise RuntimeError('refusing to replace a newer source')
        file_id = db.execute(text("""
            SELECT id FROM public.files WHERE object_key=:key AND size=:size
                AND user_id=:owner AND status='completed' ORDER BY id LIMIT 1
        """), {'key': source.object_key, 'size': source.size, 'owner': STEAM_USER_ID}).scalar_one_or_none()
        if file_id is None:
            file_id = _insert_file(db, source.object_key, f'{item.id}.rwmod', 'application/rwmod', source.size)
        metadata = {'steam_source': {
            'file_id': str(file_id), 'sha256': source.sha256, 'object_key': source.object_key,
            'steam_time_updated': source.steam_time_updated,
        }}
        if existing:
            asset_id = str(existing.id)
            db.execute(text("""
                UPDATE asset.assets SET metadata=COALESCE(metadata, '{}'::jsonb) || CAST(:metadata AS jsonb)
                WHERE id=:id
            """), {'metadata': json.dumps(metadata), 'id': asset_id})
        else:
            asset_id = _insert_source_asset(db, item, str(file_id), metadata, images or {})
        db.execute(text("""
            UPDATE public.steam_sync_status SET status='completed', asset_id=:asset, error_message=NULL,
                synced_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE workshop_item_id=:item
        """), {'asset': asset_id, 'item': item.id})
        return asset_id


def _insert_source_asset(db: Session, item: WorkshopItem, file_id: str, metadata: dict, images: dict) -> str:
    from mimetypes import guess_type
    from pathlib import PurePosixPath

    def image_file(key: str) -> str:
        return _insert_file(db, key, PurePosixPath(key).name, guess_type(key)[0] or 'application/octet-stream')

    cover = image_file(images['cover_key']) if images.get('cover_key') else None
    screenshots = [image_file(key) for key in images.get('screenshot_keys', [])]
    metadata.update(steam_workshop_id=item.id, steam_url=item.url, steam_author=item.author, steam_rating=item.rating)
    asset_id = str(db.execute(text("""
        INSERT INTO asset.assets (title, description, creator_id, version, file_id, cover_file_id,
            screenshot_file_ids, visibility, status, published_at, created_at, updated_at, metadata)
        VALUES (CAST(:title AS jsonb), CAST(:description AS jsonb), :owner, '1.0.0', :file, :cover,
            CAST(:screenshots AS uuid[]), 'public', 'published', :published, :created, :updated,
            CAST(:metadata AS jsonb)) RETURNING id
    """), {
        'title': json.dumps({'zh': item.title, 'en': item.title}),
        'description': json.dumps({'zh': item.description, 'en': item.description}) if item.description else None,
        'owner': STEAM_USER_ID, 'file': file_id, 'cover': cover, 'screenshots': screenshots or None,
        'published': item.synced_at, 'created': item.created_at or item.synced_at,
        'updated': item.updated_at or item.synced_at, 'metadata': json.dumps(metadata),
    }).scalar_one())
    db.execute(text('INSERT INTO asset.asset_stats (asset_id) VALUES (:id) ON CONFLICT DO NOTHING'), {'id': asset_id})
    return asset_id


def get_existing_asset_id(item_id: str) -> str | None:
    with get_db() as db:
        asset = _matching_asset(db, item_id)
        return str(asset.id) if asset else None


def get_recovery_asset(item_id: str, asset_id: str) -> str | None:
    with get_db() as db:
        asset = _matching_asset(db, item_id)
        if asset is None or str(asset.id) != asset_id or str(asset.creator_id) != STEAM_USER_ID:
            raise RuntimeError('Workshop item does not match the expected Steam asset')
        return str(asset.file_id) if asset.file_id else None


def read_committed_source(item_id: str, asset_id: str, source: SteamSource) -> dict:
    with get_db() as db:
        row = db.execute(text("""
            SELECT a.file_id AS default_file_id, a.metadata->'steam_source' AS source,
                f.id AS source_file_id, s.status
            FROM asset.assets a
            JOIN public.steam_sync_status s ON s.asset_id=a.id AND s.workshop_item_id=:item
            JOIN public.files f ON CAST(f.id AS text)=a.metadata #>> '{steam_source,file_id}'
            WHERE a.id=:asset AND a.deleted_at IS NULL AND s.status='completed'
              AND f.object_key=:key AND f.size=:size AND f.status='completed' AND f.user_id=:owner
        """), {'item': item_id, 'asset': asset_id, 'key': source.object_key,
               'size': source.size, 'owner': STEAM_USER_ID}).one_or_none()
        if row is None or row.source != {
            'file_id': str(row.source_file_id), 'sha256': source.sha256,
            'object_key': source.object_key, 'steam_time_updated': source.steam_time_updated,
        }:
            raise RuntimeError('committed source read-back did not match')
        return {'default_file_id': str(row.default_file_id) if row.default_file_id else None,
                'source_file_id': str(row.source_file_id), 'status': row.status}


def list_legacy_candidates(limit: int, after: str = '') -> list[dict]:
    """Return hypotheses for targeted review, never mutate or imply a ZIP was inspected."""
    with get_db() as db:
        db.execute(text('SET TRANSACTION READ ONLY'))
        rows = db.execute(text("""
            SELECT w.id AS item_id, CAST(a.id AS text) AS asset_id, s.status,
                   legacy.size AS legacy_recorded_size,
                   'steam/' || w.id || '/' || w.id || '.rwmod' AS legacy_key
            FROM public.workshop_items w
            JOIN asset.assets a ON a.metadata->>'steam_workshop_id'=w.id AND a.deleted_at IS NULL
            LEFT JOIN public.steam_sync_status s ON s.workshop_item_id=w.id
            LEFT JOIN LATERAL (
                SELECT MIN(f.size) AS size, COUNT(*) AS n FROM public.files f
                WHERE f.object_key='steam/' || w.id || '/' || w.id || '.rwmod'
            ) legacy ON true
            WHERE w.id > :after AND a.creator_id=:owner AND (a.metadata->'steam_source') IS NULL
              AND (s.status IN ('failed', 'syncing') OR legacy.n > 0)
            ORDER BY w.id, a.id LIMIT :limit
        """), {'after': after, 'owner': STEAM_USER_ID, 'limit': limit}).mappings()
        return [dict(row) for row in rows]
