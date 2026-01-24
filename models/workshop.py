import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer
from sqlalchemy import ARRAY, JSON, String
from sqlmodel import Column, Field, SQLModel


class Pagination(BaseModel):
    items_count: int = 0
    current_page: int = 1
    total_pages: int = 1


class WorkshopItem(SQLModel, table=True):
    """Workshop Item model"""

    __tablename__ = "workshop_items"  # type: ignore[assignment]
    model_config = ConfigDict(arbitrary_types_allowed=True)

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
    meta_data: dict[str, Any] | None = Field(default=None, sa_column=Column("metadata", JSON))

    @field_serializer("meta_data")
    def serialize_meta_data(self, value: dict[str, Any] | None, _info) -> str | None:
        """Serialize dict to JSON string for database storage."""
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)

    def __repr__(self) -> str:
        return f"WorkshopItem(id={self.id}, title={self.title}, author={self.author}, created_at={self.created_at}, updated_at={self.updated_at}, rating={self.rating})"
