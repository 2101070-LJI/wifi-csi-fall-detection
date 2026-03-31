"""
api/main.py — FastAPI 서버 진입점

실행:
    uvicorn api.main:app --host 0.0.0.0 --port 8000

엔드포인트:
    GET /status      현재 감지 상태
    GET /events      낙상 이벤트 이력
    GET /csi/stream  최신 CSI 파형 데이터
    GET /stats       날짜·시간대별 통계
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import status, events, csi, stats

app = FastAPI(
    title="WiFi-CSI 낙상 감지 API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(status.router)
app.include_router(events.router)
app.include_router(csi.router)
app.include_router(stats.router)
