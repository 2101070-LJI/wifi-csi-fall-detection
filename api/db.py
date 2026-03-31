"""
api/db.py — MySQL 연결 헬퍼

mysql.connector 기반 단순 쿼리 유틸리티.
DB 설정은 event_logger.py / db_writer.py 와 동일 (csi_user / 1111).
"""

import mysql.connector
from mysql.connector import MySQLConnection

_DB_CONFIG: dict = dict(
    host="localhost",
    database="csi_fall_db",
    user="csi_user",
    password="1111",
    charset="utf8mb4",
)


def _connect() -> MySQLConnection:
    return mysql.connector.connect(**_DB_CONFIG)


def query_one(sql: str, params: tuple = ()) -> dict | None:
    """단일 행 반환. 결과 없으면 None."""
    conn = _connect()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchone()
    finally:
        conn.close()


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    """전체 행 반환."""
    conn = _connect()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()
