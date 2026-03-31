"""
csi_reader.py — Nexmon CSI 패킷 실시간 파싱

Nexmon CSI는 UDP 포트 5500으로 CSI 패킷을 전송한다.
패킷 구조 (nexmon_csi 레포 기준):
  - 매직 넘버  4 bytes (0x11111111)
  - rssi       1 byte  (signed)
  - frame_ctrl 2 bytes
  - src_mac    6 bytes
  - seq_num    2 bytes
  - core_spatial 1 byte
  - chan_spec  2 bytes
  - chip_ver   2 bytes
  - payload_len 2 bytes
  - CSI data   N bytes (복소수 float, 인터리브 실수/허수)
"""

import socket
import struct
import time
from threading import Thread, Event
from queue import Queue

import numpy as np

# Nexmon CSI 패킷 헤더 파싱 상수
_NEXMON_MAGIC   = 0x11111111
_UDP_PORT       = 5500
_HEADER_FMT     = "<IbHHHIH"      # magic(4), rssi(1pad3), fc(2), src(4+2 treated), ...
_MIN_PKT_LEN    = 24               # 헤더 최소 바이트
_N_SUBCARRIERS  = 256              # BCM43455C0 기준 최대 서브캐리어 수


def _parse_packet(data: bytes) -> np.ndarray | None:
    """
    UDP 패킷 → 서브캐리어 진폭 배열 (float32, shape: [n_subcarriers])
    파싱 실패 시 None 반환
    """
    if len(data) < _MIN_PKT_LEN:
        return None

    # 매직 넘버 확인
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic != _NEXMON_MAGIC:
        return None

    # 페이로드 길이 (헤더 20바이트 오프셋)
    try:
        payload_len = struct.unpack_from("<H", data, 20)[0]
    except struct.error:
        return None

    payload_start = 22
    payload = data[payload_start: payload_start + payload_len]
    if len(payload) < 4:
        return None

    # CSI 데이터: int16 인터리브 (실수, 허수, 실수, 허수, ...)
    n_values = len(payload) // 2
    raw = np.frombuffer(payload, dtype=np.int16, count=n_values).astype(np.float32)

    # 복소수 재구성 → 진폭 계산
    real = raw[0::2]
    imag = raw[1::2]
    amplitudes = np.sqrt(real ** 2 + imag ** 2)

    # 서브캐리어 수를 _N_SUBCARRIERS 로 정규화 (패딩 또는 트리밍)
    if len(amplitudes) < _N_SUBCARRIERS:
        amplitudes = np.pad(amplitudes, (0, _N_SUBCARRIERS - len(amplitudes)))
    else:
        amplitudes = amplitudes[:_N_SUBCARRIERS]

    return amplitudes


class CSIReader:
    """
    백그라운드 스레드에서 UDP 소켓을 수신하며 CSI 샘플을 Queue에 쌓는다.

    Usage:
        reader = CSIReader()
        reader.start()
        ts, amp = reader.queue.get()   # (timestamp_float, np.ndarray)
        reader.stop()
    """

    def __init__(self, host: str = "0.0.0.0", port: int = _UDP_PORT,
                 maxsize: int = 1000):
        self.queue: Queue[tuple[float, np.ndarray]] = Queue(maxsize=maxsize)
        self._host = host
        self._port = port
        self._stop_event = Event()
        self._thread: Thread | None = None
        self.n_received = 0
        self.n_parsed = 0

    def start(self):
        self._stop_event.clear()
        self._thread = Thread(target=self._recv_loop, daemon=True, name="CSIReader")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _recv_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(0.5)
        sock.bind((self._host, self._port))

        while not self._stop_event.is_set():
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            self.n_received += 1
            ts = time.time()
            amp = _parse_packet(data)
            if amp is not None:
                self.n_parsed += 1
                if not self.queue.full():
                    self.queue.put((ts, amp))

        sock.close()
