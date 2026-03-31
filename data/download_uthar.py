"""
UT-HAR 오픈소스 CSI 데이터셋 다운로드 + 포맷 변환

출처: https://github.com/minestone/UT-HAR
논문: "Towards Environment Independent Device Free Human Activity Recognition"

UT-HAR 클래스 → 우리 클래스 매핑:
  0: lie down     → lie_down_slow  (3)
  1: fall         → fall_forward   (0)  ← 방향 정보 없어서 forward 로 통일
  2: walk         → walk           (5)
  3: run          → walk           (5)  ← run은 walk에 근사
  4: sit down     → sit_down       (6)
  5: stand up     → stand_up       (7)
  6: pick up      → stand_up       (7)  ← 유사 동작

사용법:
    cd /home/lee/project
    python data/download_uthar.py --out data/dataset_uthar.npz

    # 다운로드 없이 이미 클론된 경로 지정
    python data/download_uthar.py --repo_dir /tmp/UT-HAR --out data/dataset_uthar.npz
"""

import argparse
import os
import sys
import subprocess
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ml.preprocessing import preprocess_csi_session

UTHAR_REPO = "https://github.com/minestone/UT-HAR.git"
DEFAULT_CLONE_DIR = "/tmp/UT-HAR"

# UT-HAR 클래스 인덱스 → 우리 클래스 인덱스 매핑
OUR_CLASSES = [
    "fall_forward", "fall_side", "fall_backward",
    "lie_down_slow", "lie_down_fast",
    "walk", "sit_down", "stand_up", "static",
]
UTHAR_TO_OURS = {
    0: 3,   # lie down    → lie_down_slow
    1: 0,   # fall        → fall_forward
    2: 5,   # walk        → walk
    3: 5,   # run         → walk
    4: 6,   # sit down    → sit_down
    5: 7,   # stand up    → stand_up
    6: 7,   # pick up     → stand_up
}
UTHAR_CLASS_NAMES = ["lie_down", "fall", "walk", "run", "sit_down", "stand_up", "pick_up"]


def clone_repo(clone_dir: str):
    if os.path.exists(os.path.join(clone_dir, ".git")):
        print(f"이미 클론됨: {clone_dir}")
        return
    print(f"UT-HAR 클론 중: {UTHAR_REPO} → {clone_dir}")
    ret = subprocess.run(
        ["git", "clone", "--depth", "1", UTHAR_REPO, clone_dir],
        capture_output=True, text=True
    )
    if ret.returncode != 0:
        print(f"[오류] git clone 실패:\n{ret.stderr}")
        sys.exit(1)
    print("클론 완료.")


def detect_data_files(repo_dir: str) -> dict[int, str]:
    """
    UT-HAR 레포 구조를 탐색해 클래스별 npy 파일 경로 반환.
    레포 구조 예시:
      data/
        lie_down.npy  또는  0_lie_down.npy  또는  lie down.npy
    """
    data_dir = os.path.join(repo_dir, "data")
    if not os.path.isdir(data_dir):
        data_dir = repo_dir

    print(f"\ndata 디렉토리 내용 ({data_dir}):")
    found = {}
    for fname in sorted(os.listdir(data_dir)):
        fpath = os.path.join(data_dir, fname)
        print(f"  {fname}")
        if not fname.endswith(".npy"):
            continue
        name_lower = fname.lower().replace(" ", "_").replace("-", "_")
        for idx, cls in enumerate(UTHAR_CLASS_NAMES):
            if cls in name_lower:
                found[idx] = fpath
                break
    return found


def load_uthar_npy(fpath: str) -> np.ndarray:
    """
    npy 로드. UT-HAR 데이터 shape 허용:
      (N, T, F)   — 이미 (샘플, 시간, 피처) 형태
      (N, F, T)   — (샘플, 피처, 시간) → transpose
      (N, F*T)    — flat → reshape 시도
    """
    arr = np.load(fpath, allow_pickle=True)
    if arr.dtype == object:
        # 가변 길이 배열인 경우 각 원소를 개별 세션으로 처리
        return arr
    print(f"    shape: {arr.shape}  dtype: {arr.dtype}")
    return arr


