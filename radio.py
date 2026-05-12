#!/usr/bin/env python3
import threading
import time
import logging

from smbus2 import SMBus
from config import RadioConfig
from rssi import RSSIHandler

class Radio:
    def __init__(self, config, rssi_handler: RSSIHandler, persistence_handler=None):
        self.config = config
        self.rssi_handler = rssi_handler
        self.persistence_handler = persistence_handler
        self.frequency = self.config.DEFAULT_FREQUENCY
        self._bus = None
        self._bus_lock = threading.Lock()
        self.stabilization_timer = None
        # Set by main after construction
        self.on_frequency_changed = None

    def _get_bus(self) -> SMBus:
        if self._bus is None:
            self._bus = SMBus(self.config.I2C_BUS_NUMBER)
        return self._bus

    def set_frequency(self, freq: float, stabilize: bool = False, update_rssi: bool = False) -> None:
        try:
            freq = max(87.5, min(freq, 108.0))
            freq = round(freq * 10) / 10.0
            self.frequency = freq

            frequency_hz = freq * 1_000_000
            pll = int((4 * (frequency_hz + 225_000)) / 32_768)

            data = [
                (pll >> 8) & 0x3F,
                pll & 0xFF,
                0xF0,
                0x90,
                0x40
            ]

            with self._bus_lock:
                self._get_bus().write_i2c_block_data(self.config.TEA5767_ADDRESS, data[0], data[1:])

            logging.info(f"Frequency set to {freq:.1f} MHz (mono)")

            if stabilize:
                time.sleep(0.5)
                if update_rssi and self.config.ENABLE_RSSI:
                    self.rssi_handler.read_signal_strength()
                if self.persistence_handler and self.config.PERSISTENCE_ENABLED:
                    self.persistence_handler.save_frequency(freq)

            if self.on_frequency_changed:
                self.on_frequency_changed()

        except Exception as e:
            logging.error(f"Error setting frequency: {e}")
            with self._bus_lock:
                try:
                    if self._bus:
                        self._bus.close()
                except Exception:
                    pass
                self._bus = None

    def adjust_frequency(self, delta: int) -> None:
        if self.stabilization_timer and self.stabilization_timer.is_alive():
            self.stabilization_timer.cancel()

        new_freq = self.frequency + (delta * self.config.FREQUENCY_STEP)
        self.set_frequency(new_freq, stabilize=False)

        def stabilized_callback():
            self.set_frequency(new_freq, stabilize=True, update_rssi=True)
            if self.persistence_handler and self.config.PERSISTENCE_ENABLED:
                self.persistence_handler.save_frequency(new_freq)

        self.stabilization_timer = threading.Timer(0.5, stabilized_callback)
        self.stabilization_timer.start()

    def get_frequency(self) -> float:
        return self.frequency

    def cleanup(self):
        with self._bus_lock:
            if self._bus:
                try:
                    self._bus.close()
                except Exception:
                    pass
                self._bus = None
