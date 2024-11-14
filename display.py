#!/usr/bin/env python3
# display.py - OLED display handling

# Standard library imports
import threading
import logging
from typing import Optional, Dict

# Third-party imports
from PIL import ImageFont
from luma.core.interface.serial import spi
from luma.oled.device import ssd1306
from luma.core.render import canvas
import RPi.GPIO as GPIO

# Local imports
from config import RadioConfig

class Display:
    def __init__(self, config):
        self.config = config
        self.current_message = None
        self.message_timer = None
        self._last_freq = None
        self._last_paused = None
        self._last_rssi_handler = None
        self._last_audio_buffer = None
        
        # Disable GPIO warnings
        GPIO.setwarnings(False)
        
        # Initialize OLED
        serial_interface = spi(device=0, port=0)
        self.oled = ssd1306(serial_interface)
        
        # Initialize fonts
        self.fonts = self._initialize_fonts()

    def _initialize_fonts(self) -> Dict[str, ImageFont.FreeTypeFont]:
        """Initialize fonts with fallbacks"""
        fonts = {}
        for name, size in self.config.FONT_SIZES.items():
            try:
                fonts[name] = ImageFont.truetype(self.config.FONT_PATH, size)
            except IOError:
                logging.warning(f"Failed to load {name} font, using default")
                fonts[name] = ImageFont.load_default()
        return fonts

    def clear_message(self) -> None:
        """Clear temporary message from display and trigger update"""
        print("Clearing")
        self.current_message = None
        # Trigger a display update with the last known state
        if self._last_freq is not None:
            self.update(
                self._last_freq,
                self._last_paused,
                self._last_rssi_handler,
                self._last_audio_buffer
            )

    def update(self, freq: float, paused: bool, rssi_handler=None, audio_buffer=None, message: Optional[str] = None) -> None:
        """Update OLED display with current status"""
        # Store the current state
        self._last_freq = freq
        self._last_paused = paused
        self._last_rssi_handler = rssi_handler
        self._last_audio_buffer = audio_buffer
        
        with canvas(self.oled) as draw:
            # Clear display
            draw.rectangle(self.oled.bounding_box, outline=0, fill=0)

            # Draw frequency
            self._draw_frequency(draw, freq)
            
            # Draw RSSI if available
            if rssi_handler and self.config.ENABLE_RSSI:
                self._draw_signal_strength(draw, rssi_handler)
            
            # Draw playback status
            self._draw_playback_status(draw, paused)
            
            # Draw buffer time if available
            if audio_buffer:
                self._draw_buffer_time(draw, audio_buffer, paused)
            
            # Draw message
            self._draw_message(draw, message)

    def _draw_frequency(self, draw, freq: float) -> None:
        """Draw frequency display with perfect horizontal and vertical centering"""
        # Get frequency text dimensions
        freq_text = f"{freq:.1f}"
        bbox_freq = self.fonts['large'].getbbox(freq_text)
        freq_width = bbox_freq[2] - bbox_freq[0]
        freq_height = bbox_freq[3] - bbox_freq[1]

        # Get MHz text dimensions
        mhz_text = "MHz"
        bbox_mhz = self.fonts['small'].getbbox(mhz_text)
        mhz_width = bbox_mhz[2] - bbox_mhz[0]
        mhz_height = bbox_mhz[3] - bbox_mhz[1]

        # Calculate total width and height for centering
        spacing = 2  # Space between frequency and MHz
        total_width = freq_width + spacing + mhz_width
        total_height = max(freq_height, mhz_height)

        # Calculate center positions
        center_x = 128 // 2  # Screen width / 2
        center_y = 32  # Screen height / 2 (assuming 64 pixel height)

        # Calculate starting positions for perfect centering
        freq_x = center_x - (total_width // 2)
        mhz_x = freq_x + freq_width + spacing

        # Vertically align both texts to middle
        freq_y = center_y - (freq_height // 2)
        mhz_y = center_y - (mhz_height // 2)

        # Draw the texts
        draw.text((freq_x, freq_y -5), freq_text, fill="white", font=self.fonts['large'])
        draw.text((mhz_x, mhz_y + 4), mhz_text, fill="white", font=self.fonts['small'])

    def _draw_signal_strength(self, draw, rssi_handler) -> None:
        """Draw signal strength bars"""
        rssi = rssi_handler.get_rssi()
        bars = rssi_handler.rssi_to_bars(rssi)
        
        bar_width = 4
        bar_height_unit = 3
        spacing = 2
        x_start = 5
        y_start = 35

        for i in range(5):
            bar_height = (i + 1) * bar_height_unit
            y_pos = y_start + (5 * bar_height_unit) - bar_height
            if i < bars:
                draw.rectangle([
                    x_start + i*(bar_width + spacing),
                    y_pos,
                    x_start + i*(bar_width + spacing) + bar_width,
                    y_start + (5 * bar_height_unit)
                ], fill="white")
            else:
                draw.rectangle([
                    x_start + i*(bar_width + spacing),
                    y_pos,
                    x_start + i*(bar_width + spacing) + bar_width,
                    y_start + (5 * bar_height_unit)
                ], outline="white")

    def _draw_playback_status(self, draw, paused: bool) -> None:
        """Draw playback status centered at the bottom of display"""
        if not self.current_message:  # Only draw status if no message is showing
            status_text = "PAUSED" if paused else "PLAYING"
            bbox_status = self.fonts['small'].getbbox(status_text)
            status_width = bbox_status[2] - bbox_status[0]
            status_height = bbox_status[3] - bbox_status[1]
            
            status_x = (128 - status_width) // 2
            status_y = 64 - status_height - 3
            
            draw.text((status_x, status_y), status_text, fill="white", font=self.fonts['small'])

    def _draw_buffer_time(self, draw, audio_buffer, paused: bool) -> None:
        """Draw buffer time based on playback state: live, paused, or buffered playback."""
        
        if audio_buffer.is_live() and not paused:
            buffer_text = "LIVE"
        elif paused:
            buffer_text = f"-{audio_buffer.get_remaining_buffer_time():.1f}s"
        else:
            buffer_text = f"-{audio_buffer.get_remaining_buffer_time():.1f}s"

        bbox_buffer = self.fonts['small'].getbbox(buffer_text)
        buffer_width = bbox_buffer[2] - bbox_buffer[0]
        draw.text((128 - buffer_width - 2, 2), buffer_text, fill="white", font=self.fonts['small'])

    def _draw_message(self, draw, message: Optional[str]) -> None:
        """Draw temporary message with full-width black background over playback status"""
        if message:
            self.current_message = message
            bbox_message = self.fonts['small'].getbbox(message)
            message_width = bbox_message[2] - bbox_message[0]
            message_height = bbox_message[3] - bbox_message[1]
            
            message_x = (128 - message_width) // 2
            message_y = 64 - message_height - 3
            
            vertical_padding = 2
            draw.rectangle([
                0,
                message_y - vertical_padding,
                128,
                message_y + message_height + vertical_padding
            ], fill="black", outline="black")
            
            draw.text((message_x, message_y), message, fill="white", font=self.fonts['small'])
            
            if self.message_timer and self.message_timer.is_alive():
                self.message_timer.cancel()
            self.message_timer = threading.Timer(1.0, self.clear_message)
            self.message_timer.start()
        
        elif self.current_message:
            bbox_message = self.fonts['small'].getbbox(self.current_message)
            message_width = bbox_message[2] - bbox_message[0]
            message_height = bbox_message[3] - bbox_message[1]
            
            message_x = (128 - message_width) // 2
            message_y = 64 - message_height - 3
            
            vertical_padding = 2
            draw.rectangle([
                0,
                message_y - vertical_padding,
                128,
                message_y + message_height + vertical_padding
            ], fill="black", outline="black")
            
            draw.text((message_x, message_y), self.current_message, fill="white", font=self.fonts['small'])

    def cleanup(self) -> None:
        """Clean up display resources"""
        self.oled.clear()
        self.oled.show()