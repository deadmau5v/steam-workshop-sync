from datetime import datetime
import os

from dotenv import load_dotenv
from models.workshop import WorkshopItem
from sqlmodel import Session, SQLModel, create_engine, select
from utils.log import get_logger

load_dotenv()

logger = get_logger(__name__)

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
