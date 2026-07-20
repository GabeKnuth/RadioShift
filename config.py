#!/usr/bin/env python3
from dataclasses import dataclass, field
from typing import Dict

@dataclass
class RadioConfig:
    # I2C Configuration
    TEA5767_ADDRESS: int = 0x60
    I2C_BUS_NUMBER: int = 1

    # Audio Configuration
    INPUT_DEVICE: int = 1
    OUTPUT_DEVICE: int = 1
    SAMPLE_RATE: int = 44100
    BLOCKSIZE: int = 4096
    INPUT_CHANNELS: int = 1
    OUTPUT_CHANNELS: int = 2

    # Persistence Configuration
    PERSISTENCE_ENABLED: bool = True

    # Buffer Configuration
    PAST_BUFFER_SECONDS: int = 5
    FUTURE_BUFFER_SECONDS: int = 60

    @property
    def MAX_BUFFER_SECONDS(self) -> int:
        return self.PAST_BUFFER_SECONDS + self.FUTURE_BUFFER_SECONDS

    # GPIO Configuration
    BUTTON_GPIO_PINS: Dict[str, int] = field(default_factory=lambda: {
        'backward': 17,
        'forward': 27,
        'play_pause': 22,
        'live': 23
    })

    # Tuning Configuration
    FREQUENCY_STEP: float = 0.2
    DEFAULT_FREQUENCY: float = 99.9

    # RSSI Configuration
    RSSI_READ_INTERVAL: int = 15
    ENABLE_RSSI: bool = True

    # Display Configuration
    FONT_PATH: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    FONT_SIZES: Dict[str, int] = field(default_factory=lambda: {
        'small': 11,
        'medium': 14,
        'large': 27
    })

    # UI refresh rate
    DISPLAY_REFRESH_HZ: int = 4


config = RadioConfig()
