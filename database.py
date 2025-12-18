import os
from datetime import datetime
from typing import Optional, List

from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from dotenv import load_dotenv

from models.workshop import WorkshopItem
from utils.log import get_logger

load_dotenv()

logger = get_logger(__name__)

# 从环境变量获取数据库 URL
DATABASE_URL = os.getenv("STEAM_WORKSHOP_SYNC_DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("STEAM_WORKSHOP_SYNC_DATABASE_URL 环境变量未设置")

# 创建数据库引擎
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

# 创建会话工厂
SessionLocal = sessionmaker[Session](autocommit=False, autoflush=False, bind=engine)

# 创建基类
Base = declarative_base()


class WorkshopItemDB(Base):
    """WorkshopItem 数据库模型"""

    __tablename__ = "workshop_items"

    id = Column(String, primary_key=True, index=True)
    url = Column(String, nullable=False)
    title = Column(String, nullable=False, index=True)
    img_url = Column(String, nullable=False)
    author = Column(String, nullable=False, index=True)
    author_profile = Column(String, nullable=False)
    rating = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    synced_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"<WorkshopItemDB(id={self.id}, title={self.title}, author={self.author})>"
        )


def get_db() -> Session:
    """获取数据库会话"""
    db = SessionLocal()
    try:
        return db
    except Exception as e:
        db.close()
        raise e


def save_workshop_item(
    item: WorkshopItem, db: Optional[Session] = None
) -> WorkshopItemDB:
    """
    保存单个 WorkshopItem 到数据库

    Args:
        item: WorkshopItem 对象
        db: 数据库会话（可选）

    Returns:
        WorkshopItemDB: 保存的数据库对象
    """
    should_close = False
    if db is None:
        db = get_db()
        should_close = True

    try:
        # 检查是否已存在
        existing = db.query(WorkshopItemDB).filter(WorkshopItemDB.id == item.id).first()

        if existing:
            # 更新现有记录
            existing.url = item.url
            existing.title = item.title
            existing.img_url = item.img_url
            existing.author = item.author
            existing.author_profile = item.author_profile
            existing.rating = item.rating
            existing.description = item.description
            existing.created_at = item.created_at
            existing.updated_at = item.updated_at
            existing.synced_at = datetime.utcnow()

            logger.info(f"更新 WorkshopItem: {item.id} - {item.title}")
            db.commit()
            db.refresh(existing)
            return existing
        else:
            # 创建新记录
            db_item = WorkshopItemDB(
                id=item.id,
                url=item.url,
                title=item.title,
                img_url=item.img_url,
                author=item.author,
                author_profile=item.author_profile,
                rating=item.rating,
                description=item.description,
                created_at=item.created_at,
                updated_at=item.updated_at,
                synced_at=datetime.utcnow(),
            )
            db.add(db_item)
            db.commit()
            db.refresh(db_item)

            logger.info(f"保存新 WorkshopItem: {item.id} - {item.title}")
            return db_item

    except Exception as e:
        db.rollback()
        logger.error(f"保存 WorkshopItem 失败: {e}")
        raise
    finally:
        if should_close:
            db.close()


def save_workshop_items(items: List[WorkshopItem]) -> int:
    """
    批量保存 WorkshopItem 到数据库

    Args:
        items: WorkshopItem 对象列表

    Returns:
        int: 保存成功的数量
    """
    db = get_db()
    saved_count = 0

    try:
        for item in items:
            try:
                save_workshop_item(item, db)
                saved_count += 1
            except Exception as e:
                logger.error(f"保存 item {item.id} 失败: {e}")
                continue

        logger.info(f"批量保存完成，成功: {saved_count}/{len(items)}")
        return saved_count

    finally:
        db.close()


def get_workshop_item(item_id: str) -> Optional[WorkshopItemDB]:
    """
    根据 ID 获取 WorkshopItem

    Args:
        item_id: Workshop Item ID

    Returns:
        WorkshopItemDB: 数据库对象或 None
    """
    db = get_db()
    try:
        return db.query(WorkshopItemDB).filter(WorkshopItemDB.id == item_id).first()
    finally:
        db.close()


def init_db():
    """初始化数据库表"""
    logger.info("初始化数据库表...")
    Base.metadata.create_all(bind=engine)
    logger.info("数据库表初始化完成")
