# 현장 실제 추론 테스트 가이드

> WiFi-CSI 낙상 감지 시스템 — 현장 배치 및 실행 절차

---

## 1. 하드웨어 배치 (공유기 + RPi)

### 권장 배치 구조

```
[공유기]
   │  ← WiFi 신호 (2.4GHz, 5GHz 중 2.4GHz 권장)
   │
[실험 공간 — 빈 공간 필요]
   │
   ├── 실험 대상자 동선 (공유기와 RPi 사이)
   │
[RPi 4]  ← Nexmon CSI로 WiFi 패킷 수신
```

### 배치 원칙

| 항목 | 권장값 | 이유 |
|------|--------|------|
| 공유기 ↔ RPi 거리 | **3 ~ 5 m** | 너무 가까우면 신호 포화, 너무 멀면 SNR 저하 |
| 실험자 위치 | 공유기-RPi **연결선 위** | CSI 변화량이 가장 큰 경로 |
| 공유기 높이 | **1.0 ~ 1.5 m** (책상/선반) | 낙상 시 신호 차폐 극대화 |
| RPi 높이 | **0.5 ~ 1.0 m** (바닥 가까이) | 낙상 충격 방향 수신 유리 |
| 벽·가구 장애물 | 최소화 | 다중 경로 노이즈 감소 |

### 실제 배치 도면

```
벽 ──────────────────────────────────── 벽
│                                          │
│   [공유기]                               │
│   높이 1.2m                              │
│       │                                  │
│       │  ← 3~5m →                        │
│       │                                  │
│   실험자 동선 (낙상 발생 위치)            │
│                                          │
│                        [RPi 4 + 마이크]  │
│                         높이 0.8m        │
│                                          │
벽 ──────────────────────────────────── 벽
```

### 채널 설정

```bash
# RPi에서 채널 확인 (공유기와 동일 채널이어야 함)
sudo iwlist wlan0 channel

# Nexmon CSI 채널 고정 (공유기 채널에 맞춤, 예: 6번)
sudo iw dev wlan0 set channel 6
```

---

## 2. 다른 공유기 사용 시 주의사항

> 현장의 공유기가 바뀌어도 시스템 동작에는 문제없습니다.
> Nexmon CSI는 특정 공유기가 아닌 **WiFi 전파(무선 채널)의 변화** 자체를 측정하기 때문입니다.

### 공유기가 달라도 되는 이유

| 항목 | 영향 |
|------|------|
| 공유기 브랜드/모델 | 무관 (표준 802.11n/ac면 OK) |
| SSID / 비밀번호 | 무관 (RPi는 이더넷으로 연결) |
| 공유기 제조사 | 무관 |

### 새 공유기에서 반드시 확인할 것

**① 채널 일치** — Nexmon이 새 공유기 채널을 모니터링해야 합니다

```bash
# 현장 공유기 채널 확인 (모니터 모드 진입 전에 실행)
sudo iwlist wlan0 scan 2>/dev/null | grep -A5 "ESSID" | grep -E "ESSID|Channel"

# Nexmon을 해당 채널로 고정 (예: 채널 1)
sudo iw dev wlan0 set channel 1
```

**② RPi 인터넷 연결은 이더넷으로**

Nexmon이 `wlan0`을 모니터 모드로 점유하므로 WiFi로는 SSH 불가.
반드시 **LAN 케이블** 연결 후 진행:

```bash
# 이더넷 연결 확인
ip addr show eth0 | grep inet
# 예상: inet 192.168.x.x/24
```

### 환경(방)이 달라질 때 성능 변화

CSI는 방의 구조(벽·가구)에 따라 다중 경로 패턴이 달라집니다.
모델은 다양한 환경에서 수집된 CSI-HAR-Dataset으로 학습했으므로 일반화되어 있지만,
완전히 새로운 공간에서는 fall recall이 소폭 낮아질 수 있습니다.

