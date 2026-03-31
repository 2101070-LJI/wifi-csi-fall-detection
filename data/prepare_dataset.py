"""
MySQL 수집 데이터 → 학습용 npz 변환

수집된 csi_samples 테이블을 읽어 전처리 파이프라인을 적용한 뒤
ml/train.py 가 읽는 dataset.npz 파일로 저장한다.

사용법:
    cd /home/lee/project
    python data/prepare_dataset.py --out data/dataset.npz
    python data/prepare_dataset.py --out data/dataset.npz --min_sessions 50
"""

import argparse
import sys
import os
import numpy as np
import mysql.connector

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ml.preprocessing import preprocess_csi_session

# ── DB 접속 설정 (db_writer.py 와 동일) ───────────────────────────────────────
DB_CONFIG = dict(
    host="localhost",
    database="csi_fall_db",
    user="csi_user",
    password="1111",
    charset="utf8mb4",
)

# ── 클래스 정의 ────────────────────────────────────────────────────────────────
CLASSES = [
    "fall_forward",
    "fall_side",
    "fall_backward",
    "lie_down_slow",
    "lie_down_fast",
    "walk",
    "sit_down",
    "stand_up",
    "static",
]
CLASS_TO_IDX = {c: i for i, c in enumerate(CLASSES)}


def fetch_sessions(conn, min_sessions: int) -> list[dict]:
    """클래스별 세션 목록 조회 (min_sessions 미만 클래스는 경고만)"""
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, label, distance_m, direction FROM sessions ORDER BY id")
    rows = cur.fetchall()
    by_class: dict[str, list] = {c: [] for c in CLASSES}
    for row in rows:
        label = row["label"]
        if label in by_class:
            by_class[label].append(row)
        else:
            print(f"  [경고] 알 수 없는 레이블 '{label}' — 건너뜀")
    for cls, sessions in by_class.items():
        if len(sessions) < min_sessions:
            print(f"  [경고] '{cls}': {len(sessions)}개 세션 (목표 {min_sessions}개 미만)")
        else:
            print(f"  '{cls}': {len(sessions)}개 세션")
    return [s for sessions in by_class.values() for s in sessions]


def fetch_csi_for_session(conn, session_id: int) -> np.ndarray | None:
    """세션의 CSI 샘플 BLOB 조회 → (timesteps, subcarriers) float32 배열"""
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT subcarrier_data, n_subcarriers FROM csi_samples "
        "WHERE session_id = %s ORDER BY timestamp",
        (session_id,),
    )
    rows = cur.fetchall()
    if not rows:
        return None
    n_sub = rows[0]["n_subcarriers"]
    frames = []
    for row in rows:
        arr = np.frombuffer(row["subcarrier_data"], dtype=np.float32)
        if len(arr) == n_sub:
            frames.append(arr)
    if len(frames) < 2:
        return None
    return np.stack(frames, axis=0)  # (timesteps, n_subcarriers)


def main():
    parser = argparse.ArgumentParser(description="MySQL CSI 데이터 → npz 변환")
    parser.add_argument("--out", default="data/dataset.npz")
    parser.add_argument("--min_sessions", type=int, default=10,
                        help="클래스당 최소 세션 수 (미만 시 경고)")
    parser.add_argument("--n_subcarriers", type=int, default=30)
    parser.add_argument("--window_size",   type=int, default=100)
    parser.add_argument("--stride",        type=int, default=10)
    args = parser.parse_args()

    print("MySQL 접속 중...")
    conn = mysql.connector.connect(**DB_CONFIG)

    print("세션 목록 조회:")
    sessions = fetch_sessions(conn, args.min_sessions)
    print(f"  총 {len(sessions)}개 세션")

    X_list, y_list = [], []
    skip = 0

    for i, sess in enumerate(sessions, 1):
        label = sess["label"]
        sid   = sess["id"]
        idx   = CLASS_TO_IDX.get(label)
        if idx is None:
            skip += 1
            continue

        csi = fetch_csi_for_session(conn, sid)
        if csi is None or csi.shape[0] < args.window_size:
            print(f"  [건너뜀] session_id={sid} '{label}' — 샘플 부족 ({csi.shape[0] if csi is not None else 0})")
            skip += 1
            continue

        try:
            windows = preprocess_csi_session(
                csi,
                n_subcarriers=args.n_subcarriers,
                window_size=args.window_size,
                stride=args.stride,
            )
        except Exception as e:
            print(f"  [오류] session_id={sid}: {e}")
            skip += 1
            continue

        X_list.append(windows)
        y_list.extend([idx] * len(windows))

        if i % 20 == 0 or i == len(sessions):
            print(f"  처리: {i}/{len(sessions)} 세션, 현재 윈도우 수: {sum(len(w) for w in X_list)}")

    conn.close()

    if not X_list:
        print("변환된 데이터가 없습니다. 수집 데이터를 확인하세요.")
        sys.exit(1)

    X = np.concatenate(X_list, axis=0).astype(np.float32)
    y = np.array(y_list, dtype=np.int64)

    # 셔플
    perm = np.random.permutation(len(y))
    X, y = X[perm], y[perm]

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    np.savez(args.out, X=X, y=y, classes=CLASSES)

    print(f"\n저장 완료: {args.out}")
    print(f"  X shape : {X.shape}  (samples, window, features)")
    print(f"  y shape : {y.shape}")
    print(f"  건너뜀  : {skip}개 세션")
    print("\n클래스별 윈도우 수:")
    for idx, cls in enumerate(CLASSES):
        n = (y == idx).sum()
        print(f"  [{idx}] {cls:<20} {n:>6}개")


if __name__ == "__main__":
    main()
