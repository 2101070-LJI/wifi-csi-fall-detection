"""
mic_reader.py — sounddevice 기반 실시간 마이크 오디오 수집

RMS 진폭을 계산해 (timestamp, amplitude) 쌍을 Queue에 전달한다.
"""

import time
from threading import Event
from queue import Queue

import numpy as np
import sounddevice as sd

_DEFAULT_SAMPLERATE = 44100
_DEFAULT_BLOCKSIZE  = 1024     # ~23ms per block
_DEFAULT_CHANNELS   = 1


class MicReader:
    """
    sounddevice InputStream으로 마이크를 비동기 수집한다.

    Usage:
        reader = MicReader()
        reader.start()
        ts, rms = reader.queue.get()   # (timestamp_float, float 0~1)
        reader.stop()
    """

    def __init__(self, device=None,
                 samplerate: int = _DEFAULT_SAMPLERATE,
                 blocksize: int  = _DEFAULT_BLOCKSIZE,
                 channels: int   = _DEFAULT_CHANNELS,
                 maxsize: int    = 2000):
        self.queue: Queue[tuple[float, float]] = Queue(maxsize=maxsize)
        self._device     = device
        self._samplerate = samplerate
        self._blocksize  = blocksize
        self._channels   = channels
        self._stop_event = Event()
        self._stream: sd.InputStream | None = None

    def start(self):
        self._stop_event.clear()
        self._stream = sd.InputStream(
            device=self._device,
            samplerate=self._samplerate,
            blocksize=self._blocksize,
            channels=self._channels,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self):
        self._stop_event.set()
        if self._stream:
            self._stream.stop()
            self._stream.close()

    def _callback(self, indata: np.ndarray, frames: int,
                  time_info, status):
        if status:
            pass  # 오버플로 등 무시
        ts  = time.time()
        rms = float(np.sqrt(np.mean(indata ** 2)))
        if not self.queue.full():
            self.queue.put((ts, rms))
