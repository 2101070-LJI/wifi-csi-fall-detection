"""
db_writer.py — MySQL 저장 유틸리티

세션 생성, CSI/마이크 샘플 배치 삽입을 담당한다.
"""

import numpy as np
import mysql.connector
from mysql.connector import pooling

_POOL_SIZE = 3

_CREATE_POOL_KWARGS = dict(
    pool_name    = "csi_pool",
    pool_size    = _POOL_SIZE,
    host         = "localhost",
    database     = "csi_fall_db",
    user         = "csi_user",
    password     = "1111",
    charset      = "utf8mb4",
    autocommit   = False,
)


def _get_pool() -> pooling.MySQLConnectionPool:
    """모듈 수준 싱글턴 커넥션 풀"""
    if not hasattr(_get_pool, "_pool"):
        _get_pool._pool = pooling.MySQLConnectionPool(**_CREATE_POOL_KWARGS)
    return _get_pool._pool


class DBWriter:
    """
    세션 생성 → CSI/마이크 샘플 배치 삽입 → 커밋

    Usage:
        writer = DBWriter()
        session_id = writer.create_session("fall_forward", distance_m=2.0, direction="front")
        writer.insert_csi_batch(session_id, [(ts, amp_array), ...])
        writer.insert_mic_batch(session_id, [(ts, rms), ...])
    """

    def __init__(self):
        self._pool = _get_pool()

    # ── 세션 ─────────────────────────────────────────────────────────────────
    def create_session(self, label: str,
                       distance_m: float | None = None,
                       direction: str | None = None,
                       note: str | None = None) -> int:
        sql = """
            INSERT INTO sessions (label, distance_m, direction, note)
            VALUES (%s, %s, %s, %s)
        """
        return self._exec_insert(sql, (label, distance_m, direction, note))

    # ── CSI 배치 삽입 ─────────────────────────────────────────────────────────
    def insert_csi_batch(self, session_id: int,
                         samples: list[tuple[float, np.ndarray]]):
        """samples: [(timestamp, amplitude_array), ...]"""
        if not samples:
            return
        sql = """
            INSERT INTO csi_samples (session_id, timestamp, subcarrier_data, n_subcarriers)
            VALUES (%s, %s, %s, %s)
        """
        rows = [
            (session_id, ts, amp.astype(np.float32).tobytes(), len(amp))
            for ts, amp in samples
        ]
        self._exec_many(sql, rows)

    # ── 마이크 배치 삽입 ──────────────────────────────────────────────────────
    def insert_mic_batch(self, session_id: int,
                         samples: list[tuple[float, float]]):
        """samples: [(timestamp, rms_amplitude), ...]"""
        if not samples:
            return
        sql = """
            INSERT INTO mic_samples (session_id, timestamp, amplitude)
            VALUES (%s, %s, %s)
        """
        rows = [(session_id, ts, amp) for ts, amp in samples]
        self._exec_many(sql, rows)

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────
    def _exec_insert(self, sql: str, params: tuple) -> int:
        conn = self._pool.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def _exec_many(self, sql: str, rows: list):
        conn = self._pool.get_connection()
        try:
            cur = conn.cursor()
            cur.executemany(sql, rows)
            conn.commit()
        finally:
            conn.close()
