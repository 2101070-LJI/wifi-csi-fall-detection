"""
tests/test_integration.py — 전체 파이프라인 통합 테스트 (Task 6-2)

커버 범위:
    1. CrossValidator 시나리오 (낙상 확정 / 오탐 제거 / 단순 소음 / 쿨다운)
    2. CSIInferencer 전처리 파이프라인 (mock 모델)
    3. EventLogger mock DB
    4. FastAPI 엔드포인트 전체 (TestClient + mock api.db)
    5. 전체 파이프라인 통합: 오탐률 / 미탐률 측정

실행:
    python -m pytest tests/test_integration.py -v
"""

import sys
import os
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# mysql.connector가 없는 환경(개발 PC)에서도 테스트 가능하도록 stub 등록
if "mysql" not in sys.modules:
    _mysql_stub = MagicMock()
    sys.modules["mysql"] = _mysql_stub
    sys.modules["mysql.connector"] = _mysql_stub.connector

from realtime.cross_validator import CrossValidator
from ml.models.cnn_gru import CNNGRU
from realtime.csi_inference import CSIInferencer, CLASSES, FALL_CLASS_INDICES


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CrossValidator — 3가지 시나리오
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrossValidatorScenarios:
    """
    감지 규칙:
        CSI fall O + 충격음 O  →  낙상 확정 (confirmed=True)
        CSI fall O + 충격음 X  →  오탐 제거 (confirmed=False)
        CSI fall X + 충격음 O  →  단순 소음 (confirmed=False)
    """

    def test_fall_confirmed_with_impact(self):
        """시나리오 1: 낙상 확정 — CSI fall + 충격음 O"""
        cv = CrossValidator(impact_window_sec=1.0, cooldown_sec=5.0)
        cv.notify_impact()                          # 충격음 기록
        result = cv.validate(csi_fall=True)
        assert result is True, "CSI fall + 충격음 → 낙상 확정이어야 합니다"

    def test_false_positive_removed_no_impact(self):
        """시나리오 2: 오탐 제거 — CSI fall O + 충격음 X"""
        cv = CrossValidator(impact_window_sec=1.0, cooldown_sec=5.0)
        # notify_impact() 호출 없음 → 충격음 없음
        result = cv.validate(csi_fall=True)
        assert result is False, "충격음 없이 CSI fall만 → 오탐 제거이어야 합니다"

    def test_noise_only_not_confirmed(self):
        """시나리오 3: 단순 소음 — CSI fall X + 충격음 O"""
        cv = CrossValidator(impact_window_sec=1.0, cooldown_sec=5.0)
        cv.notify_impact()                          # 충격음 있음
        result = cv.validate(csi_fall=False)
        assert result is False, "CSI fall 없이 충격음만 → 단순 소음이어야 합니다"

    def test_impact_expired_before_validate(self):
        """충격음이 impact_window_sec 이후에 발생 → 오탐 제거"""
        cv = CrossValidator(impact_window_sec=0.05, cooldown_sec=5.0)
        cv.notify_impact()
        time.sleep(0.1)                             # window 만료
        result = cv.validate(csi_fall=True)
        assert result is False, "만료된 충격음 → 오탐 제거이어야 합니다"

    def test_cooldown_prevents_double_confirmation(self):
        """낙상 확정 직후 재감지 → 쿨다운으로 무시"""
        cv = CrossValidator(impact_window_sec=1.0, cooldown_sec=5.0)
        cv.notify_impact()
        first = cv.validate(csi_fall=True)
        assert first is True

        cv.notify_impact()
        second = cv.validate(csi_fall=True)
        assert second is False, "쿨다운 중 재확정 → 무시이어야 합니다"

    def test_cooldown_expires_and_redetects(self):
        """쿨다운 만료 후 재감지 가능"""
        cv = CrossValidator(impact_window_sec=1.0, cooldown_sec=0.05)
        cv.notify_impact()
        cv.validate(csi_fall=True)              # 첫 확정
        time.sleep(0.1)                         # 쿨다운 만료
        cv.notify_impact()
        result = cv.validate(csi_fall=True)
        assert result is True, "쿨다운 만료 후 재확정 가능해야 합니다"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CSIInferencer — 전처리 파이프라인 (mock 모델)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCSIInferencerPipeline:
    """모델 가중치 없이 전처리 + 추론 흐름을 mock으로 검증"""

    def _make_inferencer_with_mock_model(self, pred_class: int = 1) -> CSIInferencer:
        """pred_class를 항상 반환하는 mock 모델을 주입한 CSIInferencer"""
        inferencer = CSIInferencer.__new__(CSIInferencer)
        inferencer.model_path  = "mock"
        inferencer.model_name  = "cnn_gru"
        inferencer.n_subcarriers = 30
        inferencer.window_size = 100
        inferencer.stride      = 10
        inferencer.n_classes   = 7
        inferencer.device      = torch.device("cpu")

        from collections import deque
        inferencer._buffer       = deque(maxlen=100)
        inferencer._step_counter = 0

        # mock 모델: 항상 pred_class 클래스 확률 1.0
        mock_model = MagicMock()
        logits = torch.zeros(1, 7)
        logits[0, pred_class] = 10.0           # softmax 후 해당 클래스 ≈ 1.0
        mock_model.return_value = logits
        mock_model.eval = MagicMock()
        inferencer._model = mock_model

        return inferencer

    def test_push_returns_none_before_buffer_full(self):
        """버퍼가 채워지기 전에는 None 반환"""
        inf = self._make_inferencer_with_mock_model()
        amp = np.random.randn(64).astype(np.float32)
        for _ in range(99):
            result = inf.push(amp)
        assert result is None

    def test_push_returns_result_after_buffer_full(self):
        """버퍼 100개 채워지면 추론 결과 반환"""
        inf = self._make_inferencer_with_mock_model(pred_class=1)  # fall
        amp = np.random.randn(64).astype(np.float32)
        result = None
        for _ in range(100):
            result = inf.push(amp)
        # stride=10이므로 100번째(step_counter=100)에서 추론
        assert result is not None
        class_idx, confidence, is_fall = result
        assert class_idx == 1
        assert confidence > 0.99
        assert is_fall is True

    def test_push_stride_triggers_inference(self):
        """stride(10)마다 추론, 그 외는 None"""
        inf = self._make_inferencer_with_mock_model(pred_class=3)  # run
        amp = np.random.randn(64).astype(np.float32)
        results = [inf.push(amp) for _ in range(120)]
        not_none = [r for r in results if r is not None]
        # 100~120 구간: step 100, 110, 120 → 3회
        assert len(not_none) == 3

    def test_non_fall_class_is_fall_false(self):
        """fall 클래스가 아닌 경우 is_fall=False"""
        for cls in [0, 2, 3, 4, 5, 6]:  # bend, lie down, run, sitdown, standup, walk
            inf = self._make_inferencer_with_mock_model(pred_class=cls)
            amp = np.random.randn(64).astype(np.float32)
            for _ in range(100):
                result = inf.push(amp)
            if result is not None:
                _, _, is_fall = result
                assert is_fall is False, f"클래스 {cls}는 fall이 아니어야 합니다"

    def test_class_name_mapping(self):
        """클래스 인덱스 → 이름 매핑"""
        assert CSIInferencer.class_name(0) == "bend"
        assert CSIInferencer.class_name(1) == "fall"
        assert CSIInferencer.class_name(2) == "lie down"
        assert CSIInferencer.class_name(6) == "walk"
        assert CSIInferencer.class_name(99) == "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. EventLogger — mock DB
