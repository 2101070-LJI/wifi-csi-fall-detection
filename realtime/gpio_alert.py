"""
realtime/gpio_alert.py — 낙상 확정 시 GPIO 경보 출력

GPIO 핀 배정 (기본값):
    부저: GPIO 18 (PWM)
    LED:  GPIO 23
    LCD:  I2C 주소 0x27 (PCF8574 확장 모듈, 16x2 문자 LCD)
          RPLCD 라이브러리 미설치 시 자동 비활성화
"""

import logging

logger = logging.getLogger(__name__)

DEFAULT_BUZZER_PIN = 18
DEFAULT_LED_PIN    = 23
DEFAULT_LCD_ADDR   = 0x27
DEFAULT_LCD_COLS   = 16
DEFAULT_LCD_ROWS   = 2

try:
    import RPi.GPIO as GPIO
    _GPIO_AVAILABLE = True
except ImportError:
    _GPIO_AVAILABLE = False
    logger.warning("RPi.GPIO를 찾을 수 없습니다 — GPIO 경보가 비활성화됩니다.")

try:
    from RPLCD.i2c import CharLCD
    _LCD_AVAILABLE = True
except ImportError:
    _LCD_AVAILABLE = False
    logger.warning("RPLCD를 찾을 수 없습니다 — LCD 출력이 비활성화됩니다.")


class GPIOAlert:
    """
    낙상 확정 시 부저/LED/LCD 경보 출력.

    Usage:
        alert = GPIOAlert()
        alert.setup()
        alert.trigger("FALL DETECTED")
        time.sleep(3)
        alert.clear()
        alert.cleanup()
    """

    def __init__(
        self,
        buzzer_pin: int = DEFAULT_BUZZER_PIN,
        led_pin: int = DEFAULT_LED_PIN,
        buzzer_freq: int = 1000,
        buzzer_duty: float = 50.0,
        lcd_addr: int = DEFAULT_LCD_ADDR,
        lcd_cols: int = DEFAULT_LCD_COLS,
        lcd_rows: int = DEFAULT_LCD_ROWS,
    ):
        self.buzzer_pin  = buzzer_pin
        self.led_pin     = led_pin
        self.buzzer_freq = buzzer_freq
        self.buzzer_duty = buzzer_duty
        self.lcd_addr    = lcd_addr
        self.lcd_cols    = lcd_cols
        self.lcd_rows    = lcd_rows

        self._pwm  = None
        self._lcd  = None

    def setup(self):
        """GPIO 초기화 — 프로그램 시작 시 1회 호출"""
        if _GPIO_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(self.buzzer_pin, GPIO.OUT)
            GPIO.setup(self.led_pin, GPIO.OUT)
            self._pwm = GPIO.PWM(self.buzzer_pin, self.buzzer_freq)
            GPIO.output(self.led_pin, GPIO.LOW)

        if _LCD_AVAILABLE:
            try:
                self._lcd = CharLCD(
                    i2c_expander="PCF8574",
                    address=self.lcd_addr,
                    port=1,
                    cols=self.lcd_cols,
                    rows=self.lcd_rows,
                    dotsize=8,
                )
                self._lcd.clear()
                self._lcd.write_string("System Ready")
            except Exception as e:
                logger.warning(f"LCD 초기화 실패: {e}")
                self._lcd = None

    def trigger(self, message: str = "FALL DETECTED"):
        """경보 출력 — 부저 + LED + LCD"""
        logger.warning(f"[ALERT] {message}")

        if _GPIO_AVAILABLE and self._pwm:
            self._pwm.start(self.buzzer_duty)
            GPIO.output(self.led_pin, GPIO.HIGH)

        if self._lcd:
            try:
                self._lcd.clear()
                line1 = message[:self.lcd_cols]
                self._lcd.write_string(line1)
                if len(message) > self.lcd_cols:
                    self._lcd.cursor_pos = (1, 0)
                    self._lcd.write_string(message[self.lcd_cols : self.lcd_cols * 2])
            except Exception as e:
                logger.warning(f"LCD 출력 실패: {e}")

    def clear(self):
        """경보 해제"""
        if _GPIO_AVAILABLE and self._pwm:
            self._pwm.stop()
            GPIO.output(self.led_pin, GPIO.LOW)

        if self._lcd:
            try:
                self._lcd.clear()
                self._lcd.write_string("Monitoring...")
            except Exception as e:
                logger.warning(f"LCD 클리어 실패: {e}")

    def cleanup(self):
        """GPIO 정리 — 프로그램 종료 시 호출"""
        self.clear()
        if _GPIO_AVAILABLE:
            GPIO.cleanup()
        if self._lcd:
            try:
                self._lcd.close(clear=True)
            except Exception:
                pass
