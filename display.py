#!/usr/bin/env python3
import threading
import logging
from typing import Optional, Dict

from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import spi
from luma.oled.device import ssd1306
import RPi.GPIO as GPIO

from config import RadioConfig

class Display:
    def __init__(self, config):
        self.config = config
        self._message = None
        self._message_timer = None
        self._dirty = True

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        serial_interface = spi(device=0, port=0)
        self.oled = ssd1306(serial_interface)
        self.fonts = self._initialize_fonts()

        # Snapshot of state for the render loop to read
        self._freq = config.DEFAULT_FREQUENCY
        self._paused = False
        self._rssi = 0
        self._rssi_bars = 0
        self._is_live = True
        self._buffer_offset = 0.0

    def _initialize_fonts(self) -> Dict[str, ImageFont.FreeTypeFont]:
        fonts = {}
        for name, size in self.config.FONT_SIZES.items():
            try:
                fonts[name] = ImageFont.truetype(self.config.FONT_PATH, size)
            except IOError:
                logging.warning(f"Failed to load {name} font, using default")
                fonts[name] = ImageFont.load_default()
        return fonts

    def mark_dirty(self):
        self._dirty = True

    def set_state(self, freq=None, paused=None, rssi_handler=None, audio_buffer=None, message=None):
        if freq is not None:
            self._freq = freq
        if paused is not None:
            self._paused = paused
        if rssi_handler is not None:
            self._rssi = rssi_handler.get_rssi()
            self._rssi_bars = rssi_handler.rssi_to_bars(self._rssi)
        if audio_buffer is not None:
            self._is_live = audio_buffer.is_live()
            self._buffer_offset = audio_buffer.get_remaining_buffer_time()
        if message is not None:
            self._message = message
            if self._message_timer and self._message_timer.is_alive():
                self._message_timer.cancel()
            self._message_timer = threading.Timer(1.0, self._clear_message)
            self._message_timer.start()
        self._dirty = True

    def _clear_message(self):
        self._message = None
        self._dirty = True

    def render_if_dirty(self):
        if not self._dirty:
            return
        self._dirty = False
        self._render()

    def _render(self):
        # Build the frame in memory, then push to SPI in one shot
        img = Image.new('1', (self.oled.width, self.oled.height), 0)
        draw = ImageDraw.Draw(img)

        self._draw_frequency(draw, self._freq)

        if self.config.ENABLE_RSSI:
            self._draw_signal_strength(draw, self._rssi_bars)

        self._draw_buffer_indicator(draw)

        if self._message:
            self._draw_message(draw, self._message)
        else:
            self._draw_playback_status(draw, self._paused)

        self.oled.display(img)

    def _draw_frequency(self, draw, freq: float) -> None:
        freq_text = f"{freq:.1f}"
        bbox_freq = self.fonts['large'].getbbox(freq_text)
        freq_width = bbox_freq[2] - bbox_freq[0]
        freq_height = bbox_freq[3] - bbox_freq[1]

        mhz_text = "MHz"
        bbox_mhz = self.fonts['small'].getbbox(mhz_text)
        mhz_width = bbox_mhz[2] - bbox_mhz[0]
        mhz_height = bbox_mhz[3] - bbox_mhz[1]

        spacing = 2
        total_width = freq_width + spacing + mhz_width

        center_x = 128 // 2
        center_y = 32

        freq_x = center_x - (total_width // 2)
        mhz_x = freq_x + freq_width + spacing
        freq_y = center_y - (freq_height // 2)
        mhz_y = center_y - (mhz_height // 2)

        draw.text((freq_x, freq_y - 5), freq_text, fill="white", font=self.fonts['large'])
        draw.text((mhz_x, mhz_y + 4), mhz_text, fill="white", font=self.fonts['small'])

    def _draw_signal_strength(self, draw, bars: int) -> None:
        x_ant = 2
        y_ant = 3

        draw.line([(x_ant, y_ant), (x_ant + 6, y_ant)], fill="white")
        draw.point((x_ant + 1, y_ant + 1), fill="white")
        draw.point((x_ant + 5, y_ant + 1), fill="white")
        draw.point((x_ant + 2, y_ant + 2), fill="white")
        draw.point((x_ant + 4, y_ant + 2), fill="white")
        for dy in range(3, 9):
            draw.point((x_ant + 3, y_ant + dy), fill="white")

        bar_width = 2
        bar_spacing = 1
        base_height = 2
        x_start = 11
        y_bottom = 11

        for i in range(bars):
            bar_height = (i + 1) * base_height
            y2 = y_bottom
            y1 = y_bottom - bar_height + 1
            draw.rectangle([
                x_start + i * (bar_width + bar_spacing),
                y1,
                x_start + i * (bar_width + bar_spacing) + bar_width - 1,
                y2
            ], fill="white")

    def _draw_playback_status(self, draw, paused: bool) -> None:
        status_text = "PAUSED" if paused else "PLAYING"
        bbox = self.fonts['small'].getbbox(status_text)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        draw.text(((128 - w) // 2, 64 - h - 3), status_text, fill="white", font=self.fonts['small'])

    def _draw_buffer_indicator(self, draw) -> None:
        if self._is_live and not self._paused:
            text = "LIVE"
        else:
            text = f"-{self._buffer_offset:.1f}s"

        bbox = self.fonts['small'].getbbox(text)
        w = bbox[2] - bbox[0]
        draw.text((128 - w - 2, 2), text, fill="white", font=self.fonts['small'])

    def _draw_message(self, draw, message: str) -> None:
        bbox = self.fonts['small'].getbbox(message)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        msg_x = (128 - w) // 2
        msg_y = 64 - h - 3

        draw.rectangle([0, msg_y - 2, 128, msg_y + h + 2], fill="black")
        draw.text((msg_x, msg_y), message, fill="white", font=self.fonts['small'])

    def cleanup(self) -> None:
        if self._message_timer and self._message_timer.is_alive():
            self._message_timer.cancel()
        self.oled.clear()
        self.oled.show()
