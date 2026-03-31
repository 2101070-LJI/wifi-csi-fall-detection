"""
GET /csi/stream — 최신 CSI 파형 데이터

csi_samples 테이블에서 최근 n개 샘플을 읽어
서브캐리어 평균 진폭 시계열을 반환한다.

쿼리 파라미터:
    n : 샘플 수 (기본 100, 최대 500)

반환 예시:
{
    "samples": [
        {"timestamp": 1711360200.123, "mean_amplitude": 0.43},
        ...
    ]
}
"""

import numpy as np
from fastapi import APIRouter, Query

from api.db import query_all

router = APIRouter()


@router.get("/csi/stream")
def get_csi_stream(n: int = Query(default=100, ge=1, le=500)):
    rows = query_all(
        "SELECT timestamp, subcarrier_data, n_subcarriers "
        "FROM csi_samples ORDER BY timestamp DESC LIMIT %s",
        (n,),
    )

    samples = []
    for r in reversed(rows):
        raw: bytes = r["subcarrier_data"]
        arr = np.frombuffer(raw, dtype=np.float32)
        mean_amp = float(arr.mean()) if arr.size > 0 else 0.0
        samples.append({
            "timestamp": r["timestamp"],
            "mean_amplitude": round(mean_amp, 6),
        })

    return {"samples": samples}
