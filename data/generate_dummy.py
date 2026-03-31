"""
하드웨어 없이 즉시 파이프라인 검증용 합성 CSI 데이터 생성기

실제 낙상 CSI 특성을 모방한 신호 패턴:
  - fall_*     : 급격한 진폭 스파이크 + 빠른 감쇠
  - lie_down_* : 느린 진폭 변화
  - walk       : 주기적 진폭 변화 (보행 주기 ~1Hz)
  - sit_down   : 중간 속도 진폭 하강
  - stand_up   : 중간 속도 진폭 상승
  - static     : 낮은 진폭 + 소량 노이즈

사용법:
    cd /home/lee/project
    python data/generate_dummy.py --out data/dataset.npz
    python data/generate_dummy.py --out data/dataset.npz --sessions_per_class 200
"""

import argparse
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ml.preprocessing import preprocess_csi_session

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

# 시뮬레이션 파라미터: (기저 진폭, 스파이크 계수, 주파수, 감쇠)
_SIM_PARAMS = {
    "fall_forward":  dict(base=0.3, spike=3.0, freq=0.0, decay=0.8,  noise=0.05),
    "fall_side":     dict(base=0.3, spike=2.5, freq=0.0, decay=0.7,  noise=0.05),
    "fall_backward": dict(base=0.3, spike=2.8, freq=0.0, decay=0.75, noise=0.05),
    "lie_down_slow": dict(base=0.2, spike=0.8, freq=0.1, decay=0.02, noise=0.03),
    "lie_down_fast": dict(base=0.2, spike=1.5, freq=0.3, decay=0.1,  noise=0.04),
    "walk":          dict(base=0.4, spike=0.6, freq=1.2, decay=0.0,  noise=0.06),
    "sit_down":      dict(base=0.5, spike=0.9, freq=0.2, decay=0.05, noise=0.04),
    "stand_up":      dict(base=0.3, spike=0.9, freq=0.2, decay=0.05, noise=0.04),
    "static":        dict(base=0.1, spike=0.0, freq=0.0, decay=0.0,  noise=0.02),
}

N_SUBCARRIERS_RAW = 64   # 생성 시 서브캐리어 수 (전처리에서 30개로 줄어듦)
TIMESTEPS         = 300  # 세션당 타임스텝


def generate_session(label: str, rng: np.random.Generator) -> np.ndarray:
    """
    label에 맞는 CSI 진폭 시계열 생성.
    반환: (TIMESTEPS, N_SUBCARRIERS_RAW) float32
    """
    p = _SIM_PARAMS[label]
    t = np.linspace(0, 3.0, TIMESTEPS)  # 3초

    # 서브캐리어별 약간의 개성 부여
    offsets = rng.uniform(-0.1, 0.1, N_SUBCARRIERS_RAW)
    freqs   = rng.uniform(0.9, 1.1, N_SUBCARRIERS_RAW) * p["freq"]

    # 기저 신호
    base = p["base"] + offsets[np.newaxis, :]                 # (1, SC)
    # 주기 성분
    periodic = p["spike"] * 0.3 * np.sin(2 * np.pi * freqs[np.newaxis, :] * t[:, np.newaxis])
    # 스파이크 (낙상/동작 충격)
    spike_t  = rng.uniform(0.5, 1.5)  # 스파이크 위치
    spike_env = p["spike"] * np.exp(-p["decay"] * np.abs(t - spike_t) * 10 + 1e-6)
    spike_env = spike_env[:, np.newaxis] * rng.uniform(0.8, 1.2, N_SUBCARRIERS_RAW)[np.newaxis, :]
    # 노이즈
    noise = rng.normal(0, p["noise"], (TIMESTEPS, N_SUBCARRIERS_RAW))

    signal = base + periodic + spike_env + noise
    signal = np.clip(signal, 0, None).astype(np.float32)
    return signal


def main():
    parser = argparse.ArgumentParser(description="더미 CSI 데이터셋 생성")
    parser.add_argument("--out",                default="data/dataset.npz")
    parser.add_argument("--sessions_per_class", type=int, default=120,
                        help="클래스당 세션 수 (기본 120)")
    parser.add_argument("--n_subcarriers",      type=int, default=30)
    parser.add_argument("--window_size",        type=int, default=100)
    parser.add_argument("--stride",             type=int, default=10)
    parser.add_argument("--seed",               type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    X_list, y_list = [], []

    print(f"더미 데이터 생성 중 (클래스당 {args.sessions_per_class}세션)...")
    for cls_idx, label in enumerate(CLASSES):
        n_win = 0
        for _ in range(args.sessions_per_class):
            session = generate_session(label, rng)
            try:
                windows = preprocess_csi_session(
                    session,
                    n_subcarriers=args.n_subcarriers,
                    window_size=args.window_size,
                    stride=args.stride,
                )
            except Exception:
                continue
            X_list.append(windows)
            y_list.extend([cls_idx] * len(windows))
            n_win += len(windows)
        print(f"  [{cls_idx}] {label:<20} {args.sessions_per_class}세션 → {n_win}개 윈도우")

    X = np.concatenate(X_list, axis=0).astype(np.float32)
    y = np.array(y_list, dtype=np.int64)

    perm = rng.permutation(len(y))
    X, y = X[perm], y[perm]

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    np.savez(args.out, X=X, y=y, classes=CLASSES)

    print(f"\n저장 완료: {args.out}")
    print(f"  X shape : {X.shape}  (samples, window_size, n_features)")
    print(f"  y shape : {y.shape}")
    print(f"\n학습 실행:")
    print(f"  python ml/train.py --model cnn_gru --data {args.out} --epochs 30")
    print(f"  python ml/train.py --model cnn_lstm --data {args.out} --epochs 30")
    print(f"\n전체 모델 비교:")
    print(f"  for m in cnn_lstm blstm cnn_gru attention_blstm transformer resnet1d; do")
    print(f"    python ml/train.py --model $m --data {args.out} --epochs 30")
    print(f"  done")
    print(f"  python ml/evaluate.py --compare --data {args.out}")


if __name__ == "__main__":
    main()
