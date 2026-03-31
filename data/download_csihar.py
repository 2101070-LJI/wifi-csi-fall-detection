"""
CSI-HAR-Dataset 다운로드 + 포맷 변환

출처: https://github.com/Marsrocky/CSI-HAR-Dataset
데이터 형식: .mat 파일 (scipy.io.loadmat) 또는 .npy
서브캐리어: 30개 (Intel 5300 NIC, 3 안테나 × 30 서브캐리어)

CSI-HAR 클래스 → 우리 클래스 매핑:
  0: fall      → fall_forward  (0)  ← 방향 정보 없어 forward로 통일
  1: walk      → walk          (5)
  2: run       → walk          (5)  ← run은 walk에 근사
  3: sit_down  → sit_down      (6)
  4: stand_up  → stand_up      (7)
  5: pick_up   → stand_up      (7)  ← 유사 동작
  6: lie_down  → lie_down_slow (3)

사용법:
    cd /home/lee/project
    python data/download_csihar.py --out data/dataset_csihar.npz

    # 이미 클론된 경우
    python data/download_csihar.py --repo_dir /tmp/CSI-HAR-Dataset --out data/dataset_csihar.npz --no_download
"""

import argparse
import os
import subprocess
import sys

import numpy as np
import scipy.io

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ml.preprocessing import preprocess_csi_session

CSIHAR_REPO      = "https://github.com/Marsrocky/CSI-HAR-Dataset.git"
DEFAULT_CLONE_DIR = "/tmp/CSI-HAR-Dataset"

OUR_CLASSES = [
    "fall_forward", "fall_side", "fall_backward",
    "lie_down_slow", "lie_down_fast",
    "walk", "sit_down", "stand_up", "static",
]

CSIHAR_CLASS_NAMES = ["fall", "walk", "run", "sit_down", "stand_up", "pick_up", "lie_down"]

CSIHAR_TO_OURS = {
    0: 0,   # fall      → fall_forward
    1: 5,   # walk      → walk
    2: 5,   # run       → walk
    3: 6,   # sit_down  → sit_down
    4: 7,   # stand_up  → stand_up
    5: 7,   # pick_up   → stand_up
    6: 3,   # lie_down  → lie_down_slow
}


def clone_repo(clone_dir: str):
    if os.path.exists(os.path.join(clone_dir, ".git")):
        print(f"이미 클론됨: {clone_dir}")
        return
    print(f"CSI-HAR-Dataset 클론 중: {CSIHAR_REPO} → {clone_dir}")
    ret = subprocess.run(
        ["git", "clone", "--depth", "1", CSIHAR_REPO, clone_dir],
        capture_output=True, text=True,
    )
    if ret.returncode != 0:
        print(f"[오류] git clone 실패:\n{ret.stderr}")
        sys.exit(1)
    print("클론 완료.")


def detect_data_files(repo_dir: str) -> dict:
    """
    클래스별 데이터 파일 경로 반환.
    .mat 우선, 없으면 .npy 탐색.
    """
    candidates = [
        repo_dir,
        os.path.join(repo_dir, "data"),
        os.path.join(repo_dir, "Data"),
        os.path.join(repo_dir, "dataset"),
    ]
    data_dir = next((d for d in candidates if os.path.isdir(d) and
                     any(f.endswith((".mat", ".npy")) for f in os.listdir(d))),
                    repo_dir)

    print(f"\n데이터 디렉토리: {data_dir}")
    found = {}
    for fname in sorted(os.listdir(data_dir)):
        if not fname.lower().endswith((".mat", ".npy")):
            continue
        fpath = os.path.join(data_dir, fname)
        name_lower = fname.lower().replace(" ", "_").replace("-", "_")
        for idx, cls in enumerate(CSIHAR_CLASS_NAMES):
            cls_key = cls.replace("_", "")
            name_key = name_lower.replace("_", "")
            if cls_key in name_key:
                found[idx] = fpath
                print(f"  [{idx}] {cls} ← {fname}")
                break
    return found


