#!/usr/bin/env python3
"""
test_gpio.py — GPIO 하드웨어 연결 테스트
부저, LED, LCD(I2C) 순으로 동작 확인

핀 구성 (BCM 번호):
  LED    → GPIO 17
  부저   → GPIO 27
  LCD    → I2C (SDA=GPIO2, SCL=GPIO3)

실행: python3 test_gpio.py
"""

import sys
import time

# RPi.GPIO 임포트 확인
try:
    import RPi.GPIO as GPIO
except ImportError:
    print("[ERROR] RPi.GPIO 가 설치되어 있지 않습니다.")
    print("        source venv/bin/activate && pip install RPi.GPIO")
    sys.exit(1)

# ── 핀 번호 (BCM) ─────────────────────────────────────────────────────────────
LED_PIN    = 17
BUZZER_PIN = 27

# ── GPIO 초기화 ───────────────────────────────────────────────────────────────
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(LED_PIN,    GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(BUZZER_PIN, GPIO.OUT, initial=GPIO.LOW)


def test_led(blink_count: int = 5, interval: float = 0.3) -> bool:
    """LED 점멸 테스트"""
    print(f"\n[LED] GPIO {LED_PIN} 점멸 테스트 ({blink_count}회)")
    try:
        for i in range(blink_count):
            GPIO.output(LED_PIN, GPIO.HIGH)
            time.sleep(interval)
            GPIO.output(LED_PIN, GPIO.LOW)
            time.sleep(interval)
            print(f"  점멸 {i + 1}/{blink_count}", end="\r")
        print("  [LED] PASS                    ")
        return True
    except Exception as e:
        print(f"  [LED] FAIL: {e}")
        return False


def test_buzzer(beep_count: int = 3, on_ms: int = 100, off_ms: int = 200) -> bool:
    """부저 비프 테스트"""
    print(f"\n[부저] GPIO {BUZZER_PIN} 비프 테스트 ({beep_count}회)")
    try:
        for i in range(beep_count):
            GPIO.output(BUZZER_PIN, GPIO.HIGH)
            time.sleep(on_ms / 1000)
            GPIO.output(BUZZER_PIN, GPIO.LOW)
            time.sleep(off_ms / 1000)
            print(f"  비프 {i + 1}/{beep_count}", end="\r")
        print("  [부저] PASS                    ")
        return True
    except Exception as e:
        print(f"  [부저] FAIL: {e}")
        return False


def test_lcd_i2c() -> bool:
    """LCD I2C 연결 확인 (smbus2 사용)"""
    print("\n[LCD] I2C 연결 확인")
    try:
        import smbus2
    except ImportError:
        print("  smbus2 없음 — pip install smbus2")
        print("  [LCD] SKIP")
        return False

    bus_num = 1
    try:
        bus = smbus2.SMBus(bus_num)
        # 일반적인 I2C LCD 주소 (0x27 or 0x3F)
        for addr in (0x27, 0x3F):
            try:
                bus.read_byte(addr)
                print(f"  LCD I2C 감지 — 주소 0x{addr:02X}")
                bus.close()
                print("  [LCD] PASS")
                return True
            except OSError:
                continue
        bus.close()
        print("  LCD I2C 장치를 찾을 수 없습니다 (주소 0x27, 0x3F 시도)")
        print("  배선 확인: SDA → GPIO2, SCL → GPIO3")
        print("  [LCD] FAIL")
        return False
    except FileNotFoundError:
        print(f"  /dev/i2c-{bus_num} 없음 — raspi-config에서 I2C 활성화 필요")
        print("  [LCD] FAIL")
        return False


def cleanup():
    GPIO.output(LED_PIN, GPIO.LOW)
    GPIO.output(BUZZER_PIN, GPIO.LOW)
    GPIO.cleanup()


# ── 메인 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  GPIO 하드웨어 연결 테스트")
    print("=" * 50)

    results = {}
    try:
        results["LED"]    = test_led()
        results["부저"]   = test_buzzer()
        results["LCD I2C"] = test_lcd_i2c()
    finally:
        cleanup()

    print("\n" + "=" * 50)
    print("  테스트 결과 요약")
    print("=" * 50)
    all_pass = True
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {name:<10} : {status}")
        if not passed:
            all_pass = False

    print("=" * 50)
    sys.exit(0 if all_pass else 1)
