from typing import Optional
from datetime import datetime

from pydantic import BaseModel
from sqlmodel import SQLModel, Field


class Pagination(BaseModel):
    items_count: int = 0
    current_page: int = 1
    total_pages: int = 1


class WorkshopItem(SQLModel, table=True):
    """Workshop Item model"""
    
    __tablename__ = "workshop_items"
    
    id: str = Field(primary_key=True, index=True)
    url: str
    title: str = Field(index=True)
    img_url: str
    author: str = Field(index=True)
    author_profile: str
    rating: Optional[int] = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    synced_at: datetime = Field(default_factory=datetime.utcnow)

    def __repr__(self) -> str:
        return f"WorkshopItem(id={self.id}, title={self.title}, author={self.author}, created_at={self.created_at}, updated_at={self.updated_at}, rating={self.rating})"