# ═══════════════════════════════════════════════════════════════════════════════

class TestEventLogger:
    """mysql.connector를 mock으로 대체하여 DB 없이 테스트"""

    def _make_mock_conn(self):
        mock_cur = MagicMock()
        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True
        mock_conn.cursor.return_value = mock_cur
        return mock_conn, mock_cur

    def test_log_confirmed_event(self):
        """낙상 확정 이벤트 DB 저장 호출 검증"""
        from realtime.event_logger import EventLogger

        el = EventLogger(model_version="cnn_gru_test")
        mock_conn, mock_cur = self._make_mock_conn()
        el._conn = mock_conn

        el.log(csi_confidence=0.97, impact_detected=True, confirmed=True)

        mock_cur.execute.assert_called_once()
        args = mock_cur.execute.call_args[0]
        params = args[1]
        assert params[0] == pytest.approx(0.97)
        assert params[1] == 1   # impact_detected=True → 1
        assert params[2] == 1   # confirmed=True → 1
        assert params[3] == "cnn_gru_test"

    def test_log_false_positive_event(self):
        """오탐(confirmed=False) 이벤트 저장"""
        from realtime.event_logger import EventLogger

        el = EventLogger(model_version="cnn_gru_test")
        mock_conn, mock_cur = self._make_mock_conn()
        el._conn = mock_conn

        el.log(csi_confidence=0.91, impact_detected=False, confirmed=False)

        params = mock_cur.execute.call_args[0][1]
        assert params[1] == 0   # impact_detected=False → 0
        assert params[2] == 0   # confirmed=False → 0

    def test_log_reconnects_on_disconnection(self):
        """DB 연결 끊김 시 자동 재연결"""
        from realtime.event_logger import EventLogger

        el = EventLogger()
        mock_conn, mock_cur = self._make_mock_conn()
        mock_conn.is_connected.return_value = False  # 연결 끊김 상태

        with patch("realtime.event_logger.mysql.connector.connect") as mock_connect:
            mock_connect.return_value = mock_conn
            mock_conn.is_connected.return_value = True  # 재연결 후 복구
            el._conn = mock_conn
            el.log(csi_confidence=0.85, impact_detected=True, confirmed=True)
            # 재연결 시도 또는 기존 연결 사용 — 예외 없이 완료되어야 함

    def test_log_handles_db_error_gracefully(self):
        """DB 오류 시 예외가 외부로 전파되지 않아야 함"""
        from realtime.event_logger import EventLogger

        el = EventLogger()
        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True
        mock_conn.cursor.side_effect = Exception("DB Error")
        el._conn = mock_conn

        # 예외가 전파되지 않아야 함
        el.log(csi_confidence=0.9, impact_detected=True, confirmed=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. FastAPI 엔드포인트 — TestClient + mock DB
# ═══════════════════════════════════════════════════════════════════════════════

class TestFastAPIEndpoints:
    """api.db를 mock으로 대체하여 DB 없이 FastAPI 엔드포인트 검증"""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from api.main import app
        return TestClient(app)

    # ── /status ──────────────────────────────────────────────────────────────

    def test_status_with_events(self, client):
        last_event = {
            "detected_at": "2026-03-25T14:30:00",
            "csi_confidence": 0.97,
            "impact_detected": 1,
            "confirmed": 1,
            "model_version": "cnn_gru_v1",
        }
        with patch("api.routers.status.query_one") as mock_qone:
            mock_qone.side_effect = [last_event, {"cnt": 3}]
            resp = client.get("/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is True
        assert data["confirmed_total"] == 3
        assert data["last_event"]["csi_confidence"] == pytest.approx(0.97)

    def test_status_empty_db(self, client):
        with patch("api.routers.status.query_one") as mock_qone:
            mock_qone.return_value = None
            resp = client.get("/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is True
        assert data["confirmed_total"] == 0
        assert data["last_event"] is None

    # ── /events ──────────────────────────────────────────────────────────────

    def test_events_returns_list(self, client):
        fake_events = [
            {"id": 1, "detected_at": "2026-03-25T10:00:00",
             "csi_confidence": 0.95, "impact_detected": 1,
             "confirmed": 1, "model_version": "cnn_gru_v1"},
        ]
        with patch("api.routers.events.query_all") as mock_qall, \
             patch("api.routers.events.query_one") as mock_qone:
            mock_qall.return_value = fake_events
            mock_qone.return_value = {"cnt": 1}
            resp = client.get("/events?limit=10&offset=0")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["events"]) == 1
        assert data["events"][0]["confirmed"] == 1

    def test_events_pagination_params(self, client):
        with patch("api.routers.events.query_all") as mock_qall, \
             patch("api.routers.events.query_one") as mock_qone:
            mock_qall.return_value = []
            mock_qone.return_value = {"cnt": 0}
            resp = client.get("/events?limit=5&offset=10")

        assert resp.status_code == 200
        # limit/offset이 쿼리에 전달되었는지 확인
        call_params = mock_qall.call_args[0][1]
        assert call_params == (5, 10)

    def test_events_invalid_limit(self, client):
        """limit 범위 초과 → 422"""
        resp = client.get("/events?limit=999")
        assert resp.status_code == 422

    # ── /csi/stream ──────────────────────────────────────────────────────────

    def test_csi_stream_returns_samples(self, client):
        amp = np.array([0.1, 0.5, 0.3], dtype=np.float32)
        fake_rows = [
            {"timestamp": 1711360200.0,
             "subcarrier_data": amp.tobytes(),
             "n_subcarriers": 3},
        ]
        with patch("api.routers.csi.query_all") as mock_qall:
            mock_qall.return_value = fake_rows
            resp = client.get("/csi/stream?n=1")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["samples"]) == 1
        assert data["samples"][0]["timestamp"] == pytest.approx(1711360200.0)
        expected_mean = float(amp.mean())
        assert data["samples"][0]["mean_amplitude"] == pytest.approx(expected_mean, abs=1e-5)

    def test_csi_stream_empty(self, client):
        with patch("api.routers.csi.query_all") as mock_qall:
            mock_qall.return_value = []
            resp = client.get("/csi/stream")

        assert resp.status_code == 200
        assert resp.json()["samples"] == []

    # ── /stats ────────────────────────────────────────────────────────────────

    def test_stats_structure(self, client):
        with patch("api.routers.stats.query_one") as mock_qone, \
             patch("api.routers.stats.query_all") as mock_qall:
            mock_qone.return_value = {"cnt": 8}
            mock_qall.side_effect = [
                [{"date": "2026-03-25", "total": 3, "confirmed": 2}],
                [{"hour": 14, "total": 5}],
            ]
            resp = client.get("/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["confirmed_total"] == 8
        assert len(data["daily"]) == 1
        assert data["daily"][0]["date"] == "2026-03-25"
        assert len(data["hourly"]) == 1
        assert data["hourly"][0]["hour"] == 14

    def test_stats_empty_db(self, client):
        with patch("api.routers.stats.query_one") as mock_qone, \
             patch("api.routers.stats.query_all") as mock_qall:
            mock_qone.return_value = None
            mock_qall.return_value = []
            resp = client.get("/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["confirmed_total"] == 0
        assert data["daily"] == []
        assert data["hourly"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 전체 파이프라인 통합 — 오탐률 / 미탐률 측정
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullPipelineMetrics:
    """
    CSIInferencer(mock) → CrossValidator → EventLogger(mock) 전체 흐름을 N회 시뮬레이션.
    오탐률(FPR)과 미탐률(FNR) 허용 기준 검증.
    """

    def _run_pipeline(self, scenarios):
        """
        scenarios: list of (csi_fall, has_impact, expected_confirmed)

        각 이벤트는 독립적인 CrossValidator 인스턴스로 평가한다.
        (실제 시스템에서 각 이벤트는 서로 다른 시점에 발생하며 영향을 주지 않음)

        Returns:
            tp, fp, fn, tn counts
        """
        from realtime.event_logger import EventLogger

        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True
        mock_conn.cursor.return_value = MagicMock()
        el = EventLogger(model_version="test_v1")
        el._conn = mock_conn

        tp = fp = fn = tn = 0
        for csi_fall, has_impact, expected in scenarios:
            # 각 이벤트마다 독립 CrossValidator 사용 (시간 bleed 방지)
            cv = CrossValidator(impact_window_sec=0.5, cooldown_sec=0.0)
            if has_impact:
                cv.notify_impact()

            confirmed = cv.validate(csi_fall=csi_fall)
            el.log(
                csi_confidence=0.95 if csi_fall else 0.1,
                impact_detected=has_impact,
                confirmed=confirmed,
            )

            if expected and confirmed:
                tp += 1
            elif not expected and confirmed:
                fp += 1
            elif expected and not confirmed:
                fn += 1
            else:
                tn += 1

        return tp, fp, fn, tn

    def test_perfect_fall_detection(self):
        """낙상 확정 시나리오만 — 100% TP"""
        scenarios = [(True, True, True)] * 10
        tp, fp, fn, tn = self._run_pipeline(scenarios)
        assert tp == 10
        assert fp == 0
        assert fn == 0

    def test_false_positive_removal(self):
        """CSI fall만 있고 충격음 없음 — 전부 FP 제거 (TP=0, FP=0)"""
        scenarios = [(True, False, False)] * 10
        tp, fp, fn, tn = self._run_pipeline(scenarios)
        # expected=False, confirmed=False → tn
        assert fp == 0, "충격음 없이 CSI fall만 → 오탐 제거 실패"
        assert tn == 10

    def test_missed_detection_noise_only(self):
        """충격음만 있고 CSI fall 없음 — 전부 TN (미탐)"""
        scenarios = [(False, True, False)] * 10
        tp, fp, fn, tn = self._run_pipeline(scenarios)
        assert tp == 0
        assert tn == 10

    def test_mixed_scenario_fpr_fnr(self):
        """혼합 시나리오: FPR=0, FNR 허용 기준 검증"""
        # (csi_fall, has_impact, ground_truth)
        scenarios = (
            [(True, True, True)] * 20    # 실제 낙상 20건
            + [(True, False, False)] * 10  # CSI 오탐 10건 (충격음 없음)
            + [(False, True, False)] * 10  # 소음 10건
            + [(False, False, False)] * 10  # 정상 10건
        )
        tp, fp, fn, tn = self._run_pipeline(scenarios)

        total_positive = 20   # 실제 낙상
        total_negative = 30   # 오탐+소음+정상

        fpr = fp / total_negative if total_negative > 0 else 0.0
        fnr = fn / total_positive if total_positive > 0 else 0.0

        print(f"\n[파이프라인 메트릭] TP={tp}, FP={fp}, FN={fn}, TN={tn}")
        print(f"  FPR(오탐률)={fpr:.1%}, FNR(미탐률)={fnr:.1%}")

        assert fpr == 0.0, f"FPR(오탐률)이 0이어야 하나 {fpr:.1%}입니다"
        assert fnr == 0.0, f"FNR(미탐률)이 0이어야 하나 {fnr:.1%}입니다"
        assert tp == 20


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
