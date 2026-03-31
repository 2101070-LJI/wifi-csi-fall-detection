# WiFi-CSI 기반 낙상 감지 시스템 구현 계획

**Goal:** Raspberry Pi 4에서 WiFi CSI + 마이크 교차검증으로 낙상을 실시간 감지하고 LAMP 대시보드로 관제

**Architecture:**
- 데이터 레이어: Nexmon CSI (WiFi) + sounddevice (마이크) → MySQL
- AI 레이어: PyTorch 모델 (다중 모델 비교 후 선정) → FastAPI REST 서버
- 표현 레이어: Apache 리버스 프록시 + PHP + Chart.js 대시보드

**Tech Stack:** Raspberry Pi OS, Nexmon CSI (BCM43455C0), PyTorch, FastAPI, APScheduler, Apache, MySQL, PHP, Chart.js, sounddevice, librosa, RPi.GPIO, ngrok/Cloudflare Tunnel

---

## 시스템 아키텍처

```
[ 하드웨어 ]
Raspberry Pi 4
├── WiFi 칩 (Nexmon CSI)   → CSI 시계열 수집
├── 마이크 모듈            → 충격음 감지
└── GPIO → 브레드보드
         ├── 부저
         ├── LED
         └── LCD

[ 소프트웨어 스택 ]
Linux (Raspberry Pi OS: Raspberry Pi OS Lite (64-bit) / A port of Debian Trixie with no desktop environment / 릴리즈: 2025-12-04)
├── Apache  :80   → 리버스 프록시
├── MySQL         → 탐지 이력, 학습 데이터
├── PHP           → 대시보드 프론트엔드
└── Python
    ├── FastAPI   :8000  → REST API 레이어
    ├── AI 모델           → CSI 시계열 낙상 분류
    └── APScheduler      → 자동 파인튜닝
```

## 시스템 흐름

```
WiFi 신호 → Nexmon CSI 추출 → 전처리 → AI 모델 추론
                                              |
마이크 입력 ─────────── 충격음 감지 → 교차검증 로직
                                              |
                              낙상 확정 / 오탐 제거
                                              |
                         GPIO 경보 + MySQL 저장
                                              |
                     FastAPI → Apache → PHP 대시보드
```

## 교차검증 로직

```
CSI 낙상 감지 O  +  충격음 O  →  낙상 확정  →  경보 출력
CSI 낙상 감지 O  +  충격음 X  →  오탐 제거  →  무시
CSI 낙상 감지 X  +  충격음 O  →  단순 소음  →  무시
```

---

## PHASE 1 — 환경 구축

> 목표: 개발 가능한 상태 만들기
> ⚠️ Nexmon CSI 정상 동작 확인 후 다음 단계 진행

### Task 1-1: RPi OS 세팅 및 Nexmon CSI 설치

**Files:**
- Create: `scripts/setup/install_nexmon.sh`

> ❌ **블로커 — OS 재설치 필요 (2026-03-31)**
>
> 현재 OS: Raspberry Pi OS Trixie (kernel 6.12.47)
> nexmon_csi 지원 커널: 4.19 / 5.4 / 5.10 까지
>
> 펌웨어(brcmfmac43455-sdio.bin)는 교체됐으나, 커널 6.12용 brcmfmac.ko 패치 미지원
> → `iw dev wlan0 set type monitor` 자체 실패 (EOPNOTSUPP)
>
> **해결 방법: Raspberry Pi OS Bookworm (kernel 6.1.x) 재설치 후 install_nexmon.sh 재실행**
> 재설치 전 프로젝트 파일 GitHub 백업 필수

- [ ] 프로젝트 GitHub 백업 (git init + push)
- [ ] SD카드 재플래싱 — Raspberry Pi OS **Bookworm** Lite 64-bit 선택
- [ ] 부팅 후 SSH 연결 확인, 이더넷 연결 (WiFi 비활성화)
- [ ] `sudo bash install_nexmon.sh` 실행
- [x] `install_nexmon.sh` 작성 — 커널 패치, 드라이버 빌드, `nexutil` 설치
- [ ] 재부팅 후 모니터 모드 전환: `sudo bash /usr/local/bin/csi_start.sh`
- [ ] `tcpdump`로 CSI 패킷 수신 검증

