"""
CSI 데이터 전처리 파이프라인
- Hampel 필터 (이상값 제거)
- Savitzky-Golay 스무딩
- 서브캐리어 선택
- 슬라이딩 윈도우
- MinMax 정규화 (윈도우 단위)
"""

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter


def hampel_filter(data: np.ndarray, window_size: int = 5, n_sigma: float = 3.0) -> np.ndarray:
    """
    Hampel 필터 — pandas rolling median 기반 이상값 제거.

    Args:
        data: 2D ndarray (timesteps, subcarriers)
        window_size: rolling 윈도우 크기
        n_sigma: 이상값 판단 임계 배수 (MAD 기준)

    Returns:
        이상값이 대체된 ndarray (입력과 동일한 shape)
    """
    out = data.copy().astype(np.float32)
    for c in range(data.shape[1]):
        col = data[:, c].astype(np.float64)
        s = pd.Series(col)
        med = s.rolling(window_size, center=True, min_periods=1).median().values
        mad = pd.Series(np.abs(col - med)).rolling(window_size, center=True, min_periods=1).median().values
        threshold = n_sigma * 1.4826 * (mad + 1e-10)
        mask = np.abs(col - med) > threshold
        out[mask, c] = med[mask]
    return out


def savitzky_golay(data: np.ndarray, window: int = 11, poly: int = 3) -> np.ndarray:
    """
    Savitzky-Golay 스무딩 필터.

    Args:
        data: 2D ndarray (timesteps, subcarriers)
        window: 윈도우 길이 (홀수, >= poly+2)
        poly: 다항식 차수

    Returns:
        스무딩된 ndarray
    """
    if window % 2 == 0:
        window += 1
    out = np.zeros_like(data, dtype=np.float32)
    for c in range(data.shape[1]):
        out[:, c] = savgol_filter(data[:, c].astype(float), window_length=window, polyorder=poly)
    return out


def select_subcarriers(csi: np.ndarray, n: int = 30) -> np.ndarray:
    """
    분산이 높은 서브캐리어 n개 선택.

    Args:
        csi: 2D ndarray (timesteps, subcarriers)
        n: 선택할 서브캐리어 수

    Returns:
        (timesteps, n) ndarray
    """
    if csi.ndim != 2:
        raise ValueError(f"csi는 2D 배열이어야 합니다. 현재 shape: {csi.shape}")
    n = min(n, csi.shape[1])
    variances = np.var(csi, axis=0)
    indices = np.sort(np.argsort(variances)[-n:])
    return csi[:, indices]


def sliding_window(
    data: np.ndarray,
    window_size: int = 100,
    stride: int = 10,
) -> np.ndarray:
    """
    슬라이딩 윈도우로 시계열 데이터를 샘플 배열로 변환.

    Args:
        data: 2D ndarray (timesteps, features)
        window_size: 윈도우 크기 (타임스텝 수)
        stride: 슬라이딩 간격

    Returns:
        3D ndarray (n_windows, window_size, features)
    """
    if data.ndim == 1:
        data = data[:, np.newaxis]
    T, C = data.shape
    if T < window_size:
        raise ValueError(f"데이터 길이({T})가 window_size({window_size})보다 짧습니다.")
    windows = []
    for start in range(0, T - window_size + 1, stride):
        windows.append(data[start : start + window_size])
    return np.stack(windows, axis=0) if windows else np.empty((0, window_size, C), dtype=data.dtype)


def normalize_window(windows: np.ndarray) -> np.ndarray:
    """
    윈도우 단위 MinMax 정규화 → [0, 1].

    Args:
        windows: 3D ndarray (n_windows, window_size, features)

    Returns:
        정규화된 ndarray (동일 shape)
    """
    out = windows.copy().astype(np.float32)
    for i in range(len(out)):
        mn = out[i].min()
        mx = out[i].max()
        if mx - mn > 1e-8:
            out[i] = (out[i] - mn) / (mx - mn)
    return out


def preprocess_csi_session(
    csi: np.ndarray,
    n_subcarriers: int = 30,
    window_size: int = 100,
    stride: int = 10,
    hampel_window: int = 5,
    hampel_sigma: float = 3.0,
    sg_window: int = 11,
    sg_poly: int = 3,
) -> np.ndarray:
    """
    단일 수집 세션 CSI 데이터에 전체 전처리 파이프라인 적용.

    순서: Hampel → Savitzky-Golay → 서브캐리어 선택 → 슬라이딩 윈도우 → MinMax 정규화

    Args:
        csi: (timesteps, all_subcarriers) ndarray

    Returns:
        (n_windows, window_size, n_subcarriers) ndarray, float32, [0, 1] 정규화됨
    """
    csi = hampel_filter(csi, window_size=hampel_window, n_sigma=hampel_sigma)
    csi = savitzky_golay(csi, window=sg_window, poly=sg_poly)
    csi = select_subcarriers(csi, n=n_subcarriers)
    windows = sliding_window(csi, window_size=window_size, stride=stride)
    windows = normalize_window(windows)
    return windows
