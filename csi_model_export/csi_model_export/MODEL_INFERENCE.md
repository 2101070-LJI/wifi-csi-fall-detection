# CSI-HAR 낙상 감지 모델 — 추론 가이드

> 다른 하드웨어에서 `best_model.pth` (CNN-GRU)를 로드해 추론하는 데 필요한 모든 정보

---

## 성능 지표

| 항목 | 수치 |
|------|------|
| Test Accuracy | **99.87%** |
| fall recall | **100%** |
| lie_down recall | **99.78%** |
| 추론 속도 (GPU) | 0.06 ms/sample |
| 파라미터 수 | 131,271 |

---

## 의존성

```
python==3.8.*
torch>=1.9.0          # CPU 전용이면 일반 pip 설치 가능
numpy
pandas
scipy
```

CUDA GPU 사용 시:
```
torch>=1.9.0+cu111    # CUDA 11.x 계열
```

CPU 전용 (Raspberry Pi 등):
```
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

---

## 클래스 레이블

```python
CLASSES = ['bend', 'fall', 'lie down', 'run', 'sitdown', 'standup', 'walk']
# 인덱스:    0       1       2           3      4          5          6
```

---

## 모델 아키텍처 (CNN-GRU)

```
입력: (batch, 100, 30)   ← (배치, 타임스텝, 서브캐리어)

Conv1d(30→64, k=3, pad=1) → BatchNorm1d → ReLU → Dropout(0.3)
↓
GRU(64→64, num_layers=2, bidirectional=True, dropout=0.3)
↓ (양방향 마지막 hidden concat)
Linear(128→7)

출력: (batch, 7)   ← 클래스별 로짓
```

```python
# ml/models/cnn_gru.py
import torch
import torch.nn as nn

class CNNGRU(nn.Module):
    def __init__(self, input_size=30, num_classes=7,
                 cnn_channels=64, gru_hidden=64, num_layers=2, dropout=0.3):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv1d(input_size, cnn_channels, kernel_size=3, padding=1),
            nn.BatchNorm1d(cnn_channels),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.gru = nn.GRU(cnn_channels, gru_hidden, num_layers=num_layers,
                          batch_first=True, dropout=dropout, bidirectional=True)
        self.fc = nn.Linear(gru_hidden * 2, num_classes)

    def forward(self, x):          # x: (B, T, C)
        x = x.permute(0, 2, 1)    # (B, C, T)
        x = self.cnn(x)            # (B, 64, T)
        x = x.permute(0, 2, 1)    # (B, T, 64)
        _, h = self.gru(x)
        h = torch.cat([h[-2], h[-1]], dim=1)  # (B, 128)
        return self.fc(h)          # (B, 7)
```

---

## 전처리 파이프라인

CSI 원시 데이터(행=타임스텝, 열=52 서브캐리어)에 아래 순서로 적용:

### 1. Hampel 필터 (이상치 제거)
```python
import pandas as pd
import numpy as np

def hampel_filter(data, window_size=5, n_sigma=3.0):
    out = data.copy()
    for c in range(data.shape[1]):
        col = data[:, c]
        s   = pd.Series(col)
        med = s.rolling(window_size, center=True, min_periods=1).median().values
        mad = pd.Series(np.abs(col - med)).rolling(window_size, center=True, min_periods=1).median().values
        thr = n_sigma * 1.4826 * (mad + 1e-10)
        mask = np.abs(col - med) > thr
        out[mask, c] = med[mask]
    return out
```

### 2. Savitzky-Golay 스무딩
```python
from scipy.signal import savgol_filter

def savitzky_golay(data, window=11, poly=3):
    out = np.zeros_like(data)
    for c in range(data.shape[1]):
        out[:, c] = savgol_filter(data[:, c], window_length=window, polyorder=poly)
    return out
```

### 3. 서브캐리어 30개 선택 (분산 기준 상위 30개)

> **중요:** 학습 시 선택된 서브캐리어 인덱스를 그대로 써야 함.
> 추론 환경의 CSI가 학습 데이터와 동일한 52개 서브캐리어 구조라면 아래 함수 사용.
> 채널 수가 다를 경우 인덱스를 학습 시 저장해 두어야 함.

```python
def select_subcarriers(data, n=30):
    variances = np.var(data, axis=0)
    indices   = np.sort(np.argsort(variances)[-n:])
    return data[:, indices]
```

### 4. 슬라이딩 윈도우
```python
WIN_SIZE = 100   # 타임스텝
STRIDE   = 10

def sliding_window(data, win_size=100, stride=10):
    windows = []
    for start in range(0, len(data) - win_size + 1, stride):
        windows.append(data[start:start + win_size])
    return np.stack(windows) if windows else np.empty((0, win_size, data.shape[1]))
```

### 5. MinMax 정규화 (윈도우 단위)
```python
def normalize_window(windows):
    out = windows.copy()
    for i in range(len(out)):
        mn, mx = out[i].min(), out[i].max()
        if mx - mn > 1e-8:
            out[i] = (out[i] - mn) / (mx - mn)
    return out
