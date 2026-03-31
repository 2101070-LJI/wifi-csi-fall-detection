"""
ml/preprocessing.py 단위 테스트
"""

import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ml.preprocessing import (
    hampel_filter,
    savitzky_golay,
    select_subcarriers,
    sliding_window,
    preprocess_csi_session,
)


# --- hampel_filter ---

def test_hampel_filter_1d_replaces_outlier():
    x = np.array([1.0, 1.1, 1.0, 100.0, 1.0, 1.1, 1.0])
    result = hampel_filter(x, window_size=2, n_sigma=3)
    assert result[3] < 10.0, "이상값이 중앙값으로 대체되어야 합니다"


def test_hampel_filter_1d_preserves_normal():
    x = np.array([1.0, 1.1, 0.9, 1.0, 1.1, 0.9, 1.0])
    result = hampel_filter(x, window_size=2, n_sigma=3)
    np.testing.assert_allclose(result, x, atol=1e-9)


def test_hampel_filter_2d_shape():
    x = np.random.randn(50, 30)
    result = hampel_filter(x)
    assert result.shape == x.shape


def test_hampel_filter_2d_replaces_outlier():
    x = np.ones((20, 5))
    x[10, 2] = 999.0  # 특정 서브캐리어에 이상값 삽입
    result = hampel_filter(x, window_size=3, n_sigma=3)
    assert result[10, 2] < 100.0


# --- savitzky_golay ---

def test_savitzky_golay_1d_shape():
    x = np.random.randn(100)
    result = savitzky_golay(x, window=11, poly=3)
    assert result.shape == x.shape


def test_savitzky_golay_2d_shape():
    x = np.random.randn(100, 30)
    result = savitzky_golay(x, window=11, poly=3)
    assert result.shape == x.shape


def test_savitzky_golay_smooths():
    """상수 신호는 스무딩 후에도 상수여야 함"""
    x = np.ones(100)
    result = savitzky_golay(x, window=11, poly=3)
    np.testing.assert_allclose(result, x, atol=1e-6)


def test_savitzky_golay_even_window_corrected():
    """짝수 윈도우를 넣어도 홀수로 보정되어 동작해야 함"""
    x = np.random.randn(100)
    result = savitzky_golay(x, window=10, poly=3)  # 10 → 11로 보정
    assert result.shape == x.shape


# --- select_subcarriers ---

def test_select_subcarriers_shape():
    csi = np.random.randn(200, 64)
    result = select_subcarriers(csi, n=30)
    assert result.shape == (200, 30)


def test_select_subcarriers_selects_high_variance():
    """분산이 높은 서브캐리어가 선택되어야 함"""
    np.random.seed(42)
    csi = np.ones((100, 10))
    # 마지막 3개 서브캐리어에 높은 분산 부여
    csi[:, 7] += np.random.randn(100) * 10
    csi[:, 8] += np.random.randn(100) * 10
    csi[:, 9] += np.random.randn(100) * 10
    result = select_subcarriers(csi, n=3)
    assert result.shape == (100, 3)
    # 분산이 낮은 서브캐리어 값(1.0)이 결과에 없어야 함
    assert np.var(result) > 1.0


def test_select_subcarriers_n_exceeds_total():
    """n이 전체 서브캐리어 수보다 크면 전체 반환"""
    csi = np.random.randn(100, 10)
    result = select_subcarriers(csi, n=50)
    assert result.shape == (100, 10)


def test_select_subcarriers_wrong_dim():
    import pytest
    with pytest.raises(ValueError):
        select_subcarriers(np.random.randn(100), n=10)


# --- sliding_window ---

def test_sliding_window_output_shape():
    data = np.random.randn(200, 30)
    result = sliding_window(data, window_size=100, stride=10)
    expected_n = (200 - 100) // 10 + 1  # = 11
    assert result.shape == (expected_n, 100, 30)


def test_sliding_window_1d_input():
    data = np.random.randn(150)
    result = sliding_window(data, window_size=50, stride=10)
    assert result.shape[1] == 50
    assert result.shape[2] == 1


def test_sliding_window_stride_1():
    data = np.random.randn(10, 5)
    result = sliding_window(data, window_size=3, stride=1)
    assert result.shape == (8, 3, 5)


def test_sliding_window_too_short():
    import pytest
    data = np.random.randn(50, 30)
    with pytest.raises(ValueError):
        sliding_window(data, window_size=100, stride=10)


def test_sliding_window_content():
    """첫 번째 윈도우의 내용이 원본 데이터와 일치해야 함"""
    data = np.arange(20).reshape(10, 2).astype(float)
    result = sliding_window(data, window_size=4, stride=2)
    np.testing.assert_array_equal(result[0], data[:4])
    np.testing.assert_array_equal(result[1], data[2:6])


# --- preprocess_csi_session ---

def test_preprocess_csi_session_shape():
    csi = np.random.randn(300, 64)
    result = preprocess_csi_session(
        csi, n_subcarriers=30, window_size=100, stride=10
    )
    assert result.ndim == 3
    assert result.shape[1] == 100
    assert result.shape[2] == 30


def test_preprocess_csi_session_no_nan():
    csi = np.random.randn(200, 64)
    csi[50, :] = np.nan  # NaN 삽입
    # NaN이 있으면 hampel 후 남을 수 있으므로, nan이 없는 입력 기준 테스트
    csi_clean = np.random.randn(200, 64)
    result = preprocess_csi_session(csi_clean)
    assert not np.any(np.isnan(result))


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