def convert_sample(sample: np.ndarray, n_subcarriers: int, window_size: int, stride: int):
    """
    단일 샘플(세션) → 전처리 윈도우 배열.
    sample shape: (timesteps, features) 또는 (features, timesteps) 등 허용.
    """
    if sample.ndim == 1:
        # flat → (timesteps, 1)
        sample = sample[:, np.newaxis]
    elif sample.ndim == 2:
        # (T, F) 또는 (F, T) — T가 더 길면 (T, F)
        if sample.shape[0] < sample.shape[1]:
            sample = sample.T  # (T, F)
    else:
        return None

    sample = sample.astype(np.float32)
    if sample.shape[0] < window_size:
        return None

    try:
        windows = preprocess_csi_session(
            sample,
            n_subcarriers=min(n_subcarriers, sample.shape[1]),
            window_size=window_size,
            stride=stride,
        )
        return windows
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="UT-HAR 다운로드 + 변환")
    parser.add_argument("--out",          default="data/dataset_uthar.npz")
    parser.add_argument("--repo_dir",     default=DEFAULT_CLONE_DIR,
                        help="git clone 대상 (또는 기존 클론 경로)")
    parser.add_argument("--n_subcarriers", type=int, default=30)
    parser.add_argument("--window_size",   type=int, default=100)
    parser.add_argument("--stride",        type=int, default=10)
    parser.add_argument("--no_download",   action="store_true",
                        help="다운로드 건너뜀 (이미 클론 완료 시)")
    args = parser.parse_args()

    if not args.no_download:
        clone_repo(args.repo_dir)

    data_files = detect_data_files(args.repo_dir)
    if not data_files:
        print(f"\n[오류] npy 파일을 찾지 못했습니다. {args.repo_dir} 내 구조를 확인하세요.")
        sys.exit(1)

    print(f"\n발견된 클래스 파일: {len(data_files)}개")
    X_list, y_list = [], []

    for uthar_idx, fpath in sorted(data_files.items()):
        our_idx = UTHAR_TO_OURS.get(uthar_idx)
        if our_idx is None:
            continue
        uthar_name = UTHAR_CLASS_NAMES[uthar_idx]
        our_name   = OUR_CLASSES[our_idx]
        print(f"\n  처리: [{uthar_idx}] {uthar_name} → [{our_idx}] {our_name}")

        data = load_uthar_npy(fpath)

        if data.dtype == object:
            # 가변 길이: 각 원소가 하나의 세션
            sessions = list(data)
        elif data.ndim == 3:
            # (N, T, F) 또는 (N, F, T)
            if data.shape[1] < data.shape[2]:
                data = data.transpose(0, 2, 1)  # → (N, T, F)
            sessions = [data[i] for i in range(len(data))]
        elif data.ndim == 2:
            # (N, T*F) or (N, T) — 단일 세션으로 처리
            sessions = [data]
        else:
            print(f"    [건너뜀] 지원하지 않는 shape: {data.shape}")
            continue

        converted = 0
        for sample in sessions:
            windows = convert_sample(
                np.array(sample, dtype=np.float32),
                n_subcarriers=args.n_subcarriers,
                window_size=args.window_size,
                stride=args.stride,
            )
            if windows is None or len(windows) == 0:
                continue
            X_list.append(windows)
            y_list.extend([our_idx] * len(windows))
            converted += 1

        print(f"    변환 완료: {converted}개 세션")

    if not X_list:
        print("\n변환된 데이터가 없습니다. UT-HAR 레포 구조를 확인하세요.")
        sys.exit(1)

    X = np.concatenate(X_list, axis=0).astype(np.float32)
    y = np.array(y_list, dtype=np.int64)

    perm = np.random.permutation(len(y))
    X, y = X[perm], y[perm]

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    np.savez(args.out, X=X, y=y, classes=OUR_CLASSES)

    print(f"\n저장 완료: {args.out}")
    print(f"  X shape : {X.shape}")
    print(f"  y shape : {y.shape}")
    print("\n클래스별 윈도우 수:")
    for idx, cls in enumerate(OUR_CLASSES):
        n = (y == idx).sum()
        if n > 0:
            print(f"  [{idx}] {cls:<20} {n:>6}개")

    print(f"\n학습 명령:")
    print(f"  python ml/train.py --model cnn_gru --data {args.out} --epochs 30")


if __name__ == "__main__":
    main()