**처음 설치 시 반드시 시험 낙상을 2~3회 수행하여 감지 여부를 확인하세요.**

---

## 3. GPIO 하드웨어 배선 (부저, LED, LCD)

### 핀 배정 (BCM 번호 기준)

| 장치 | BCM 핀 | 물리 핀 | 역할 |
|------|--------|---------|------|
| 부저 (Passive) | GPIO 18 | 12번 | PWM 출력 (1kHz) |
| LED | GPIO 23 | 16번 | HIGH=ON, LOW=OFF |
| LCD SDA | GPIO 2 | 3번 | I2C 데이터 |
| LCD SCL | GPIO 3 | 5번 | I2C 클럭 |

### RPi 4 GPIO 핀맵 (관련 핀만)

```
        3.3V  [ 1] [ 2]  5V
  SDA / GPIO2  [ 3] [ 4]  5V
  SCL / GPIO3  [ 5] [ 6]  GND
               ...
  GPIO18(PWM)  [12] [11]  ...
               ...
       GPIO23  [16] [17]  3.3V
               ...
          GND  [20] [19]  ...
```

### 부저 배선 (Passive Buzzer)

```
RPi GPIO 18 (핀 12) ──────────── 부저 + 단자
RPi GND     (핀 14) ──────────── 부저 - 단자
```

> **Active Buzzer** 사용 시 PWM 불필요 — HIGH 신호만으로 울림.
> 코드 기본값은 Passive Buzzer (PWM 1kHz). Active로 바꾸려면
> `gpio_alert.py`의 `buzzer_freq` 무시하고 `GPIO.output()` 방식으로 수정 필요.

### LED 배선

```
RPi GPIO 23 (핀 16) ── [220Ω 저항] ── LED 양극(+, 긴 다리)
RPi GND     (핀 20) ──────────────── LED 음극(-, 짧은 다리)
```

> 저항 없이 직결하면 LED 손상 또는 RPi GPIO 손상 위험.
> 220Ω ~ 330Ω 저항을 반드시 직렬 연결하세요.

### LCD (I2C, 선택)

```
RPi 3.3V (핀 1) ─── LCD VCC
RPi GND  (핀 6) ─── LCD GND
RPi SDA  (핀 3) ─── LCD SDA
RPi SCL  (핀 5) ─── LCD SCL
```

I2C 주소 확인:
```bash
sudo i2cdetect -y 1
# 0x27 위치에 '27'이 표시되면 정상
```

LCD 라이브러리 설치:
```bash
source /home/lee/project/venv/bin/activate
pip install RPLCD
```

### GPIO 동작 테스트 (실제 연결 전 확인)

```bash
cd /home/lee/project
source venv/bin/activate
python scripts/test/test_gpio.py
# 부저 1초 울림 → LED 1초 점등 → LCD 메시지 출력 순서로 동작
```

---

## 4. 현장 도착 후 실행 순서

### 4-1. 서비스 상태 확인

```bash
# RPi SSH 접속 후
printf "csi-api: %s\napache2: %s\nmysql:   %s\n" \
    "$(systemctl is-active csi-api)" \
    "$(systemctl is-active apache2)" \
    "$(systemctl is-active mysql)"
```

모두 `active`여야 합니다. 미기동 시 아래 명령으로 시작:

```bash
sudo systemctl start mysql
sudo systemctl start csi-api
sudo systemctl start apache2
```

### 4-2. MySQL DB 초기화 (첫 방문 시만)

```bash
# DB 스키마 적용
mysql -u csi_user -pchangeme csi_fall_db < /home/lee/project/db/schema.sql

# 확인
mysql -u csi_user -pchangeme csi_fall_db -e "SHOW TABLES;"
```

### 4-3. Nexmon CSI 활성화

```bash
# wlan0 모니터 모드 전환 + CSI 활성화
sudo ip link set wlan0 down
sudo iw dev wlan0 set type monitor
sudo ip link set wlan0 up

# CSI 수신 시작 (채널 6, 5MHz 대역폭 예시)
sudo nexutil -Iwlan0 -s500 -b -l34 -vKgAAAAAAA=

# 수신 확인 (다른 터미널)
sudo tcpdump -i wlan0 | head -20
```

