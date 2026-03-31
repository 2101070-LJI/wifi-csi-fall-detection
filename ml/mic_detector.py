"""
마이크 충격음 감지기 — 낙상 교차검증용
임계값 기반 RMS 진폭 분석
"""

import numpy as np
from collections import deque
from typing import Optional


class ImpactDetector:
    """
    실시간 오디오 버퍼에서 충격음(낙상 충격)을 감지.

    감지 알고리즘:
    1. 입력 오디오 버퍼의 RMS 계산
    2. 배경 소음 수준(rolling baseline) 동적 추정
    3. RMS가 baseline * threshold_ratio를 초과하면 충격음으로 판단
    4. window_ms 이내에 재발 방지 (쿨다운)
    """

    def __init__(
        self,
        threshold: float = 0.5,
        window_ms: int = 200,
        sample_rate: int = 16000,
        baseline_alpha: float = 0.995,
        min_baseline: float = 0.01,
    ):
        """
        Args:
            threshold: RMS가 baseline * (1 + threshold)를 초과하면 감지
            window_ms: 충격음 감지 후 쿨다운 시간 (ms)
            sample_rate: 오디오 샘플레이트 (Hz)
            baseline_alpha: 배경 소음 EMA 평활 계수 (0~1, 1에 가까울수록 느리게 갱신)
            min_baseline: 배경 소음 최소값 (0 나누기 방지)
        """
        self.threshold = threshold
        self.cooldown_samples = int(sample_rate * window_ms / 1000)
        self.sample_rate = sample_rate
        self.baseline_alpha = baseline_alpha
        self.min_baseline = min_baseline

        self._baseline: float = min_baseline
        self._cooldown_remaining: int = 0

    def reset(self):
        """상태 초기화 (새 세션 시작 시 호출)"""
        self._baseline = self.min_baseline
        self._cooldown_remaining = 0

    def detect(self, audio_buffer: np.ndarray) -> bool:
        """
        오디오 버퍼를 분석하여 충격음 여부 반환.

        Args:
            audio_buffer: 1D float32 ndarray (오디오 샘플)

        Returns:
            True: 충격음 감지됨, False: 미감지
        """
        if len(audio_buffer) == 0:
            return False

        rms = float(np.sqrt(np.mean(audio_buffer.astype(np.float64) ** 2)))
        n_samples = len(audio_buffer)

        # 쿨다운 처리
        if self._cooldown_remaining > 0:
            self._cooldown_remaining = max(0, self._cooldown_remaining - n_samples)
            self._update_baseline(rms)
            return False

        # 감지 판단
        trigger_level = self._baseline * (1.0 + self.threshold)
        detected = rms > max(trigger_level, self.min_baseline * (1.0 + self.threshold))

        if detected:
            self._cooldown_remaining = self.cooldown_samples
        else:
            self._update_baseline(rms)

        return detected

    def _update_baseline(self, rms: float):
        """EMA로 배경 소음 수준 갱신 (충격음 감지 시에는 갱신 안 함)"""
        self._baseline = (
            self.baseline_alpha * self._baseline + (1.0 - self.baseline_alpha) * rms
        )
        self._baseline = max(self._baseline, self.min_baseline)

    @property
    def baseline(self) -> float:
        return self._baseline

    @property
    def in_cooldown(self) -> bool:
        return self._cooldown_remaining > 0