```bash
sudo tcpdump -i wlan0 dst port 5500 -vv
```

- [ ] 검증 완료 후 커밋

### Task 1-2: LAMP 스택 설치

**Files:**
- [x] `scripts/setup/install_lamp.sh`

- [x] Apache2, MariaDB, PHP 설치 완료 (2026-03-31)
- [x] MySQL DB/유저 생성 (`csi_fall_db`, `csi_user`, pw: `1111`)
- [x] Apache 기본 동작 확인 (HTTP 200)
- [x] `db/schema.sql` 적용 완료 — 테이블 4개 생성 (sessions, csi_samples, mic_samples, fall_events)

> ⚠️ OS 재설치 후 `sudo bash scripts/setup/install_lamp.sh` 및 스키마 재적용 필요

### Task 1-3: Python 환경 및 AI 라이브러리 설치

**Files:**
- [x] `scripts/setup/install_python_env.sh`
- [x] `requirements.txt` — 버전 범위 및 하드웨어 패키지 정리 완료 (2026-03-31)

- [x] Python 3.13.5, 가상환경(`venv`) 생성 완료
- [x] 전 패키지 import 검증 완료 (`ALL OK`, 2026-03-31)
      - fastapi 0.135.2 / uvicorn 0.42.0 / torch 2.11.0 (CPU)
      - numpy 2.4.3 / scipy 1.17.1 / pandas 3.0.1
      - sounddevice 0.5.5 / librosa 0.11.0
      - apscheduler 3.11.2 / mysql-connector-python 9.6.0
      - RPi.GPIO 0.7.1

> ⚠️ OS 재설치 후 `bash scripts/setup/install_python_env.sh` 재실행 필요

### Task 1-4: GPIO 하드웨어 연결 테스트

**Files:**
- [x] `scripts/test/test_gpio.py` — LED(GPIO 23), 부저(GPIO 27 → 18 PWM으로 수정 예정), LCD I2C
- [x] `scripts/test/test_mic.py` — sounddevice 녹음 + RMS 파형 출력

- [ ] 마이크 모듈 GPIO 연결 (OS 재설치 후 진행)
- [ ] ALSA 설정 (`/etc/asound.conf`) 및 dtoverlay 활성화
- [ ] 실제 하드웨어 연결 후 `python3 scripts/test/test_gpio.py` 실행
- [ ] `python3 scripts/test/test_mic.py` 실행

---

## PHASE 2 — 데이터 수집

> 목표: AI 학습용 CSI 데이터셋 확보
>
> **주 데이터소스: CSI-HAR-Dataset** (`data/download_csihar.py`)
> - 직접 수집(Task 2-3)은 필수가 아니며, CSI-HAR-Dataset에 없는 클래스 보완 및 파인튜닝 용도
> - CSI-HAR 미포함 클래스: fall_side, fall_backward, lie_down_fast, static → 직접 수집 필요
> - 서브캐리어: CSI-HAR-Dataset 30개 (Intel 5300) / Nexmon 256개 → 학습 시 30개로 통일

### 클래스 (CSI-HAR-Dataset 기준, 7개)

| 인덱스 | 클래스 | 설명 |
|--------|--------|------|
| 0 | `bend` | 구부리기 |
| **1** | **`fall`** | **낙상 ← 감지 대상** |
| 2 | `lie down` | 눕기 |
| 3 | `run` | 달리기 |
| 4 | `sitdown` | 앉기 |
| 5 | `standup` | 일어서기 |
| 6 | `walk` | 걷기 |

### Task 2-1: MySQL 스키마 설계

**Files:**
- Create: `db/schema.sql`

- [x] 수집 데이터 저장 테이블 설계

