"""
realtime/main.py — 낙상 감지 실시간 파이프라인 메인 진입점

스레드 구성:
    Thread 1 (CSIBuffer):  CSI 패킷 수신 → 슬라이딩 윈도우 → AI 추론 → result_queue
    Thread 2 (Decision):   result_queue → CSI 단독 판정 → GPIO 경보 + DB 저장

실행:
    python -m realtime.main --model cnn_gru --model-path models/best_model.pth
"""

import argparse
import logging
import signal
import time
from queue import Empty, Queue
from threading import Event, Thread

import numpy as np

from data_collection.csi_reader import CSIReader
from realtime.csi_inference import CSIInferencer
from realtime.event_logger import EventLogger
from realtime.gpio_alert import GPIOAlert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("realtime.main")


def csi_buffer_thread(
    csi_reader: CSIReader,
    inferencer: CSIInferencer,
    result_queue: Queue,
    stop_event: Event,
):
    """Thread 1: CSI 수신 → 추론 → result_queue"""
    logger.info("CSI 버퍼 스레드 시작")
    while not stop_event.is_set():
        try:
            ts, amp = csi_reader.queue.get(timeout=0.5)
        except Empty:
            continue

        result = inferencer.push(amp)
        if result is not None:
            class_idx, confidence, is_fall = result
            result_queue.put((class_idx, confidence, is_fall, ts))

    logger.info("CSI 버퍼 스레드 종료")


def decision_thread(
    result_queue: Queue,
    gpio_alert: GPIOAlert,
    event_logger: EventLogger,
    stop_event: Event,
    alert_duration_sec: float = 3.0,
):
    """Thread 2: CSI 추론 결과 → 낙상 판정 → 경보 + DB 저장"""
    logger.info("판단 스레드 시작")

    while not stop_event.is_set():
        try:
            class_idx, confidence, is_fall, ts = result_queue.get(timeout=0.5)
        except Empty:
            continue

        class_label = CSIInferencer.class_name(class_idx)
        logger.debug(f"추론 결과: {class_label} (conf={confidence:.2f}, fall={is_fall})")

        if is_fall:
            event_logger.log(
                csi_confidence=confidence,
                impact_detected=False,
                confirmed=True,
            )
            logger.warning(f"낙상 확정! class={class_label} conf={confidence:.2f}")
            gpio_alert.trigger(f"FALL:{class_label[:8]}")
            time.sleep(alert_duration_sec)
            gpio_alert.clear()

    logger.info("판단 스레드 종료")


def main():
    parser = argparse.ArgumentParser(description="낙상 감지 실시간 파이프라인")
    parser.add_argument(
        "--model", default="cnn_gru",
        choices=["cnn_lstm", "blstm", "cnn_gru", "attention_blstm", "transformer", "resnet1d"],
    )
    parser.add_argument("--model-path", default="models/best_model.pth")
    parser.add_argument("--n-subcarriers", type=int, default=30)
    parser.add_argument("--window-size", type=int, default=100)
    parser.add_argument("--stride", type=int, default=10)
    parser.add_argument("--alert-duration", type=float, default=3.0,
                        help="경보 지속 시간 (초)")
    parser.add_argument("--buzzer-pin", type=int, default=18)
    parser.add_argument("--led-pin", type=int, default=23)
    args = parser.parse_args()

    # ── 컴포넌트 초기화 ───────────────────────────────────────────────────────
    logger.info(f"모델 로드: {args.model} ← {args.model_path}")
    inferencer = CSIInferencer(
        model_path=args.model_path,
        model_name=args.model,
        n_subcarriers=args.n_subcarriers,
        window_size=args.window_size,
        stride=args.stride,
    )
    inferencer.load()

    csi_reader   = CSIReader()
    gpio_alert   = GPIOAlert(buzzer_pin=args.buzzer_pin, led_pin=args.led_pin)
    event_logger = EventLogger(model_version=f"{args.model}_v1")

    gpio_alert.setup()
    event_logger.connect()

    stop_event   = Event()
    result_queue: Queue = Queue(maxsize=100)

    # ── 시그널 핸들러 ─────────────────────────────────────────────────────────
    def _shutdown(signum, frame):
        logger.info("종료 신호 수신, 파이프라인 중지 중...")
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # ── 스레드 시작 ───────────────────────────────────────────────────────────
    csi_reader.start()

    threads = [
        Thread(
            target=csi_buffer_thread,
            args=(csi_reader, inferencer, result_queue, stop_event),
            name="CSIBuffer",
            daemon=True,
        ),
        Thread(
            target=decision_thread,
            args=(result_queue, gpio_alert, event_logger, stop_event, args.alert_duration),
            name="Decision",
            daemon=True,
        ),
    ]

    for t in threads:
        t.start()

    logger.info("낙상 감지 파이프라인 가동 중 — Ctrl+C로 종료")

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop_event.set()

    for t in threads:
        t.join(timeout=3.0)

    csi_reader.stop()
    event_logger.close()
    gpio_alert.cleanup()
    logger.info("파이프라인 정상 종료")


if __name__ == "__main__":
    main()
