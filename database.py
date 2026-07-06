from datetime import datetime
import json
import os
from uuid import UUID

from dotenv import load_dotenv
from models.workshop import WorkshopItem
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
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
        statement = select(WorkshopItem).where(WorkshopItem.id == item.id)
        existing = db.exec(statement).first()

        if existing:
            if not exist_ok:
                return existing

            update_data = item.model_dump(exclude={"id", "synced_at"})
            for key, value in update_data.items():
                # JSONB 列直接赋值 dict，SQLAlchemy 会正确处理
                setattr(existing, key, value)
            existing.synced_at = datetime.utcnow()

            db.commit()
            db.refresh(existing)
            logger.info(f"更新 WorkshopItem: {item.id} - {item.title}")
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


def upsert_sync_status(item_id: str, status: str = "pending", error_message: str | None = None) -> None:
    """创建或更新同步状态（upsert）"""
    db = get_db()
    try:
        db.execute(
            text(
                """
                INSERT INTO public.steam_sync_status (workshop_item_id, status, error_message)
                VALUES (:item_id, :status, :error_msg)
                ON CONFLICT (workshop_item_id)
                DO UPDATE SET status = :status, error_message = :error_msg, updated_at = CURRENT_TIMESTAMP
                """
            ),
            {"item_id": item_id, "status": status, "error_msg": error_message},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"upsert_sync_status 失败: {e}")
        raise
    finally:
        db.close()


def update_sync_status_completed(item_id: str, asset_id: str) -> None:
    """标记同步完成"""
    db = get_db()
    try:
        db.execute(
            text(
                """
                UPDATE public.steam_sync_status
                SET status = 'completed', asset_id = :asset_id, synced_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE workshop_item_id = :item_id
                """
            ),
            {"item_id": item_id, "asset_id": asset_id},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"update_sync_status_completed 失败: {e}")
        raise
    finally:
        db.close()