```sql
CREATE TABLE sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    label VARCHAR(50) NOT NULL,
    collected_at DATETIME DEFAULT NOW(),
    distance_m FLOAT,
    direction VARCHAR(20)
);

CREATE TABLE csi_samples (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT,
    timestamp FLOAT,
    subcarrier_data BLOB,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE mic_samples (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT,
    timestamp FLOAT,
    amplitude FLOAT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

- [x] `schema.sql` 작성 완료
- [ ] RPi MySQL에 스키마 적용

### Task 2-2: 동기화 수집 스크립트

**Files:**
- Create: `data_collection/collect.py`
- Create: `data_collection/csi_reader.py`
- Create: `data_collection/mic_reader.py`
- Create: `data_collection/db_writer.py`

- [x] `csi_reader.py` — Nexmon CSI 패킷 파싱 및 서브캐리어 진폭 추출
- [x] `mic_reader.py` — sounddevice 기반 실시간 오디오 수집
- [x] `db_writer.py` — MySQL 저장 유틸리티
- [x] `collect.py` — CSI + 마이크 타임스탬프 동기화 수집 CLI

```bash
python collect.py --label fall_forward --duration 3 --distance 2.0 --direction front
```

- [ ] 실제 RPi에서 수집 테스트 (1개 클래스, 5세션)

### Task 2-3: 보완 데이터 수집 (선택)

> CSI-HAR-Dataset에 없는 클래스 위주로 수집. 전체 재수집 불필요.

- [ ] 미포함 클래스 수집: fall_side, fall_backward, lie_down_fast, static
- [ ] 클래스당 최소 50세션, 다양한 거리(1m~3m) / 방향
- [ ] 수집 후 CSI-HAR 데이터와 병합하여 최종 npz 생성

---

## PHASE 3 — AI 모델 학습

> ✅ **학습 완료. `csi_model_export.zip` 으로 배포됨.**
>
> **선정 모델: CNN-GRU** (`models/best_model.pth`)
> - Test Accuracy: 99.87% | fall recall: 100% | lie_down recall: 99.78%
> - 추론 속도 (GPU): 0.06 ms/sample
> - 클래스: 7개 — `['bend', 'fall', 'lie down', 'run', 'sitdown', 'standup', 'walk']`
> - 입력: (batch, 100, 30) — 윈도우 단위 MinMax 정규화 적용
>
> **전처리 파이프라인 (학습/추론 동일):**
> Hampel → Savitzky-Golay → 서브캐리어 30개 선택 → 슬라이딩 윈도우(100, stride 10) → MinMax 정규화

### Task 3-1: 전처리 파이프라인

**Files:**
- [x] `ml/preprocessing.py`
- [x] `tests/test_preprocessing.py`

- [x] `test_preprocessing.py` 작성 (Hampel 필터, 슬라이딩 윈도우 검증)
- [x] `preprocessing.py` 구현 + export 기준으로 업데이트 (pandas rolling Hampel, normalize_window 추가)

```python
def hampel_filter(data, window_size=5, n_sigma=3): ...   # pandas rolling 방식
def savitzky_golay(data, window=11, poly=3): ...
def select_subcarriers(csi, n=30): ...
def sliding_window(data, window_size=100, stride=10): ...
def normalize_window(windows): ...                        # 윈도우 단위 MinMax [0,1]
def preprocess_csi_session(...): ...                      # 위 5단계 파이프라인
```

- [ ] 테스트 실행 통과 확인 (다른 하드웨어에서)

### Task 3-2: 모델 구현 및 비교 실험

**Files:**
- [x] `ml/models/cnn_lstm.py`
- [x] `ml/models/blstm.py`
- [x] `ml/models/cnn_gru.py`
- [x] `ml/models/attention_blstm.py`
- [x] `ml/models/transformer.py`
- [x] `ml/models/resnet1d.py`
- [x] `ml/train.py`
- [x] `ml/evaluate.py`
- [x] `data/prepare_dataset.py` — MySQL 수집 데이터 → npz 변환 (보완 수집분 병합용)
- [x] `data/generate_dummy.py` — 파이프라인 검증용 합성 데이터 생성
- [x] `data/download_csihar.py` — CSI-HAR-Dataset 다운로드 + 클래스 매핑 변환 (주 학습 데이터)

실험할 모델:

| 모델 | 특징 |
|------|------|
| CNN-LSTM | 공간 패턴 + 시계열, 안정적 |
| BLSTM | 양방향 시계열, 낙상 전후 구분 |
| CNN-GRU | LSTM 대비 경량, 빠른 추론 |
| Attention-BLSTM | 중요 시점 가중치 집중 |
| Transformer | 장거리 의존성, 고정확도 |
| ResNet1D | 1D 신호 잔차 네트워크 |

- [x] 각 모델 구현 (export 아키텍처로 교체: `input_size`/`num_classes` 파라미터, 7클래스)
- [x] `train.py` 작성 — CLASSES 7개 반영, `model_cls(input_size=..., num_classes=...)` 호출
- [x] `evaluate.py` 작성 — fall vs lie_down 구분율, `model_cls(input_size=..., num_classes=...)` 호출
- [x] 모델별 학습 실행 및 결과 비교 (`csi_model_export.zip`)

**비교 실험 결과**

| 모델 | 정확도 | 추론(ms/GPU) | fall recall | lie_down recall |
|------|--------|------------|------------|----------------|
| **CNN-GRU ← 선정** | **99.87%** | 0.06 | **100%** | **99.78%** |
| ResNet1D | 99.67% | 0.01 | 100% | 99.78% |
| CNN-LSTM | 99.54% | 0.04 | 100% | 99.33% |
| Transformer | 98.81% | 0.01 | 99.35% | 97.32% |
| BLSTM | 98.51% | 0.08 | 100% | 95.75% |
| Attention-BLSTM | 98.25% | 0.08 | 99.57% | 97.54% |

- [x] 최종 모델 선정: **CNN-GRU** (fall recall 100%, 추론 0.06ms)
- [x] `models/best_model.pth` 배포 완료 (+ 모델별 `*_best.pth` 7개)

### Task 3-3: 마이크 충격음 감지 로직

**Files:**
- [x] `ml/mic_detector.py`
- [x] `tests/test_mic_detector.py`

- [x] 임계값 기반 충격음 감지 구현 (EMA 배경 소음 추적 + 쿨다운)

```python
class ImpactDetector:
    def __init__(self, threshold=0.5, window_ms=200): ...
    def detect(self, audio_buffer) -> bool: ...
