import numpy as np
import pandas as pd
from scipy.signal import savgol_filter


def hampel_filter(data: np.ndarray, window_size: int = 5, n_sigma: float = 3.0) -> np.ndarray:
    """행=타임스텝, 열=서브캐리어. 각 열에 Hampel 필터 적용 (pandas rolling 벡터화)."""
    out = data.copy()
    for c in range(data.shape[1]):
        col = data[:, c]
        s = pd.Series(col)
        med = s.rolling(window_size, center=True, min_periods=1).median().values
        mad = pd.Series(np.abs(col - med)).rolling(window_size, center=True, min_periods=1).median().values
        threshold = n_sigma * 1.4826 * (mad + 1e-10)
        mask = np.abs(col - med) > threshold
        out[mask, c] = med[mask]
    return out


def savitzky_golay(data: np.ndarray, window: int = 11, poly: int = 3) -> np.ndarray:
    """각 서브캐리어 열에 Savitzky-Golay 스무딩 적용."""
    out = np.zeros_like(data)
    for c in range(data.shape[1]):
        out[:, c] = savgol_filter(data[:, c], window_length=window, polyorder=poly)
    return out


def select_subcarriers(data: np.ndarray, n: int = 30) -> np.ndarray:
    """분산이 가장 큰 n개의 서브캐리어 선택."""
    variances = np.var(data, axis=0)
    indices = np.argsort(variances)[-n:]
    indices = np.sort(indices)
    return data[:, indices]


def sliding_window(data: np.ndarray, win_size: int = 100, stride: int = 10) -> np.ndarray:
    """(T, C) → (N_windows, win_size, C)"""
    T, C = data.shape
    windows = []
    for start in range(0, T - win_size + 1, stride):
        windows.append(data[start:start + win_size])
    return np.stack(windows, axis=0) if windows else np.empty((0, win_size, C), dtype=data.dtype)


def normalize_window(windows: np.ndarray) -> np.ndarray:
    """(N, win_size, C) 각 윈도우를 [0, 1]로 MinMax 정규화."""
    out = windows.copy()
    for i in range(len(out)):
        mn = out[i].min()
        mx = out[i].max()
        if mx - mn > 1e-8:
            out[i] = (out[i] - mn) / (mx - mn)
    return out
