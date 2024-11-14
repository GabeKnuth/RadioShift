#!/usr/bin/env python3
# rssi.py - RSSI handling functionality

# Standard library imports
import threading
import time
import logging
from typing import Optional

# Third-party imports
from smbus2 import SMBus, i2c_msg

# Local imports
from config import RadioConfig

class RSSIHandler:
    def __init__(self, config):
        self.config = config
        self.current_rssi = 0
        self.rssi_lock = threading.Lock()
        self.i2c_lock = threading.Lock()
        self.running = True

    def read_signal_strength(self) -> None:
        """Read signal strength from the TEA5767 tuner"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with self.i2c_lock:
                    read = i2c_msg.read(self.config.TEA5767_ADDRESS, 5)
                    bus = SMBus(self.config.I2C_BUS_NUMBER)
                    bus.i2c_rdwr(read)
                    status = list(read)
                    bus.close()
                
                rssi = (status[3] >> 4) & 0x0F
                with self.rssi_lock:
                    self.current_rssi = rssi
                return

            except Exception as e:
                logging.error(f"Attempt {attempt + 1}: Error reading signal strength: {e}")
                time.sleep(0.1)

        with self.rssi_lock:
            self.current_rssi = 0
        logging.error("Failed to read RSSI after multiple attempts")

    def get_rssi(self) -> int:
        """Get the current RSSI value"""
        with self.rssi_lock:
            return self.current_rssi

    @staticmethod
    def rssi_to_bars(rssi: int, max_bars: int = 5) -> int:
        """Convert RSSI value to number of signal strength bars"""
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

    def start_monitoring(self, display_update_callback) -> None:
        """Start periodic RSSI monitoring"""
        def monitor_loop():
            while self.running and self.config.ENABLE_RSSI:
                self.read_signal_strength()
                if display_update_callback:
                    display_update_callback()
                time.sleep(self.config.RSSI_READ_INTERVAL)

        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()
        return thread

    def stop_monitoring(self) -> None:
        """Stop RSSI monitoring"""
        self.running = False