```

- [ ] 테스트 실행 통과 확인 (다른 하드웨어에서)

---

## PHASE 4 — 하드웨어 통합

> ✅ **완료**

### Task 4-1: 실시간 추론 파이프라인

**Files:**
- [x] `realtime/__init__.py`
- [x] `realtime/csi_inference.py`
- [x] `realtime/cross_validator.py`
- [x] `realtime/gpio_alert.py`
- [x] `realtime/event_logger.py`
- [x] `realtime/main.py`

- [x] `csi_inference.py` — 롤링 버퍼(deque) + Hampel/SG/서브캐리어/normalize 전처리 + PyTorch 추론, stride마다 실행
- [x] `cross_validator.py` — CSI 낙상 + 충격음 1초 윈도우 교차검증, 5초 쿨다운

```python
class CrossValidator:
    def notify_impact(self): ...          # 마이크 충격음 감지 시 호출
    def validate(self, csi_fall) -> bool: # CSI fall + 충격음 → 확정
```

- [x] `gpio_alert.py` — 부저(GPIO 18 PWM) + LED(GPIO 23) + I2C LCD(0x27), RPi.GPIO/RPLCD 미설치 시 자동 비활성화
- [x] `event_logger.py` — `fall_events` 테이블에 confidence/impact/confirmed 기록
- [x] `main.py` — 3-스레드 파이프라인, SIGINT/SIGTERM 정상 종료

```python
# 스레드 구성
Thread 1 (CSIBuffer):  CSI 패킷 수신 → 슬라이딩 윈도우 → AI 추론 → result_queue
Thread 2 (MicMonitor): 마이크 스트림 → ImpactDetector → CrossValidator 갱신
Thread 3 (Decision):   result_queue → 교차검증 → GPIO 경보 + DB 저장
```

```bash
# 실행
python -m realtime.main --model cnn_gru --model-path models/best_model.pth
```

- [ ] 실제 RPi에서 통합 테스트 실행

---

## PHASE 5 — LAMP 대시보드 구축

> ✅ **완료 (2026-03-25)**

### FastAPI 엔드포인트

| 엔드포인트 | 설명 |
|-----------|------|
| `GET /status` | 현재 감지 상태 |
| `GET /events` | 낙상 이벤트 이력 |
| `GET /csi/stream` | 최신 CSI 파형 데이터 (csi_samples 폴링) |
| `GET /stats` | 일별/시간대별 통계 |

### Task 5-1: FastAPI 서버

**Files:**
- [x] `api/__init__.py`
- [x] `api/db.py` — `query_one` / `query_all` MySQL 헬퍼 (csi_user/changeme)
- [x] `api/main.py` — FastAPI 앱, CORS, 라우터 등록, docs `/api/docs`
- [x] `api/routers/__init__.py`
- [x] `api/routers/status.py` — 마지막 이벤트 + confirmed 누계
- [x] `api/routers/events.py` — 낙상 이력 (limit/offset 페이지네이션)
- [x] `api/routers/csi.py` — csi_samples → numpy float32 → 평균 진폭 시계열
- [x] `api/routers/stats.py` — 일별(30일) + 시간대별(7일) 집계

- [x] 각 라우터 구현 및 MySQL 연동
- [x] RPi에서 `uvicorn api.main:app --host 0.0.0.0 --port 8000` 실행 확인
      → `config/systemd/csi-api.service` 등록, `systemctl status csi-api` active 확인 (2026-03-26)
      → mysql-connector-python venv 설치 완료
- [ ] 커밋

### Task 5-2: PHP 대시보드

**Files:**
- [x] `dashboard/index.php` — Bootstrap 5 메인 페이지, 상태 카드 3개, 컴포넌트 include
- [x] `dashboard/components/csi_chart.php` — Chart.js 라인차트, 2초 폴링
- [x] `dashboard/components/event_timeline.php` — 이벤트 테이블, 10초 폴링
- [x] `dashboard/components/stats.php` — 일별/시간대별 막대차트, 30초 폴링

- [x] Chart.js 기반 실시간 CSI 파형 시각화
- [x] 낙상 이벤트 타임라인
- [x] 날짜/시간대별 통계
- [ ] RPi 브라우저에서 동작 확인 (Nexmon CSI 재설치 후)
- [ ] 커밋

### Task 5-3: Apache 리버스 프록시 + 외부 접속

**Files:**
- [x] `config/apache/csi-dashboard.conf`

- [x] Apache 리버스 프록시 설정 (`:80` → FastAPI `:8000`)

```apache
ProxyPass /api http://localhost:8000
ProxyPassReverse /api http://localhost:8000
```

```bash
# RPi 배포
sudo cp config/apache/csi-dashboard.conf /etc/apache2/sites-available/
sudo a2enmod proxy proxy_http
sudo a2dissite 000-default
sudo a2ensite csi-dashboard
sudo systemctl reload apache2
```

- [ ] ngrok 또는 Cloudflare Tunnel 설정으로 외부 접속 확인 (Nexmon CSI 재설치 후)
- [ ] 커밋

---

## PHASE 6 — 자동 파인튜닝 + 시스템 통합

> 목표: 전체 파이프라인 자동화 및 완성도 확보

### Task 6-1: APScheduler 자동 재학습

**Files:**
- Create: `autotuning/scheduler.py`
- Create: `autotuning/retrain.py`
- Create: `autotuning/model_manager.py`

- [ ] `retrain.py` — 누적 데이터로 모델 재학습
- [ ] `model_manager.py` — 성능 비교 후 자동 교체 / 롤백 로직

```python
def should_retrain(min_new_samples=50) -> bool:
    """신규 누적 샘플이 50개 이상일 때만 재학습 실행"""
    return count_new_samples() >= min_new_samples