def load_file(fpath: str) -> np.ndarray:
    """
    .mat 또는 .npy 파일 로드.
    .mat: 배열 키를 자동 탐지.
    반환: ndarray (dtype=float32)
    """
    if fpath.endswith(".npy"):
        return np.load(fpath, allow_pickle=True)

    mat = scipy.io.loadmat(fpath)
    # __ 로 시작하는 메타키 제외, 첫 번째 배열 반환
    keys = [k for k in mat if not k.startswith("_")]
    if not keys:
        raise ValueError(f"mat 파일에서 데이터 키를 찾지 못했습니다: {fpath}")
    data = mat[keys[0]]
    return data.astype(np.float32)


def convert_sample(sample: np.ndarray, n_subcarriers: int, window_size: int, stride: int):
    """
    단일 샘플(세션) → 전처리 윈도우 배열.
    지원 shape: (T, F), (F, T), (T,), flat
    """
    sample = np.array(sample, dtype=np.float32)

    if sample.ndim == 1:
        sample = sample[:, np.newaxis]
    elif sample.ndim == 2:
        # T가 더 긴 축이 시간 축
        if sample.shape[0] < sample.shape[1]:
            sample = sample.T
    else:
        return None

    if sample.shape[0] < window_size:
        return None

    try:
        return preprocess_csi_session(
            sample,
            n_subcarriers=min(n_subcarriers, sample.shape[1]),
            window_size=window_size,
            stride=stride,
        )
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="CSI-HAR-Dataset 다운로드 + 변환")
    parser.add_argument("--out",           default="data/dataset_csihar.npz")
    parser.add_argument("--repo_dir",      default=DEFAULT_CLONE_DIR)
    parser.add_argument("--n_subcarriers", type=int, default=30)
    parser.add_argument("--window_size",   type=int, default=100)
    parser.add_argument("--stride",        type=int, default=10)
    parser.add_argument("--no_download",   action="store_true")
    args = parser.parse_args()

    if not args.no_download:
        clone_repo(args.repo_dir)

    data_files = detect_data_files(args.repo_dir)
    if not data_files:
        print(f"\n[오류] 데이터 파일을 찾지 못했습니다. {args.repo_dir} 내 구조를 확인하세요.")
        sys.exit(1)

    print(f"\n발견된 클래스: {len(data_files)}개")
    X_list, y_list = [], []

    for csihar_idx, fpath in sorted(data_files.items()):
        our_idx = CSIHAR_TO_OURS.get(csihar_idx)
        if our_idx is None:
            continue
        csihar_name = CSIHAR_CLASS_NAMES[csihar_idx]
        our_name    = OUR_CLASSES[our_idx]
        print(f"\n  처리: [{csihar_idx}] {csihar_name} → [{our_idx}] {our_name}")

        try:
            data = load_file(fpath)
        except Exception as e:
            print(f"    [오류] 파일 로드 실패: {e}")
            continue

        print(f"    shape: {data.shape}  dtype: {data.dtype}")

        # 3D (N, T, F) 또는 (N, F, T) → 세션 분리
        if data.ndim == 3:
            if data.shape[1] < data.shape[2]:
                data = data.transpose(0, 2, 1)
            sessions = [data[i] for i in range(len(data))]
        elif data.dtype == object:
            sessions = list(data)
        else:
            sessions = [data]

        converted = 0
        for sample in sessions:
            windows = convert_sample(
                sample,
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
        print("\n변환된 데이터가 없습니다. 레포 구조를 확인하세요.")
        sys.exit(1)

    X = np.concatenate(X_list, axis=0).astype(np.float32)
    y = np.array(y_list, dtype=np.int64)

    perm = np.random.permutation(len(y))
    X, y = X[perm], y[perm]

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    np.savez(args.out, X=X, y=y, classes=OUR_CLASSES)

    print(f"\n저장 완료: {args.out}")
    print(f"  X shape : {X.shape}  (samples, window_size, n_subcarriers)")
    print(f"  y shape : {y.shape}")
    print("\n클래스별 윈도우 수:")
    for idx, cls in enumerate(OUR_CLASSES):
        n = (y == idx).sum()
        if n > 0:
            print(f"  [{idx}] {cls:<20} {n:>6}개")

    print(f"\n미포함 클래스 (직접 수집 필요):")
    for idx, cls in enumerate(OUR_CLASSES):
        if (y == idx).sum() == 0:
            print(f"  [{idx}] {cls}")

    print(f"\n학습 명령:")
    print(f"  python ml/train.py --model cnn_gru --data {args.out} --epochs 50")


if __name__ == "__main__":
    main()
