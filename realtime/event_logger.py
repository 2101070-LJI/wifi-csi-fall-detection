"""
realtime/event_logger.py — 낙상 이벤트 MySQL 저장

fall_events 테이블에 감지 결과를 기록한다.
"""

import logging

import mysql.connector

logger = logging.getLogger(__name__)

_DB_CONFIG = dict(
    host     = "localhost",
    database = "csi_fall_db",
    user     = "csi_user",
    password = "1111",
    charset  = "utf8mb4",
)


class EventLogger:
    """
    낙상 감지 이벤트를 fall_events 테이블에 기록.

    Usage:
        el = EventLogger(model_version="cnn_gru_v1")
        el.connect()
        el.log(csi_confidence=0.92, impact_detected=True, confirmed=True)
        el.close()
    """

    def __init__(self, model_version: str = "unknown"):
        self.model_version = model_version
        self._conn = None

    def connect(self):
        self._conn = mysql.connector.connect(**_DB_CONFIG)

    def close(self):
        if self._conn and self._conn.is_connected():
            self._conn.close()

    def log(
        self,
        csi_confidence: float,
        impact_detected: bool,
        confirmed: bool,
    ):
        """fall_events 테이블에 이벤트 1건 삽입"""
        sql = """
            INSERT INTO fall_events
                (csi_confidence, impact_detected, confirmed, model_version)
            VALUES (%s, %s, %s, %s)
        """
        params = (
            float(csi_confidence),
            int(impact_detected),
            int(confirmed),
            self.model_version,
        )
        try:
            if self._conn is None or not self._conn.is_connected():
                self.connect()
            cur = self._conn.cursor()
            cur.execute(sql, params)
            self._conn.commit()
            cur.close()
        except Exception as e:
            logger.error(f"이벤트 로그 저장 실패: {e}")
