"""
realtime/cross_validator.py — CSI + 마이크 교차검증

감지 규칙:
    CSI 낙상 O + 충격음 O → 낙상 확정
    CSI 낙상 O + 충격음 X → 오탐 제거 → 무시
    CSI 낙상 X + 충격음 O → 단순 소음 → 무시
"""

import time


class CrossValidator:
    """
    CSI 낙상 이벤트와 마이크 충격음을 시간 윈도우 내에서 교차검증.

    충격음은 CSI 낙상 감지 기준 impact_window_sec 이내에 발생해야 확정.
    """

    def __init__(self, impact_window_sec: float = 1.0, cooldown_sec: float = 5.0):
        """
        Args:
            impact_window_sec: 낙상 감지 시점 기준 이 시간 안에 충격음이 있으면 확정 (초)
            cooldown_sec: 낙상 확정 후 재감지 억제 시간 (초)
        """
        self.impact_window_sec = impact_window_sec
        self.cooldown_sec = cooldown_sec

        self._last_impact_ts: float = 0.0
        self._last_confirmed_ts: float = 0.0

    def notify_impact(self):
        """마이크 충격음 감지 시 호출"""
        self._last_impact_ts = time.time()

    def is_impact_recent(self) -> bool:
        """현재 시각 기준으로 최근 충격음이 impact_window_sec 이내인지 확인"""
        return (time.time() - self._last_impact_ts) <= self.impact_window_sec

    def validate(self, csi_fall: bool) -> bool:
        """
        CSI 추론 결과와 최근 충격음 기록을 교차검증.

        Returns:
            True: 낙상 확정, False: 무시
        """
        if not csi_fall:
            return False

        now = time.time()

        # 쿨다운 중이면 무시
        if now - self._last_confirmed_ts < self.cooldown_sec:
            return False

        if self.is_impact_recent():
            self._last_confirmed_ts = now
            return True

        return False
