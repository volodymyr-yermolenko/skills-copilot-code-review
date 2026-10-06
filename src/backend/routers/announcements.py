"""
Announcement endpoints for the High School Management System API

Reading active announcements is public; managing them requires a signed-in teacher.
"""

import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    """Body for creating or updating an announcement (dates are YYYY-MM-DD)"""
    message: str = Field(..., max_length=500)
    start_date: Optional[date] = None
    expiration_date: date

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message must not be empty")
        return value

    @model_validator(mode="after")
    def start_before_expiration(self):
        if self.start_date and self.start_date > self.expiration_date:
            raise ValueError("Start date must not be after the expiration date")
        return self


def require_teacher(teacher_username: Optional[str]) -> None:
    """Raise 401 unless the username belongs to a signed-in teacher"""
    if not teacher_username:
        raise HTTPException(
            status_code=401, detail="Authentication required for this action")
    if not teachers_collection.find_one({"_id": teacher_username}):
        raise HTTPException(
            status_code=401, detail="Invalid teacher credentials")


def serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a stored document to its API representation"""
    return {
        "id": doc["_id"],
        "message": doc["message"],
        "start_date": doc.get("start_date"),
        "expiration_date": doc["expiration_date"],
    }


def to_document(payload: AnnouncementPayload) -> Dict[str, Any]:
    return {
        "message": payload.message,
        "start_date": payload.start_date.isoformat() if payload.start_date else None,
        "expiration_date": payload.expiration_date.isoformat(),
    }


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get announcements that are currently visible (public)"""
    today = date.today().isoformat()
    query = {
        "expiration_date": {"$gte": today},
        "$or": [
            {"start_date": None},
            {"start_date": {"$exists": False}},
            {"start_date": {"$lte": today}},
        ],
    }
    cursor = announcements_collection.find(query).sort("expiration_date", 1)
    return [serialize(doc) for doc in cursor]


@router.get("/all", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Get every announcement, including scheduled and expired ones - requires teacher authentication"""
    require_teacher(teacher_username)
    cursor = announcements_collection.find({}).sort("expiration_date", -1)
    return [serialize(doc) for doc in cursor]


@router.post("", response_model=Dict[str, Any], status_code=201)
def create_announcement(
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Create an announcement - requires teacher authentication"""
    require_teacher(teacher_username)
    doc = {"_id": uuid.uuid4().hex, **to_document(payload)}
    announcements_collection.insert_one(doc)
    return serialize(doc)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an announcement - requires teacher authentication"""
    require_teacher(teacher_username)
    updated = announcements_collection.find_one_and_update(
        {"_id": announcement_id},
        {"$set": to_document(payload)},
        return_document=True
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return serialize(updated)


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Delete an announcement - requires teacher authentication"""
    require_teacher(teacher_username)
    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return {"message": "Announcement deleted"}
