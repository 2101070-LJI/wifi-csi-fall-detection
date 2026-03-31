"""
GET /status — 현재 시스템 감지 상태

반환 예시:
{
    "running": true,
    "confirmed_total": 3,
    "last_event": {
        "detected_at": "2026-03-25T14:30:00",
        "csi_confidence": 0.97,
        "impact_detected": 1,
        "confirmed": 1,
        "model_version": "cnn_gru_v1"
    }
}
"""

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder

from api.db import query_one

router = APIRouter()


@router.get("/status")
def get_status():
    latest = query_one(
        "SELECT detected_at, csi_confidence, impact_detected, confirmed, model_version "
        "FROM fall_events ORDER BY detected_at DESC LIMIT 1"
    )
    total = query_one(
        "SELECT COUNT(*) AS cnt FROM fall_events WHERE confirmed = 1"
    )
    return jsonable_encoder({
        "running": True,
        "confirmed_total": total["cnt"] if total else 0,
        "last_event": latest,
    })