```

---

## 추론 코드 (완전한 예시)

```python
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from scipy.signal import savgol_filter

CLASSES = ['bend', 'fall', 'lie down', 'run', 'sitdown', 'standup', 'walk']

# --- 모델 정의 (위의 CNNGRU 클래스 붙여넣기) ---

def preprocess(raw_csv_path):
    """CSV 파일 경로 → 슬라이딩 윈도우 텐서 (N, 100, 30)"""
    data = pd.read_csv(raw_csv_path, header=None).values.astype(np.float32)
    # 1. Hampel
    data = hampel_filter(data)
    # 2. SG
    data = savitzky_golay(data)
    # 3. 서브캐리어 선택
    data = select_subcarriers(data, n=30)
    # 4. 슬라이딩 윈도우
    windows = sliding_window(data)
    # 5. 정규화
    windows = normalize_window(windows)
    return torch.from_numpy(windows)   # (N, 100, 30)


def load_model(pth_path, device='cpu'):
    model = CNNGRU(input_size=30, num_classes=7)
    model.load_state_dict(torch.load(pth_path, map_location=device))
    model.to(device)
    model.eval()
    return model


def predict(model, windows, device='cpu'):
    """
    windows: torch.Tensor (N, 100, 30)
    반환: 윈도우별 예측 클래스 이름 리스트, 최다수 클래스 (다수결)
    """
    with torch.no_grad():
        logits = model(windows.to(device))         # (N, 7)
        preds  = logits.argmax(dim=1).cpu().numpy()

    per_window = [CLASSES[p] for p in preds]
    majority   = CLASSES[np.bincount(preds).argmax()]
    return per_window, majority


# --- 사용 예시 ---
if __name__ == '__main__':
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model  = load_model('best_model.pth', device=device)

    windows = preprocess('path/to/csi_sample.csv')
    per_win, result = predict(model, windows, device=device)

    print(f'윈도우별 예측: {per_win}')
    print(f'최종 판정:    {result}')
```

---

## 실시간 스트리밍 추론 (슬라이딩 윈도우 버퍼)

```python
from collections import deque

class RealtimeInference:
    def __init__(self, model, device='cpu', win_size=100, stride=10):
        self.model   = model
        self.device  = device
        self.win_size = win_size
        self.stride  = stride
        self.buffer  = deque(maxlen=win_size)  # 최근 100 타임스텝 유지
        self.step    = 0

    def push(self, frame: np.ndarray) -> str | None:
        """
        frame: 1D array (52,) — 한 타임스텝의 서브캐리어 값
        stride마다 추론 실행, 결과 반환. 버퍼 부족 시 None.
        """
        self.buffer.append(frame)
        self.step += 1

        if len(self.buffer) < self.win_size:
            return None
        if self.step % self.stride != 0:
            return None

        window = np.array(self.buffer, dtype=np.float32)  # (100, 52)
        # 전처리 (Hampel, SG, 서브캐리어 선택, 정규화)
        window = hampel_filter(window)
        window = savitzky_golay(window)
        window = select_subcarriers(window, n=30)
        mn, mx = window.min(), window.max()
        if mx - mn > 1e-8:
            window = (window - mn) / (mx - mn)

        t = torch.from_numpy(window).unsqueeze(0)  # (1, 100, 30)
        with torch.no_grad():
            pred = self.model(t.to(self.device)).argmax(1).item()
        return CLASSES[pred]
```

---

## 입력 데이터 형식 요약

| 항목 | 값 |
|------|-----|
| 원시 CSV 형식 | 헤더 없음, 행=타임스텝, 열=서브캐리어 |
| 서브캐리어 수 (원시) | 52 |
| 서브캐리어 수 (선택 후) | 30 |
| 윈도우 크기 | 100 타임스텝 |
| 슬라이딩 보폭 | 10 타임스텝 |
| 정규화 범위 | [0, 1] (윈도우 단위 MinMax) |
| 모델 입력 shape | `(batch, 100, 30)` float32 |
| 모델 출력 shape | `(batch, 7)` logit |

---

## 비교 실험 결과 (전체 모델)

| 모델 | 정확도 | 추론(ms) | fall recall | lie_down recall |
|------|--------|---------|------------|----------------|
| **CNN-GRU** ← best | **99.87%** | 0.06 | **100%** | **99.78%** |
| ResNet1D | 99.67% | 0.01 | 100% | 99.78% |
| CNN-LSTM | 99.54% | 0.04 | 100% | 99.33% |
| Transformer | 98.81% | 0.01 | 99.35% | 97.32% |
| BLSTM | 98.51% | 0.08 | 100% | 95.75% |
| Attention-BLSTM | 98.25% | 0.08 | 99.57% | 97.54% |

> Raspberry Pi 4에서 추론 속도는 GPU 대비 약 10~50배 느림 예상. ResNet1D(0.01ms)와 Transformer(0.01ms)가 RPi 환경에서 유리할 수 있음.
