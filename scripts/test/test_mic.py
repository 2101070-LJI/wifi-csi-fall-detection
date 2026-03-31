#!/usr/bin/env python3
"""
test_mic.py — 마이크 모듈 동작 확인
sounddevice로 3초 녹음 후 RMS 진폭 출력으로 정상 동작 확인

실행: python3 test_mic.py [--device DEVICE_INDEX] [--duration 3]
"""

import argparse
import sys

import numpy as np

try:
    import sounddevice as sd
except ImportError:
    print("[ERROR] sounddevice 가 설치되어 있지 않습니다.")
    print("        source venv/bin/activate && pip install sounddevice")
    sys.exit(1)


# ── 설정 ──────────────────────────────────────────────────────────────────────
SAMPLE_RATE  = 44100
CHANNELS     = 1
DTYPE        = "float32"
RMS_THRESHOLD = 0.005   # 이 값 이상이면 마이크 정상으로 판단


def list_devices():
    print("\n사용 가능한 오디오 장치:")
    print(sd.query_devices())


def record_and_check(device: int | None, duration: float) -> bool:
    """녹음 후 RMS 진폭 확인"""
    print(f"\n[마이크] {duration:.1f}초 녹음 시작 (Ctrl+C로 중단)")
    print("  → 마이크에 소리를 내어주세요.\n")

    try:
        audio = sd.rec(
            int(duration * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            device=device,
        )
        sd.wait()
    except sd.PortAudioError as e:
        print(f"  [마이크] PortAudio 오류: {e}")
        return False

    audio = audio.flatten()

    # ── 통계 계산 ────────────────────────────────────────────────────────────
    rms      = float(np.sqrt(np.mean(audio ** 2)))
    peak     = float(np.max(np.abs(audio)))
    duration_actual = len(audio) / SAMPLE_RATE

    print(f"  샘플 수   : {len(audio):,}")
    print(f"  실제 길이 : {duration_actual:.2f}초")
    print(f"  RMS 진폭  : {rms:.6f}")
    print(f"  피크 진폭 : {peak:.6f}")

    # ── ASCII 파형 미리보기 (80열) ────────────────────────────────────────────
    print("\n  파형 미리보기 (80 샘플 다운샘플):")
    step     = max(1, len(audio) // 80)
    envelope = [abs(audio[i * step]) for i in range(80)]
    max_val  = max(envelope) if max(envelope) > 0 else 1.0
    bar_h    = 8
    for row in range(bar_h, 0, -1):
        line = ""
        for val in envelope:
            bar = int((val / max_val) * bar_h)
            line += "█" if bar >= row else " "
        print(f"  |{line}|")
    print(f"  └{'─' * 80}┘")

    # ── 판정 ─────────────────────────────────────────────────────────────────
    if rms >= RMS_THRESHOLD:
        print(f"\n  [마이크] PASS — RMS {rms:.6f} ≥ {RMS_THRESHOLD}")
        return True
    else:
        print(f"\n  [마이크] FAIL — RMS {rms:.6f} < {RMS_THRESHOLD}")
        print("  마이크 연결 및 ALSA 설정(/etc/asound.conf)을 확인하세요.")
        print("  arecord -l 로 장치 목록 확인 후 --device 옵션으로 인덱스 지정.")
        return False


# ── CLI ───────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="마이크 동작 확인 스크립트")
    p.add_argument("--device",   type=int, default=None,
                   help="sounddevice 장치 인덱스 (기본: 시스템 기본값)")
    p.add_argument("--duration", type=float, default=3.0,
                   help="녹음 시간(초) (기본: 3)")
    p.add_argument("--list",     action="store_true",
                   help="사용 가능한 오디오 장치 목록 출력")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    print("=" * 50)
    print("  마이크 모듈 동작 확인")
    print("=" * 50)

    if args.list:
        list_devices()
        sys.exit(0)

    passed = record_and_check(device=args.device, duration=args.duration)

    print("\n" + "=" * 50)
    sys.exit(0 if passed else 1)
