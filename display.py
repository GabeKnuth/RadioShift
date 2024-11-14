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
        """Clear temporary message from display"""
        self.current_message = None

    def update(self, freq: float, paused: bool, rssi_handler=None, audio_buffer=None, message: Optional[str] = None) -> None:
        """Update OLED display with current status"""
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
        """Draw frequency display"""
        freq_text = f"{freq:.1f}"
        bbox = self.fonts['large'].getbbox(freq_text)
        freq_width = bbox[2] - bbox[0]
        freq_height = bbox[3] - bbox[1]

        mhz_text = "MHz"
        bbox_mhz = self.fonts['small'].getbbox(mhz_text)
        mhz_width = bbox_mhz[2] - bbox_mhz[0]
        mhz_height = bbox_mhz[3] - bbox_mhz[1]

        total_width = freq_width + 2 + mhz_width
        freq_x = (128 - total_width) // 2
        freq_y = 2
        mhz_x = freq_x + freq_width + 2
        mhz_y = freq_y + freq_height - mhz_height

        draw.text((freq_x, freq_y), freq_text, fill="white", font=self.fonts['large'])
        draw.text((mhz_x, mhz_y), mhz_text, fill="white", font=self.fonts['small'])

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
        """Draw playback status"""
        status_text = "PAUSED" if paused else "PLAYING"
        bbox_status = self.fonts['medium'].getbbox(status_text)
        status_width = bbox_status[2] - bbox_status[0]
        status_x = (128 - status_width) // 2
        draw.text((status_x, 40), status_text, fill="white", font=self.fonts['medium'])

    def _draw_buffer_time(self, draw, audio_buffer, paused: bool) -> None:
        """Draw buffer time based on playback state: live, paused, or buffered playback."""
        
        if audio_buffer.is_live() and not paused:
            buffer_text = "LIVE"
        elif paused:
            # Show future buffer time if playback is paused
            buffer_text = f"-{audio_buffer.get_future_buffer_time():.1f}s"
        else:
            # Show remaining buffer time when playing from buffer
            buffer_text = f"-{audio_buffer.get_remaining_buffer_time():.1f}s"

        # Draw the buffer text on the display
        bbox_buffer = self.fonts['small'].getbbox(buffer_text)
        buffer_width = bbox_buffer[2] - bbox_buffer[0]
        draw.text((128 - buffer_width - 2, 2), buffer_text, fill="white", font=self.fonts['small'])


    # def _draw_buffer_time(self, draw, audio_buffer, paused: bool) -> None:
    #     """Draw buffer time"""
    #     buffer_time = audio_buffer.get_delayed_time()
    #     if buffer_time <= 0.1 and not paused:
    #         buffer_text = "LIVE"
    #     else:
    #         buffer_time = min(buffer_time, self.config.MAX_BUFFER_SECONDS)
    #         buffer_text = f"-{buffer_time:.1f}s"
        
    #     bbox_buffer = self.fonts['small'].getbbox(buffer_text)
    #     buffer_width = bbox_buffer[2] - bbox_buffer[0]
    #     draw.text((128 - buffer_width - 2, 2), buffer_text, 
    #              fill="white", font=self.fonts['small'])

    def _draw_message(self, draw, message: Optional[str]) -> None:
        """Draw temporary message"""
        if message:
            self.current_message = message
            bbox_message = self.fonts['small'].getbbox(message)
            message_width = bbox_message[2] - bbox_message[0]
            message_x = (128 - message_width) // 2
            draw.text((message_x, 55), message, fill="white", font=self.fonts['small'])
            
            if self.message_timer and self.message_timer.is_alive():
                self.message_timer.cancel()
            self.message_timer = threading.Timer(2.0, self.clear_message)
            self.message_timer.start()
        elif self.current_message:
            bbox_message = self.fonts['small'].getbbox(self.current_message)
            message_width = bbox_message[2] - bbox_message[0]
            message_x = (128 - message_width) // 2
            draw.text((message_x, 55), self.current_message, 
                     fill="white", font=self.fonts['small'])

    def cleanup(self) -> None:
        """Clean up display resources"""
        self.oled.clear()
        self.oled.show()
