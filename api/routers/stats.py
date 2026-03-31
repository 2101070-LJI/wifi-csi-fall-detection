"""
GET /stats — 날짜·시간대별 낙상 통계

반환 예시:
{
    "confirmed_total": 8,
    "daily": [
        {"date": "2026-03-25", "total": 3, "confirmed": 2},
        ...
    ],
    "hourly": [
        {"hour": 14, "total": 5},
        ...
    ]
}
"""

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder

from api.db import query_all, query_one

router = APIRouter()


@router.get("/stats")
def get_stats():
    confirmed_total = query_one(
        "SELECT COUNT(*) AS cnt FROM fall_events WHERE confirmed = 1"
    )

    # 일별 집계 (최근 30일)
    daily = query_all(
        "SELECT DATE(detected_at) AS date, "
        "COUNT(*) AS total, SUM(confirmed) AS confirmed "
        "FROM fall_events "
        "WHERE detected_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) "
        "GROUP BY DATE(detected_at) ORDER BY date ASC"
    )

    # 시간대별 집계 (최근 7일)
    hourly = query_all(
        "SELECT HOUR(detected_at) AS hour, COUNT(*) AS total "
        "FROM fall_events "
        "WHERE detected_at >= DATE_SUB(NOW(), INTERVAL 7 DAY) "
        "GROUP BY HOUR(detected_at) ORDER BY hour ASC"
    )

    return jsonable_encoder({
        "confirmed_total": confirmed_total["cnt"] if confirmed_total else 0,
        "daily": daily,
        "hourly": hourly,
    })