def update_model(new_model_path, new_accuracy):
    if new_accuracy > current_accuracy:
        deploy(new_model_path)
    else:
        rollback()
```

- [ ] `scheduler.py` — APScheduler로 야간 자동 실행 등록
- [ ] 커밋

### Task 6-2: 전체 통합 테스트

- [x] `tests/test_integration.py` 작성 — 28개 테스트 전원 통과 (2026-03-26)
      - CrossValidator 3시나리오 (낙상 확정 / 오탐 제거 / 단순 소음) + 쿨다운
      - CSIInferencer mock 모델 추론 파이프라인
      - EventLogger mock DB 저장 검증
      - FastAPI 전체 엔드포인트 (`/status`, `/events`, `/csi/stream`, `/stats`) TestClient
- [x] 오탐률(FPR) / 미탐률(FNR) 측정 및 기록
      → mock 파이프라인 50개 혼합 시나리오: FPR=0%, FNR=0% 확인
- [ ] 실제 낙상 시나리오 현장 테스트 (낙상 확정, 오탐 제거, 미탐 확인) ← 현장 이동 후 진행 예정
- [ ] 대시보드 end-to-end 동작 확인 (Apache + MySQL 설치 후)
- [ ] 자동 파인튜닝 스케줄 1회 실행 후 모델 갱신 확인 (Task 6-1 완료 후)
- [ ] 최종 커밋

---

## 현재 진행 상황 (2026-03-31)

### 완료
| Phase | 상태 | 비고 |
|-------|------|------|
| PHASE 3 — AI 모델 학습 | ✅ 완료 | CNN-GRU, 99.87%, fall recall 100% |
| PHASE 4 — 하드웨어 통합 코드 | ✅ 완료 | realtime/ 전체 구현 |
| PHASE 5 — LAMP 대시보드 코드 | ✅ 완료 | FastAPI + PHP + Apache 설정 |
| PHASE 1-2 — LAMP 실제 설치 | ✅ 완료 | Apache, MariaDB, PHP, DB 스키마 적용 |
| PHASE 1-3 — Python 환경 설치 | ✅ 완료 | 전 패키지 import 성공 |

### 블로커
| 항목 | 원인 | 해결 방법 |
|------|------|-----------|
| **Nexmon CSI 모니터 모드 불가** | kernel 6.12 미지원 | OS를 Bookworm(kernel 6.1.x)으로 재설치 |

### 남은 작업 (OS 재설치 후)
1. **[필수]** GitHub 백업 → Bookworm 재플래싱 → 코드 복구
2. **[필수]** `sudo bash scripts/setup/install_nexmon.sh` 실행 + CSI 패킷 수신 검증
3. **[필수]** LAMP + Python 환경 재설치 (스크립트 있음)
4. **[필수]** GPIO 하드웨어 연결 (부저, LED, LCD, 마이크) + 테스트 스크립트 실행
5. **[필수]** `python -m realtime.main` 실제 낙상 시나리오 현장 테스트
6. **[필수]** 대시보드 end-to-end 동작 확인
7. **[선택]** PHASE 6 — autotuning/ 3개 파일 구현 + 스케줄 1회 실행

---

## 기술 스택 요약

| 분류 | 기술 |
|------|------|
| OS | Raspberry Pi OS (Linux) |
| WiFi CSI | Nexmon CSI (BCM43455C0) |
| AI / ML | PyTorch, CNN-GRU (99.87%, fall recall 100%) |
| 웹 서버 | Apache |
| 데이터베이스 | MySQL |
| 프론트엔드 | PHP + Chart.js |
| API 레이어 | Python FastAPI |
| 자동화 | APScheduler |
| 오디오 | sounddevice / librosa |
| 하드웨어 | RPi GPIO, 부저, LED, LCD, 마이크 모듈 |
| 외부 터널링 | ngrok / Cloudflare Tunnel |

---

## 파일 구조

```
wifi-csi-fall-detection/
├── scripts/
│   ├── setup/
│   │   ├── install_nexmon.sh
│   │   ├── install_lamp.sh
│   │   └── install_python_env.sh
│   └── test/
│       ├── test_gpio.py
│       └── test_mic.py
├── db/
│   └── schema.sql
├── data_collection/
│   ├── collect.py
│   ├── csi_reader.py
│   ├── mic_reader.py
│   └── db_writer.py
├── data/
│   ├── prepare_dataset.py    ← MySQL 수집 데이터 → npz 변환 (보완 수집분)
│   ├── generate_dummy.py     ← 파이프라인 검증용 합성 데이터
│   ├── download_csihar.py    ← CSI-HAR-Dataset 다운로드 + 변환 (주 학습 데이터) ✓
│   └── download_uthar.py     ← UT-HAR 변환 (대체됨, 참고용 보존)
├── ml/
│   ├── preprocessing.py
│   ├── train.py
│   ├── evaluate.py
│   ├── mic_detector.py
│   └── models/
│       ├── cnn_lstm.py
│       ├── blstm.py
│       ├── cnn_gru.py
│       ├── attention_blstm.py
│       ├── transformer.py
│       └── resnet1d.py
├── realtime/
│   ├── main.py
│   ├── csi_inference.py
│   ├── cross_validator.py
│   ├── gpio_alert.py
│   └── event_logger.py
├── api/
│   ├── main.py
│   └── routers/
│       ├── status.py
│       ├── events.py
│       ├── csi.py
│       └── stats.py
├── dashboard/
│   ├── index.php
│   └── components/
│       ├── csi_chart.php
│       ├── event_timeline.php
│       └── stats.php
├── autotuning/
│   ├── scheduler.py
│   ├── retrain.py
│   └── model_manager.py
├── config/
│   ├── apache/
│   │   └── csi-dashboard.conf
│   └── systemd/
│       └── csi-api.service          ← uvicorn systemd 서비스 (2026-03-26 추가)
├── tests/
│   ├── test_preprocessing.py
│   ├── test_mic_detector.py
│   └── test_integration.py          ← 전체 파이프라인 통합 테스트 28개 (2026-03-26 추가)
├── INFERENCE_SETUP.md               ← 현장 추론 테스트 환경 설정 가이드 (2026-03-26 추가)
├── models/
│   ├── best_model.pth          ← CNN-GRU (선정 모델, 518KB)
│   ├── cnn_gru_best.pth
│   ├── cnn_lstm_best.pth
│   ├── blstm_best.pth
│   ├── attention_blstm_best.pth
│   ├── transformer_best.pth
│   └── resnet1d_best.pth
└── requirements.txt
```

---

## 검증 방법

1. **Nexmon CSI:** `tcpdump`로 CSI 패킷 수신 확인
2. **AI 모델:** 테스트셋 혼동행렬, fall vs lie_down 구분율 집중 확인 (99.78% 달성)
3. **교차검증:** 낙상 / 오탐 / 미탐 시나리오별 결과 확인
4. **대시보드:** FastAPI → PHP 데이터 흐름 end-to-end 확인
5. **자동 파인튜닝:** 신규 샘플 50개 이상 누적 후 스케줄 실행 → 모델 버전 갱신 확인

---

## 단계 요약

```
PHASE 1  환경 구축          ✓ 스크립트 작성 완료 / 실제 RPi 실행·검증 필요
PHASE 2  데이터 수집        ✓ 수집 스크립트 완료 / 주 데이터: CSI-HAR-Dataset
                              보완 수집(fall_side, fall_backward, lie_down_fast, static)은 선택