### 4-4. FastAPI 응답 확인

```bash
curl http://localhost:8000/status
# 정상: {"running": true, "confirmed_total": 0, "last_event": null}
```

---

## 5. 실시간 추론 파이프라인 실행

```bash
cd /home/lee/project
source venv/bin/activate

python -m realtime.main \
    --model cnn_gru \
    --model-path models/best_model.pth
```

실행 후 터미널에서 확인할 로그:

```
[CSIBuffer]   버퍼 채우는 중... (0/100)
[CSIBuffer]   추론 시작
[MicMonitor]  마이크 스트림 시작
[Decision]    대기 중...
```

종료: `Ctrl+C`

---

## 6. 낙상 시나리오별 테스트

### 시나리오 1 — 낙상 확정 (정탐)

| 조건 | 행동 |
|------|------|
| 실험자 위치 | 공유기-RPi 연결선 위, 3m 지점 |
| 동작 | 매트 위로 옆으로 쓰러짐 |
| 기대 결과 | `[ALERT] FALL DETECTED` 출력, GPIO 경보 |

```bash
# 결과 확인 (다른 터미널)
curl -s http://localhost:8000/events?limit=5 | python3 -m json.tool
```

### 시나리오 2 — 오탐 제거 (충격음 없이)

| 조건 | 행동 |
|------|------|
| 실험자 위치 | 동일 |
| 동작 | 빠르게 앉기, 갑자기 구부리기 (충격음 없음) |
| 기대 결과 | 경보 **없음** (CSI fall + 충격음 X → 오탐 제거) |

### 시나리오 3 — 단순 소음 무시

| 조건 | 행동 |
|------|------|
| 실험자 위치 | RPi 옆 |
| 동작 | 무거운 물건을 바닥에 떨어뜨림 (사람 움직임 없음) |
| 기대 결과 | 경보 **없음** (충격음 O + CSI fall X → 무시) |

### 측정 지표 기록

테스트 후 아래를 기록합니다:

```bash
mysql -u csi_user -pchangeme csi_fall_db << 'EOF'
SELECT
    COUNT(*) AS total,
    SUM(confirmed) AS confirmed,
    SUM(impact_detected=1 AND confirmed=0) AS false_positive,
    SUM(confirmed=0 AND csi_confidence > 0.8) AS missed
FROM fall_events;
EOF
```

---

## 7. 대시보드 확인

RPi의 IP 주소로 브라우저 접속:

```
http://<RPi_IP>/          ← PHP 대시보드 (Chart.js 실시간 CSI 파형)
http://<RPi_IP>/api/docs  ← FastAPI Swagger UI
```

RPi IP 확인:
```bash
hostname -I | awk '{print $1}'
```

---

## 8. 자주 발생하는 문제

| 증상 | 원인 | 해결 |
|------|------|------|
| CSI 패킷 수신 안 됨 | 채널 불일치 | `sudo iw dev wlan0 set channel <공유기채널>` |
| `Can't connect to MySQL` | MySQL 미기동 | `sudo systemctl start mysql` |
| 경보가 너무 자주 울림 | threshold 낮음 | `ImpactDetector(threshold=0.8)` 조정 |
| 경보가 전혀 안 울림 | 마이크 미인식 | `python scripts/test/test_mic.py` 실행 |
| 모델 추론 느림 | CPU 부하 | `stride=20`으로 변경 (추론 빈도 절반) |


# 재부팅                                                  
  sudo reboot                                                                                                                                   
                                                            
  재부팅 후 커널 버전 확인:
  uname -r
  # 예상: 5.10.xx+
                                                                                                                                                
  확인되면 이어서 실행:
  sudo bash /home/lee/project/scripts/setup/install_nexmon.sh