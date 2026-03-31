"""
GET /events — 낙상 이벤트 이력 (최신순)

쿼리 파라미터:
    limit  : 반환 건수 (기본 50, 최대 200)
    offset : 오프셋 페이지네이션 (기본 0)

반환 예시:
{
    "total": 12,
    "events": [
        {
            "id": 12,
            "detected_at": "2026-03-25T14:30:00",
            "csi_confidence": 0.97,
            "impact_detected": 1,
            "confirmed": 1,
            "model_version": "cnn_gru_v1"
        },
        ...
    ]
}
"""

from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder

from api.db import query_all, query_one

router = APIRouter()


@router.get("/events")
def get_events(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows = query_all(
        "SELECT id, detected_at, csi_confidence, impact_detected, confirmed, model_version "
        "FROM fall_events ORDER BY detected_at DESC LIMIT %s OFFSET %s",
        (limit, offset),
    )
    total = query_one("SELECT COUNT(*) AS cnt FROM fall_events")
    return jsonable_encoder({
        "total": total["cnt"] if total else 0,
        "events": rows,
    })