PHASE 3  AI 모델 학습       ✓ 완료 — CNN-GRU best_model.pth (99.87%, fall recall 100%)
PHASE 4  하드웨어 통합      ✓ 완료 (realtime/ 5개 파일)
PHASE 5  LAMP 대시보드      ◑ uvicorn(csi-api) RPi 기동 확인 ✓
                              Apache·MySQL 미설치 → 현장 설치 필요 (INFERENCE_SETUP.md 참조)
PHASE 6  자동화 + 통합      ◑ 진행 중 ← 현재 단계
                              Task 6-1 (APScheduler 자동 재학습) 미시작
                              Task 6-2 (통합 테스트) mock 검증 완료 / 현장 실제 테스트 예정
```

재부팅 후 — 전체 실행 순서                                                                                                    
                                                                                                                              
  Step 1. 이더넷 SSH 재접속 확인
  ip addr show eth0 | grep inet   # 이더넷 IP 확인 (WiFi는 모니터 모드로 사용)                                                  
                                                                              
  Step 2. Nexmon CSI 활성화                                                                                                     
  sudo bash /usr/local/bin/csi_start.sh   # wlan0 모니터 모드 + CSI 활성화                                                      
                                                                                                                                
  Step 3. CSI 수신 확인 (다른 터미널)                                                                                           
  sudo tcpdump -i wlan0 dst port 5500 -vv                                                                                       
  # UDP 패킷이 들어오면 정상. 공유기 채널이 다르면:                                                                             
  sudo iw dev wlan0 set channel <공유기채널번호>                                                                                
                                                                                                                                
  Step 4. venv 활성화 + 추론 실행                                                                                               
  cd /home/lee/project                                                                                                          
  source venv/bin/activate                                                                                                      
                                                                                                                                
  python -m realtime.main \
      --model cnn_gru \                                                                                                         
      --model-path models/best_model.pth                                                                                      

  실행 후 보이는 정상 로그:                                                                                                     
  [CSIBuffer]   버퍼 채우는 중... (0/100)
  [CSIBuffer]   추론 시작                                                                                                       
  [MicMonitor]  마이크 스트림 시작                                                                                              
  [Decision]    대기 중...        
                                                                                                                                
  Step 5. 낙상 감지 확인                                                                                                      
  # 별도 터미널에서                                                                                                             
  curl -s http://localhost:8000/events?limit=5 | python3 -m json.tool
                                                                                                                                
  ---                                                                                                                           
  테스트 시나리오
                                                                                                                                
  ┌────────────────────────────┬───────────────────────────────────┐                                                          
  │            동작            │             기대 결과             │                                                            
  ├────────────────────────────┼───────────────────────────────────┤
  │ 공유기-RPi 선상에서 쓰러짐 │ [ALERT] FALL DETECTED + GPIO 경보 │                                                            
  ├────────────────────────────┼───────────────────────────────────┤                                                          
  │ 빠르게 앉기 (충격음 없음)  │ 경보 없음 (오탐 제거)             │                                                            
  ├────────────────────────────┼───────────────────────────────────┤                                                            
  │ 물건만 떨어뜨림            │ 경보 없음 (단순 소음)             │                                                            
  └────────────────────────────┴───────────────────────────────────┘                                                            
                                                                                                                              
  ---                                                                                                                           
  지금 당장 할 수 있는 것 (재부팅 전)                                                                                         
                                                                                                                                
  Nexmon 없이 더미 데이터로 추론 파이프라인만 테스트:
                                                                                                                                
  cd /home/lee/project                                                                                                        
  source venv/bin/activate                                                                                                      
  python -m pytest tests/test_integration.py -v   # 28개 mock 테스트                                                          
                                                                                                                                
  CSI 없이 모델만 단독 확인:                                                                                                    
  python -c "                                                                                                                   
  import torch                                                                                                                  
  from ml.models.cnn_gru import CNNGRUModel                                                                                   
  model = torch.load('models/best_model.pth', map_location='cpu')
  model.eval()                                                                                                                  
  x = torch.randn(1, 100, 30)
  out = model(x)                                                                                                                
  print('추론 결과:', out.argmax(dim=1).item(), '(0=bend,1=fall,2=lie down,...)')                                               
  " 