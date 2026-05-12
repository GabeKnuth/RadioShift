#!/usr/bin/env python3
import threading
import time
import logging

from smbus2 import SMBus, i2c_msg
from config import RadioConfig

class RSSIHandler:
    def __init__(self, config):
        self.config = config
        self.current_rssi = 0
        self.running = True
        self._bus = None
        self._bus_lock = threading.Lock()

    def _get_bus(self) -> SMBus:
        if self._bus is None:
            self._bus = SMBus(self.config.I2C_BUS_NUMBER)
        return self._bus

    def read_signal_strength(self) -> None:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with self._bus_lock:
                    read = i2c_msg.read(self.config.TEA5767_ADDRESS, 5)
                    self._get_bus().i2c_rdwr(read)
                    status = list(read)
                rssi = (status[3] >> 4) & 0x0F
                self.current_rssi = rssi
                return
            except Exception as e:
                logging.error(f"Attempt {attempt + 1}: Error reading signal strength: {e}")
                with self._bus_lock:
                    try:
                        if self._bus:
                            self._bus.close()
                    except Exception:
                        pass
                    self._bus = None
                time.sleep(0.1)

        self.current_rssi = 0
        logging.error("Failed to read RSSI after multiple attempts")

    def get_rssi(self) -> int:
        return self.current_rssi

    @staticmethod
    def rssi_to_bars(rssi: int, max_bars: int = 5) -> int:
        if rssi >= 14:
            return max_bars
        elif rssi >= 11:
            return 4
        elif rssi >= 8:
            return 3
        elif rssi >= 5:
            return 2
        elif rssi >= 2:
            return 1
        else:
            return 0

    def start_monitoring(self) -> threading.Thread:
        def monitor_loop():
            while self.running and self.config.ENABLE_RSSI:
                self.read_signal_strength()
                time.sleep(self.config.RSSI_READ_INTERVAL)

        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()
        return thread

    def stop_monitoring(self) -> None:
        self.running = False
        with self._bus_lock:
            if self._bus:
                try:
                    self._bus.close()
                except Exception:
                    pass
                self._bus = None
