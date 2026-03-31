"""
collect.py — CSI 수집 CLI

Usage:
    python collect.py --label fall_forward --duration 3 --distance 2.0 --direction front
    python collect.py --label walk --duration 5 --sessions 10

수집 흐름:
  1. CSIReader 백그라운드 스레드 시작
  2. --duration 초 동안 샘플 버퍼링
  3. DBWriter로 세션 생성 → CSI 배치 삽입
  4. --sessions 횟수만큼 반복 (세션 간 3초 대기)
"""

import argparse
import time
import sys

from csi_reader import CSIReader
from db_writer   import DBWriter

_SESSION_PAUSE = 3.0   # 세션 간 대기 (초)


def collect_one_session(csi: CSIReader, db: DBWriter,
                        label: str, duration: float,
                        distance_m: float | None, direction: str | None,
                        session_num: int) -> dict:
    """
    단일 세션 수집 → DB 저장 → 통계 반환
    """
    print(f"  [세션 {session_num}] 수집 시작 ({duration}s) — '{label}'", flush=True)

    # 큐 비우기 (이전 잔여 샘플 제거)
    while not csi.queue.empty():
        csi.queue.get_nowait()

    csi_buf: list = []

    deadline = time.time() + duration
    while time.time() < deadline:
        while not csi.queue.empty():
            csi_buf.append(csi.queue.get_nowait())
        time.sleep(0.01)

    # DB 저장
    session_id = db.create_session(label, distance_m=distance_m,
                                   direction=direction)
    db.insert_csi_batch(session_id, csi_buf)

    stats = {
        "session_id": session_id,
        "csi_samples": len(csi_buf),
    }
    print(f"  [세션 {session_num}] 저장 완료 — "
          f"session_id={session_id}, CSI={len(csi_buf)}개", flush=True)
    return stats


def main():
    parser = argparse.ArgumentParser(description="CSI + 마이크 동기화 수집")
    parser.add_argument("--label",     required=True,
                        choices=[
                            "fall_forward", "fall_side", "fall_backward",
                            "lie_down_slow", "lie_down_fast",
                            "walk", "sit_down", "stand_up", "static",
                        ],
                        help="수집 클래스 레이블")
    parser.add_argument("--duration",  type=float, default=3.0,
                        help="세션당 수집 시간 (초, 기본 3)")
    parser.add_argument("--sessions",  type=int,   default=1,
                        help="반복 세션 수 (기본 1)")
    parser.add_argument("--distance",  type=float, default=None,
                        help="측정 거리 (m)")
    parser.add_argument("--direction", type=str,   default=None,
                        choices=["front", "side", "back"],
                        help="측정 방향")
    args = parser.parse_args()

    print(f"=== 수집 시작 ===")
    print(f"  레이블   : {args.label}")
    print(f"  세션수   : {args.sessions}")
    print(f"  세션시간 : {args.duration}s")
    print(f"  거리     : {args.distance}m")
    print(f"  방향     : {args.direction}")

    csi = CSIReader()
    db  = DBWriter()

    csi.start()

    total_csi = 0

    try:
        for i in range(1, args.sessions + 1):
            if i > 1:
                print(f"  ({_SESSION_PAUSE}초 대기 후 다음 세션 시작...)", flush=True)
                time.sleep(_SESSION_PAUSE)

            stats = collect_one_session(
                csi, db,
                label      = args.label,
                duration   = args.duration,
                distance_m = args.distance,
                direction  = args.direction,
                session_num = i,
            )
            total_csi += stats["csi_samples"]

    except KeyboardInterrupt:
        print("\n수집 중단 (Ctrl-C)", flush=True)
    finally:
        csi.stop()

    print(f"\n=== 수집 완료 ===")
    print(f"  총 CSI 샘플 : {total_csi}")


if __name__ == "__main__":
    main()
