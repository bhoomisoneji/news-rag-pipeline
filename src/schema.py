from __future__ import annotations

from datetime import datetime
from typing import Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class FundingInfo(BaseModel):
    amount: Optional[float] = None
    currency: Optional[str] = None
    round: Optional[str] = None
    investors: list[str] = Field(default_factory=list)
    announced_at: Optional[datetime] = None

    @field_validator("investors", mode="before")
    @classmethod
    def coerce_investors(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise ValueError("investors must be a string or list of strings")


class ArticleRecord(BaseModel):
    id: str
    url: str
    title: str
    author: Union[str, list[str]] = ""
    published_at: datetime
    body: str
    summary: str
    companies: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    category: str
    funding: Optional[FundingInfo] = None

    @field_validator("title", "body", "summary", "id", "url", "category")
    @classmethod
    def non_empty_strings(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("field must be a non-empty string")
        return value.strip()

    @field_validator("author", mode="before")
    @classmethod
    def coerce_author(cls, value: object) -> Union[str, list[str]]:
        if value is None:
            return ""
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return str(value).strip()

    @field_validator("companies", "people", "locations", mode="before")
    @classmethod
    def coerce_string_lists(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            seen: list[str] = []
            for item in value:
                text = str(item).strip()
                if text and text not in seen:
                    seen.append(text)
            return seen
        raise ValueError("expected a list of strings")

    @model_validator(mode="after")
    def summary_from_body(self) -> "ArticleRecord":
        if len(self.summary.split()) < 5:
            raise ValueError("summary is too short")
        return self
