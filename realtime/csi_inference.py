"""
realtime/csi_inference.py — 실시간 CSI 추론

CSIReader Queue에서 샘플을 받아 슬라이딩 윈도우 버퍼를 유지하고
버퍼가 채워질 때마다 PyTorch 모델로 행동 분류를 수행한다.
"""

from collections import deque

import numpy as np
import torch

from ml.models import MODEL_REGISTRY
from ml.preprocessing import hampel_filter, savitzky_golay, select_subcarriers, normalize_window

# CSI-HAR-Dataset 7클래스
CLASSES = ["bend", "fall", "lie down", "run", "sitdown", "standup", "walk"]

# 낙상 클래스 인덱스: fall(1)
FALL_CLASS_INDICES = {1}


class CSIInferencer:
    """
    롤링 버퍼 + 전처리 + AI 모델 추론.

    Usage:
        inferencer = CSIInferencer("models/best_model.pth", "cnn_gru")
        inferencer.load()
        result = inferencer.push(amp)
        if result:
            class_idx, confidence, is_fall = result
    """

    def __init__(
        self,
        model_path: str,
        model_name: str,
        n_subcarriers: int = 30,
        window_size: int = 100,
        stride: int = 10,
        n_classes: int = 7,
        device: str = "cpu",
    ):
        self.model_path = model_path
        self.model_name = model_name
        self.n_subcarriers = n_subcarriers
        self.window_size = window_size
        self.stride = stride
        self.n_classes = n_classes
        self.device = torch.device(device)

        self._buffer: deque = deque(maxlen=window_size)
        self._step_counter: int = 0
        self._model = None

    def load(self):
        """모델 가중치 로드"""
        model_cls = MODEL_REGISTRY[self.model_name]
        self._model = model_cls(
            input_size=self.n_subcarriers,
            num_classes=self.n_classes,
        )
        state = torch.load(self.model_path, map_location=self.device, weights_only=True)
        self._model.load_state_dict(state)
        self._model.to(self.device)
        self._model.eval()

    def push(self, amp: np.ndarray):
        """
        새 CSI 샘플을 버퍼에 추가. stride마다 추론 수행.

        Args:
            amp: (n_raw_subcarriers,) float32 ndarray

        Returns:
            (class_idx, confidence, is_fall) 또는 None (아직 추론 시점 아님)
        """
        self._buffer.append(amp)
        self._step_counter += 1

        if len(self._buffer) < self.window_size:
            return None
        if self._step_counter % self.stride != 0:
            return None

        return self._infer()

    def _infer(self):
        # (window_size, n_raw_subcarriers)
        csi = np.stack(list(self._buffer), axis=0)

        # 전처리: Hampel → SG → 서브캐리어 선택 → normalize
        csi = hampel_filter(csi)
        csi = savitzky_golay(csi)
        csi = select_subcarriers(csi, n=self.n_subcarriers)
        csi = normalize_window(csi[np.newaxis])[0]  # 단일 윈도우 정규화

        # (1, window_size, n_subcarriers)
        x = torch.tensor(csi, dtype=torch.float32).unsqueeze(0).to(self.device)

        with torch.no_grad():
            logits = self._model(x)          # (1, n_classes)
            probs = torch.softmax(logits, dim=-1)[0]
            class_idx = int(probs.argmax().item())
            confidence = float(probs[class_idx].item())

        is_fall = class_idx in FALL_CLASS_INDICES
        return class_idx, confidence, is_fall

    @staticmethod
    def class_name(idx: int) -> str:
        return CLASSES[idx] if 0 <= idx < len(CLASSES) else "unknown"
