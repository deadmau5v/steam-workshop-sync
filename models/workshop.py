from typing import Optional
from datetime import datetime

from pydantic import BaseModel


class Pagination(BaseModel):
    items_count: int = 0
    current_page: int = 1
    total_pages: int = 1


class WorkshopItem(BaseModel):
    id: str
    url: str
    title: str
    img_url: str
    author: str
    author_profile: str
    rating: Optional[int] = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __repr__(self) -> str:
        return f"WorkshopItem(id={self.id}, title={self.title}, author={self.author}, created_at={self.created_at}, updated_at={self.updated_at}, rating={self.rating})"
