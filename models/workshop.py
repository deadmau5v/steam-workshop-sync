from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import ARRAY, String
from sqlmodel import Column, Field, SQLModel


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
    coverview_url: str
    author: str = Field(index=True)
    author_profile: str
    rating: int | None = None
    description: str | None = None
    file_size: int = Field(default=0)
    images: list[str] = Field(sa_column=Column(ARRAY(String)))

    created_at: datetime | None = None
    updated_at: datetime | None = None
    synced_at: datetime = Field(default_factory=datetime.utcnow)

    def __repr__(self) -> str:
        return f"WorkshopItem(id={self.id}, title={self.title}, author={self.author}, created_at={self.created_at}, updated_at={self.updated_at}, rating={self.rating})"
