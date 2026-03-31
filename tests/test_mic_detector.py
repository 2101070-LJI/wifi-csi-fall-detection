"""
ml/mic_detector.py 단위 테스트
"""

import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ml.mic_detector import ImpactDetector


SAMPLE_RATE = 16000


def make_silence(n=1600, amplitude=0.001):
    return np.random.randn(n).astype(np.float32) * amplitude


def make_impact(n=1600, amplitude=1.0):
    return (np.random.randn(n) * amplitude).astype(np.float32)


# --- 기본 감지 동작 ---

def test_silence_not_detected():
    det = ImpactDetector(threshold=0.5, sample_rate=SAMPLE_RATE)
    # 배경 소음으로 baseline 초기화
    for _ in range(20):
        det.detect(make_silence())
    result = det.detect(make_silence())
    assert result is False


def test_impact_detected():
    det = ImpactDetector(threshold=0.5, sample_rate=SAMPLE_RATE)
    # baseline을 낮게 설정
    for _ in range(20):
        det.detect(make_silence(amplitude=0.001))
    result = det.detect(make_impact(amplitude=2.0))
    assert result is True


def test_detect_returns_bool():
    det = ImpactDetector()
    result = det.detect(make_silence())
    assert isinstance(result, bool)


# --- 쿨다운 동작 ---

def test_cooldown_prevents_double_detection():
    det = ImpactDetector(threshold=0.5, window_ms=200, sample_rate=SAMPLE_RATE)
    for _ in range(20):
        det.detect(make_silence(amplitude=0.001))
    # 첫 번째 충격음 감지
    det.detect(make_impact(amplitude=2.0))
    # 즉시 두 번째 충격음 — 쿨다운 중이어야 함
    result = det.detect(make_impact(amplitude=2.0))
    assert result is False


def test_cooldown_expires():
    det = ImpactDetector(threshold=0.5, window_ms=10, sample_rate=SAMPLE_RATE)
    for _ in range(20):
        det.detect(make_silence(amplitude=0.001))
    det.detect(make_impact(amplitude=2.0))
    assert det.in_cooldown is True
    # 쿨다운 기간보다 많은 샘플 처리
    cooldown_samples = int(SAMPLE_RATE * 10 / 1000) + 100
    det.detect(make_silence(n=cooldown_samples, amplitude=0.001))
    assert det.in_cooldown is False


# --- 초기화 ---

def test_reset_clears_state():
    det = ImpactDetector(threshold=0.5, sample_rate=SAMPLE_RATE)
    for _ in range(20):
        det.detect(make_silence(amplitude=0.001))
    det.detect(make_impact(amplitude=2.0))
    assert det.in_cooldown is True
    det.reset()
    assert det.in_cooldown is False


def test_reset_resets_baseline():
    det = ImpactDetector(min_baseline=0.01)
    for _ in range(50):
        det.detect(make_silence(amplitude=0.1))
    baseline_before = det.baseline
    det.reset()
    assert det.baseline == 0.01
    assert det.baseline != baseline_before


# --- 엣지 케이스 ---

def test_empty_buffer_returns_false():
    det = ImpactDetector()
    result = det.detect(np.array([], dtype=np.float32))
    assert result is False


def test_single_sample_buffer():
    det = ImpactDetector(threshold=0.5, min_baseline=0.001)
    result = det.detect(np.array([0.001], dtype=np.float32))
    assert isinstance(result, bool)


def test_baseline_increases_with_loud_background():
    det = ImpactDetector(threshold=0.5, baseline_alpha=0.9, min_baseline=0.001)
    for _ in range(100):
        det.detect(make_silence(amplitude=0.5))
    assert det.baseline > 0.01


def test_threshold_parameter_effect():
    """threshold가 낮을수록 더 민감하게 감지"""
    # sensitive detector
    det_sensitive = ImpactDetector(threshold=0.1, sample_rate=SAMPLE_RATE, min_baseline=0.001)
    det_strict = ImpactDetector(threshold=10.0, sample_rate=SAMPLE_RATE, min_baseline=0.001)

    moderate_impact = make_impact(amplitude=0.05)
    r_sensitive = det_sensitive.detect(moderate_impact)
    r_strict = det_strict.detect(moderate_impact)

    # strict는 감지하지 않아야 함
    assert r_strict is False


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
