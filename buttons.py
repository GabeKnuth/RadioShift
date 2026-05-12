#!/usr/bin/env python3
import threading
import time
import logging
from typing import Callable, Dict

import RPi.GPIO as GPIO
import evdev

from config import RadioConfig

class ButtonHandler:
    def __init__(self, config, callbacks: Dict[str, Callable]):
        self.config = config
        self.callbacks = callbacks
        self.running = True
        self._setup_gpio()

    def _setup_gpio(self) -> None:
        GPIO.setmode(GPIO.BCM)
        for pin in self.config.BUTTON_GPIO_PINS.values():
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def start_polling(self) -> threading.Thread:
        thread = threading.Thread(target=self._poll_buttons, daemon=True)
        thread.start()
        return thread

    def _poll_buttons(self) -> None:
        while self.running:
            if not GPIO.input(self.config.BUTTON_GPIO_PINS['backward']):
                self.callbacks['backward']()
                time.sleep(0.2)
            if not GPIO.input(self.config.BUTTON_GPIO_PINS['forward']):
                self.callbacks['forward']()
                time.sleep(0.2)
            if not GPIO.input(self.config.BUTTON_GPIO_PINS['play_pause']):
                self.callbacks['play_pause']()
                time.sleep(0.2)
            if not GPIO.input(self.config.BUTTON_GPIO_PINS['live']):
                self.callbacks['live']()
                time.sleep(0.2)
            time.sleep(0.05)

    def cleanup(self) -> None:
        self.running = False
        GPIO.cleanup()

class RotaryHandler:
    def __init__(self, config, callback: Callable[[int], None]):
        self.config = config
        self.callback = callback
        self.running = True

    @staticmethod
    def find_device(keyword: str) -> str:
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        for device in devices:
            if keyword.lower() in device.name.lower():
                return device.path
        return None

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self._monitor_rotary, daemon=True)
        thread.start()
        return thread

    def _monitor_rotary(self) -> None:
        try:
            rotary_device_path = self.find_device('rotary')
            if not rotary_device_path:
                logging.error("Rotary encoder device not found")
                return

            rotary_device = evdev.InputDevice(rotary_device_path)
            logging.info(f"Monitoring rotary encoder on {rotary_device.path}")

            for event in rotary_device.read_loop():
                if not self.running:
                    break
                if event.type == evdev.ecodes.EV_REL:
                    if event.code == evdev.ecodes.REL_X:
                        self.callback(event.value)

        except Exception as e:
            logging.error(f"Rotary encoder error: {e}")

    def stop(self) -> None:
        self.running = False
