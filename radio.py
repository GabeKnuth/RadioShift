#!/usr/bin/env python3
# radio.py - TEA5767 radio control with RSSI updates upon stabilization

# Standard library imports
import threading
import time
import logging
from typing import Callable

# Third-party imports
from smbus2 import SMBus

# Local imports
from config import RadioConfig
from rssi import RSSIHandler

class Radio:
    def __init__(self, config, display_callback: Callable, rssi_handler: RSSIHandler, persistence_handler=None):
        self.config = config
        self.display_callback = display_callback
        self.rssi_handler = rssi_handler  
        self.persistence_handler = persistence_handler
        self.frequency = self.config.DEFAULT_FREQUENCY
        self.i2c_lock = threading.Lock()
        self.stabilization_timer = None

    def set_frequency(self, freq: float, stabilize: bool = False, update_rssi: bool = False) -> None:
        try:
            freq = max(87.5, min(freq, 108.0))
            freq = round(freq * 10) / 10.0
            
            self.frequency = freq
            frequency_hz = freq * 1_000_000
            pll = int((4 * (frequency_hz + 225_000)) / 32_768)

            data = [
                (pll >> 8) & 0x3F,  # First byte
                pll & 0xFF,         # Second byte
                0xF0,              # Force mono mode + high side injection
                0x90,              # Maximum sensitivity (-7dBμV)
                0x40               # US deemphasis
            ]

            with self.i2c_lock:
                bus = SMBus(self.config.I2C_BUS_NUMBER)
                bus.write_i2c_block_data(self.config.TEA5767_ADDRESS, data[0], data[1:])
                bus.close()

            logging.info(f"Frequency set to {freq:.1f} MHz (mono)")

            if stabilize:
                time.sleep(0.5)
                if update_rssi and self.config.ENABLE_RSSI:
                    self.rssi_handler.read_signal_strength()
                if self.persistence_handler and self.config.PERSISTENCE_ENABLED:
                    self.persistence_handler.save_frequency(freq)

            if self.display_callback:
                self.display_callback()

        except Exception as e:
            logging.error(f"Error setting frequency: {e}")

    def adjust_frequency(self, delta: int) -> None:
        """Adjust frequency by delta steps and set stabilization timer with RSSI update"""
        # Cancel previous stabilization timer if still running
        if self.stabilization_timer and self.stabilization_timer.is_alive():
            self.stabilization_timer.cancel()

        # Adjust frequency without stabilization
        new_freq = self.frequency + (delta * self.config.FREQUENCY_STEP)
        self.set_frequency(new_freq, stabilize=False)

        # Set stabilization timer to run set_frequency with stabilization and RSSI update after delay
        def stabilized_callback():
            self.set_frequency(new_freq, stabilize=True, update_rssi=True)
            # Save frequency after PLL lock
            if self.persistence_handler and self.config.PERSISTENCE_ENABLED:
                self.persistence_handler.save_frequency(new_freq)
        
        self.stabilization_timer = threading.Timer(0.5, stabilized_callback)
        self.stabilization_timer.start()

    def get_frequency(self) -> float:
        """Get current frequency"""
        return self.frequency