def get_pending_sync_items(limit: int = 10) -> list[WorkshopItem]:
    """获取待同步的 Workshop items（status = pending）

    返回 workshop_items 表中对应的数据，且排除已完成/正在同步的。
    """
    db = get_db()
    try:
        result = db.execute(
            text(
                """
                SELECT w.* FROM public.workshop_items w
                JOIN public.steam_sync_status s ON s.workshop_item_id = w.id
                WHERE s.status = 'pending'
                ORDER BY s.created_at
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        rows = result.all()
        items = []
        for row in rows:
            # 将数据库行转换为 WorkshopItem
            item = WorkshopItem(
                id=row[0],
                url=row[1],
                title=row[2],
                coverview_url=row[3],
                author=row[4],
                author_profile=row[5],
                rating=row[6],
                description=row[7],
                file_size=row[11],
                images=row[12] if row[12] else [],
                created_at=row[8],
                updated_at=row[9],
                synced_at=row[10],
                meta_data=row[13] if len(row) > 13 else None,
            )
            items.append(item)
        return items
    finally:
        db.close()


def get_items_without_sync_status(limit: int = 50) -> list[WorkshopItem]:
    """获取还没有同步状态记录的 workshop items（新抓取的）

    这些 item 需要创建 pending 状态的 sync_status 记录。
    """
    db = get_db()
    try:
        result = db.execute(
            text(
                """
                SELECT w.* FROM public.workshop_items w
                LEFT JOIN public.steam_sync_status s ON s.workshop_item_id = w.id
                WHERE s.workshop_item_id IS NULL
                ORDER BY w.synced_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        rows = result.all()
        items = []
        for row in rows:
            item = WorkshopItem(
                id=row[0],
                url=row[1],
                title=row[2],
                coverview_url=row[3],
                author=row[4],
                author_profile=row[5],
                rating=row[6],
                description=row[7],
                file_size=row[11],
                images=row[12] if row[12] else [],
                created_at=row[8],
                updated_at=row[9],
                synced_at=row[10],
                meta_data=row[13] if len(row) > 13 else None,
            )
            items.append(item)
        return items
    finally:
        db.close()


# ============================================================
# Asset / File 记录创建（直接操作数据库，不依赖主项目 ORM）
# ============================================================


def create_file_record(
    object_key: str,
    name: str,
    mime_type: str,
    size: int | None = None,
    status: str = "completed",
    user_id: str = STEAM_USER_ID,
) -> str | None:
    """在 public.files 表创建文件记录

    Returns:
        str: file UUID，失败返回 None
    """
    db = get_db()
    try:
        result = db.execute(
            text(
                """
                INSERT INTO public.files (user_id, object_key, name, mime_type, size, status)
                VALUES (:user_id, :object_key, :name, :mime_type, :size, :status)
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "object_key": object_key,
                "name": name,
                "mime_type": mime_type,
                "size": size,
                "status": status,
            },
        )
        file_id = str(result.scalar_one())
        db.commit()
        logger.info(f"创建 file 记录: {file_id} -> {object_key}")
        return file_id
    except Exception as e:
        db.rollback()
        logger.error(f"创建 file 记录失败: {e}")
        return None
    finally:
        db.close()


def create_asset_record(
    workshop_item: WorkshopItem,
    file_id: str,
    cover_file_id: str | None = None,
    screenshot_file_ids: list[str] | None = None,
) -> str | None:
    """在 asset.assets 表创建资产记录

    Returns:
        str: asset UUID，失败返回 None
    """
    db = get_db()
    try:
        # 构建 title 和 description 的 JSONB（用 json.dumps 让 psycopg2 正确处理）
        title_json = json.dumps({"zh": workshop_item.title, "en": workshop_item.title}, ensure_ascii=False)
        description_json = (
            json.dumps({"zh": workshop_item.description, "en": workshop_item.description}, ensure_ascii=False)
            if workshop_item.description
            else None
        )

        # metadata
        metadata = json.dumps(
            {
                "steam_workshop_id": workshop_item.id,
                "steam_url": workshop_item.url,
                "steam_author": workshop_item.author,
                "steam_rating": workshop_item.rating,
            },
            ensure_ascii=False,
        )

        # screenshot_file_ids 需要转为 UUID 数组格式
        ss_ids = screenshot_file_ids if screenshot_file_ids else None

        result = db.execute(
            text(
                """
                INSERT INTO asset.assets (
                    title, description, creator_id, version, file_id, cover_file_id,
                    screenshot_file_ids, visibility, status, published_at, created_at, updated_at, metadata
                )
                VALUES (
                    CAST(:title AS jsonb), CAST(:description AS jsonb), :creator_id, '1.0.0', :file_id, :cover_file_id,
                    :screenshot_ids, 'public', 'published', :published_at, :created_at, :updated_at, CAST(:metadata AS jsonb)
                )
                RETURNING id
                """
            ),
            {
                "title": title_json,
                "description": description_json,
                "creator_id": STEAM_USER_ID,
                "file_id": file_id,
                "cover_file_id": cover_file_id,
                "screenshot_ids": ss_ids,
                "published_at": workshop_item.synced_at or datetime.utcnow(),
                "created_at": workshop_item.created_at or workshop_item.synced_at or datetime.utcnow(),
                "updated_at": workshop_item.updated_at or workshop_item.synced_at or datetime.utcnow(),
                "metadata": metadata,
            },
        )
        asset_id = str(result.scalar_one())

        # 创建 asset_stats 记录
        db.execute(
            text("INSERT INTO asset.asset_stats (asset_id) VALUES (:asset_id) ON CONFLICT DO NOTHING"),
            {"asset_id": asset_id},
        )

        db.commit()
        logger.info(f"创建 asset 记录: {asset_id} -> {workshop_item.title}")
        return asset_id
    except Exception as e:
        db.rollback()
        logger.error(f"创建 asset 记录失败: {e}")
        return None
    finally:
        db.close()


def get_existing_asset_id(item_id: str) -> str | None:
    """检查 workshop item 是否已有 asset 记录（通过 metadata.steam_workshop_id 查询）"""
    db = get_db()
    try:
        result = db.execute(
            text(
                """
                SELECT a.id FROM asset.assets a
                WHERE a.metadata->>'steam_workshop_id' = :item_id
                AND a.deleted_at IS NULL
                LIMIT 1
                """
            ),
            {"item_id": item_id},
        )
        row = result.first()
        return str(row[0]) if row else None
    finally:
        db.close()
